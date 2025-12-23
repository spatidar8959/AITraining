"""
Training API endpoints for frame training, job status, and rollback
"""
from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional
from datetime import datetime, timedelta
import json
import time
import os

from app.database import get_db
from app.models import (
    VideoBatch, ExtractedFrame, TrainingJob, FrameEmbedding,
    VideoStatus, FrameStatus, JobStatus,
    ProcessingLog, EntityType, LogStatus
)
from app.schemas import (
    TrainingExecuteRequest, TrainingExecuteResponse,
    TrainingStatusResponse, TrainingRollbackResponse,
    TrainingJobListResponse, TrainingJobItem,
    ErrorResponse
)
from app.tasks.training import train_frames_task, rollback_training_task
from app.utils.logger import app_logger
from app.utils.session import get_client_session_id, get_request_id

# #region agent log
DEBUG_LOG_PATH = os.getenv("DEBUG_LOG_PATH", "/app/project/logs/debug.log")
# #endregion

router = APIRouter(prefix="/api/training", tags=["training"])


@router.get("/list", response_model=TrainingJobListResponse)
def list_training_jobs(
    page: int = 1,
    page_size: int = 20,
    video_id: Optional[int] = None,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    List all training jobs with pagination and filtering.

    Args:
        page: Page number (starts at 1)
        page_size: Items per page
        video_id: Optional filter by video ID
        status_filter: Optional filter by job status
        db: Database session

    Returns:
        Paginated list of training jobs
    """
    try:
        from sqlalchemy import func

        # Build query
        query = db.query(
            TrainingJob,
            VideoBatch.asset_name.label('video_name')
        ).join(VideoBatch, TrainingJob.video_id == VideoBatch.id)

        # Apply filters
        if video_id:
            query = query.filter(TrainingJob.video_id == video_id)

        if status_filter:
            try:
                status_enum = JobStatus(status_filter)
                query = query.filter(TrainingJob.status == status_enum)
            except ValueError:
                raise HTTPException(
                    http_status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status: {status_filter}. Valid: pending, processing, completed, failed, paused, rolled_back"
                )

        # Get total count
        total = query.count()

        # Apply pagination
        offset = (page - 1) * page_size
        results = query.order_by(TrainingJob.created_at.desc()).offset(offset).limit(page_size).all()

        # Build response
        job_items = []
        for job, video_name in results:
            progress_percent = 0.0
            if job.total_frames > 0:
                progress_percent = round((job.processed_frames / job.total_frames) * 100, 2)

            job_items.append(TrainingJobItem(
                id=job.id,
                video_id=job.video_id,
                video_name=video_name,
                status=job.status,
                total_frames=job.total_frames,
                processed_frames=job.processed_frames,
                failed_frames=job.failed_frames,
                progress_percent=progress_percent,
                started_at=job.started_at,
                completed_at=job.completed_at,
                rolled_back_at=job.rolled_back_at,  # Add this line
                created_at=job.created_at
            ))

        return TrainingJobListResponse(
            total=total,
            page=page,
            page_size=page_size,
            jobs=job_items
        )

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error listing training jobs: {str(e)}", exc_info=True)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list training jobs: {str(e)}"
        )


@router.post("/execute", response_model=TrainingExecuteResponse, status_code=http_status.HTTP_200_OK)
def execute_training(
    request: TrainingExecuteRequest,
    db: Session = Depends(get_db),
    client_session_id: str = Depends(get_client_session_id)
):
    """
    Execute training job for selected frames.
    """
    try:
        # Deduplicate frame_ids if provided
        if request.frame_ids:
            request.frame_ids = list(dict.fromkeys(request.frame_ids))  # Preserves order while removing duplicates
        
        # Validate video exists
        video = db.query(VideoBatch).filter(VideoBatch.id == request.video_id).first()
        if not video:
            raise HTTPException(
                http_status.HTTP_404_NOT_FOUND,
                detail=f"Video {request.video_id} not found"
            )

        # Validate video is extracted
        if video.status != VideoStatus.EXTRACTED:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                detail=f"Video must be in 'extracted' status, current status: {video.status}"
            )

        # Build frame query
        frame_query = db.query(ExtractedFrame).filter(
            and_(
                ExtractedFrame.video_id == request.video_id,
                ExtractedFrame.status == FrameStatus.SELECTED,
                ExtractedFrame.deleted_at.is_(None)
            )
        )

        # Filter by specific frame_ids if provided
        if request.frame_ids:
            frame_query = frame_query.filter(ExtractedFrame.id.in_(request.frame_ids))

        frames = frame_query.all()

        if not frames:
            # Get detailed info about why frames are not available
            if request.frame_ids:
                all_frames = db.query(ExtractedFrame).filter(
                    ExtractedFrame.id.in_(request.frame_ids),
                    ExtractedFrame.video_id == request.video_id,
                    ExtractedFrame.deleted_at.is_(None)
                ).all()
                
                status_details = {}
                for frame in all_frames:
                    status = frame.status.value
                    if status not in status_details:
                        status_details[status] = []
                    status_details[status].append(frame.id)
                
                error_msg = "No selected frames found for training."
                if status_details:
                    error_msg += f" Frame statuses: {', '.join([f'{len(ids)} frames are {status}' for status, ids in status_details.items()])}"
                
                raise HTTPException(
                    http_status.HTTP_400_BAD_REQUEST,
                    detail=error_msg
                )
            else:
                raise HTTPException(
                    http_status.HTTP_400_BAD_REQUEST,
                    detail="No selected frames found for training"
                )

        # Validate frames belong to the video
        if request.frame_ids:
            invalid_frames = [fid for fid in request.frame_ids if fid not in [f.id for f in frames]]
            if invalid_frames:
                # Get status of invalid frames for better error message
                invalid_frame_details = db.query(ExtractedFrame).filter(
                    ExtractedFrame.id.in_(invalid_frames)
                ).all()
                
                status_info = {}
                deleted_frames = []
                wrong_video_frames = []
                
                for frame in invalid_frame_details:
                    # Check if frame is deleted
                    if frame.deleted_at is not None:
                        deleted_frames.append(frame.id)
                    # Check if frame belongs to wrong video
                    elif frame.video_id != request.video_id:
                        wrong_video_frames.append(frame.id)
                    else:
                        frame_status_value = frame.status.value
                        if frame_status_value not in status_info:
                            status_info[frame_status_value] = []
                        status_info[frame_status_value].append(frame.id)
                
                error_parts = []
                
                if wrong_video_frames:
                    error_parts.append(f"Frames from different video: {wrong_video_frames}")
                
                if deleted_frames:
                    error_parts.append(f"Deleted frames: {deleted_frames}")
                
                if status_info:
                    status_msgs = [f'IDs {ids} are {status_val}' for status_val, ids in status_info.items()]
                    error_parts.append(f"Statuses: {', '.join(status_msgs)}")
                
                error_msg = f"Invalid or non-selected frame IDs: {invalid_frames}"
                if error_parts:
                    error_msg += f". {' '.join(error_parts)}"
                error_msg += ". Please select frames first or ensure frames are not trained/deleted."
                
                raise HTTPException(
                    http_status.HTTP_400_BAD_REQUEST,
                    detail=error_msg
                )

        # Create training job
        training_job = TrainingJob(
            video_id=request.video_id,
            status=JobStatus.PENDING,
            total_frames=len(frames),
            processed_frames=0,
            failed_frames=0
        )
        db.add(training_job)
        db.commit()
        db.refresh(training_job)

        app_logger.info(f"Created training job {training_job.id} for video {request.video_id}, {len(frames)} frames")

        # Generate request ID for this operation
        request_id = get_request_id()

        # Trigger Celery task with client session context
        task = train_frames_task.apply_async(
            args=[training_job.id],
            kwargs={
                "client_session_id": client_session_id,
                "request_id": request_id
            }
        )
        training_job.celery_task_id = task.id
        db.commit()

        # Log training start
        log_entry = ProcessingLog(
            entity_type=EntityType.TRAINING_JOB,
            entity_id=training_job.id,
            action="training_started",
            status=LogStatus.SUCCESS,
            message=f"Training started for {len(frames)} frames",
            extra_metadata={
                "video_id": request.video_id,
                "total_frames": len(frames),
                "frame_ids": request.frame_ids if request.frame_ids else "all_selected"
            }
        )
        db.add(log_entry)
        db.commit()

        return TrainingExecuteResponse(
            job_id=training_job.id,
            task_id=task.id,
            total_frames=len(frames),
            message=f"Training started for {len(frames)} frames"
        )

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error executing training: {str(e)}", exc_info=True)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/{job_id}/status", response_model=TrainingStatusResponse)
def get_training_status(job_id: int, db: Session = Depends(get_db)):
    """
    Get training job status and progress.

    Args:
        job_id: Training job ID
        db: Database session

    Returns:
        TrainingStatusResponse with job details and progress
    """
    try:
        # Get training job - use fresh query with explicit refresh
        job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
        if job:
            db.refresh(job)  # Ensure we have latest state
        # #region agent log
        try:
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"I","location":"training.py:246","message":"API read job status","data":{"job_id":job_id,"status_in_db":job.status.value if job else None,"processed_frames":job.processed_frames if job else None,"total_frames":job.total_frames if job else None},"timestamp":int(time.time()*1000)}) + "\n")
        except Exception as log_err:
            pass  # Don't fail API call if logging fails
        # #endregion
        if not job:
            raise HTTPException(
                http_status.HTTP_404_NOT_FOUND,
                detail=f"Training job {job_id} not found"
            )

        # Calculate progress percentage
        progress_percent = 0.0
        if job.total_frames > 0:
            progress_percent = (job.processed_frames / job.total_frames) * 100

        # Estimate completion time
        estimated_completion = None
        if job.status == JobStatus.PROCESSING and job.started_at and job.processed_frames > 0:
            elapsed = (datetime.utcnow() - job.started_at).total_seconds()
            frames_per_second = job.processed_frames / elapsed if elapsed > 0 else 0
            if frames_per_second > 0:
                remaining_frames = job.total_frames - job.processed_frames
                remaining_seconds = remaining_frames / frames_per_second
                estimated_completion = datetime.utcnow() + timedelta(seconds=remaining_seconds)

        return TrainingStatusResponse(
            job_id=job.id,
            status=job.status,
            total_frames=job.total_frames,
            processed_frames=job.processed_frames,
            failed_frames=job.failed_frames,
            progress_percent=round(progress_percent, 2),
            started_at=job.started_at,
            estimated_completion=estimated_completion
        )

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error getting training status: {str(e)}", exc_info=True)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/{job_id}/rollback", response_model=TrainingRollbackResponse)
def rollback_training(
    job_id: int,
    db: Session = Depends(get_db),
    client_session_id: str = Depends(get_client_session_id)
):
    """
    Rollback a training job: delete embeddings from Qdrant and reset frame status.
    Can rollback completed jobs. Already rolled back jobs are skipped.
    """
    try:
        # Get training job
        job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
        if not job:
            raise HTTPException(
                http_status.HTTP_404_NOT_FOUND,
                detail=f"Training job {job_id} not found"
            )

        # Validate job status
        if job.status == JobStatus.ROLLED_BACK:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                detail=f"Job {job_id} is already rolled back"
            )
        
        if job.status not in [JobStatus.COMPLETED, JobStatus.FAILED]:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                detail=f"Can only rollback completed or failed jobs. Current status: {job.status}"
            )

        app_logger.info(f"Starting rollback for training job {job_id}")

        # Generate request ID for this operation
        request_id = get_request_id()

        # Trigger rollback task with client session context
        task = rollback_training_task.apply_async(
            args=[job_id],
            kwargs={
                "client_session_id": client_session_id,
                "request_id": request_id
            }
        )

        # Log rollback start
        log_entry = ProcessingLog(
            entity_type=EntityType.TRAINING_JOB,
            entity_id=job_id,
            action="rollback_started",
            status=LogStatus.SUCCESS,
            message=f"Rollback initiated for job {job_id}",
            extra_metadata={"video_id": job.video_id, "celery_task_id": task.id}
        )
        db.add(log_entry)
        db.commit()

        return TrainingRollbackResponse(
            rollback_job_id=job_id,
            message=f"Rollback started for job {job_id}"
        )

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error rolling back training: {str(e)}", exc_info=True)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/{job_id}/resume", status_code=http_status.HTTP_200_OK)
def resume_training(
    job_id: int,
    db: Session = Depends(get_db),
    client_session_id: str = Depends(get_client_session_id)
):
    """
    Resume a paused training job.

    Only paused jobs can be resumed. The job will continue from where it left off
    (only unprocessed frames will be trained).

    Args:
        job_id: Training job ID to resume
        db: Database session

    Returns:
        Success message with new task ID
    """
    try:
        # Get training job
        job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
        if not job:
            raise HTTPException(
                http_status.HTTP_404_NOT_FOUND,
                detail=f"Training job {job_id} not found"
            )

        # Validate job status
        if job.status != JobStatus.PAUSED:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                detail=f"Can only resume paused jobs. Current status: {job.status}"
            )

        app_logger.info(f"Resuming training job {job_id}")

        # Reset status to pending
        job.status = JobStatus.PENDING
        job.error_message = None
        db.commit()

        # Generate request ID for this operation
        request_id = get_request_id()

        # Trigger new Celery task with client session context (will process only remaining frames)
        task = train_frames_task.apply_async(
            args=[job_id],
            kwargs={
                "client_session_id": client_session_id,
                "request_id": request_id
            }
        )
        job.celery_task_id = task.id
        db.commit()

        # Log resume
        log_entry = ProcessingLog(
            entity_type=EntityType.TRAINING_JOB,
            entity_id=job_id,
            action="training_resumed",
            status=LogStatus.SUCCESS,
            message=f"Training job resumed after pause",
            extra_metadata={"video_id": job.video_id, "celery_task_id": task.id}
        )
        db.add(log_entry)
        db.commit()

        return {
            "job_id": job_id,
            "task_id": task.id,
            "message": f"Training job {job_id} resumed"
        }

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error resuming training: {str(e)}", exc_info=True)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.delete("/{job_id}", status_code=http_status.HTTP_200_OK)
def delete_training_job(job_id: int, db: Session = Depends(get_db)):
    """
    Delete a training job.

    Only completed, failed, or paused jobs can be deleted.
    Processing jobs must be paused first.

    Args:
        job_id: Training job ID to delete
        db: Database session

    Returns:
        Success message
    """
    try:
        # Get training job
        job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
        if not job:
            raise HTTPException(
                http_status.HTTP_404_NOT_FOUND,
                detail=f"Training job {job_id} not found"
            )

        # Validate job status - can't delete processing jobs
        if job.status == JobStatus.PROCESSING:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete job while processing. Please pause it first."
            )

        app_logger.info(f"Deleting training job {job_id}")

        # Log deletion
        log_entry = ProcessingLog(
            entity_type=EntityType.TRAINING_JOB,
            entity_id=job_id,
            action="training_job_deleted",
            status=LogStatus.SUCCESS,
            message=f"Training job {job_id} deleted",
            extra_metadata={
                "video_id": job.video_id,
                "status": job.status.value,
                "total_frames": job.total_frames,
                "processed_frames": job.processed_frames,
                "failed_frames": job.failed_frames
            }
        )
        db.add(log_entry)

        # Delete job from database
        db.delete(job)
        db.commit()

        return {
            "job_id": job_id,
            "message": f"Training job {job_id} deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error deleting training job: {str(e)}", exc_info=True)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/{job_id}/pause", status_code=http_status.HTTP_200_OK)
def pause_training_job(job_id: int, db: Session = Depends(get_db)):
    """
    Pause a running training job.

    Args:
        job_id: Training job ID to pause
        db: Database session

    Returns:
        Success message
    """
    try:
        # Get training job
        job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
        if not job:
            raise HTTPException(
                http_status.HTTP_404_NOT_FOUND,
                detail=f"Training job {job_id} not found"
            )

        # Validate job status
        if job.status != JobStatus.PROCESSING:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                detail=f"Can only pause processing jobs. Current status: {job.status}"
            )

        # Pause job (the task checks for this status)
        job.status = JobStatus.PAUSED
        db.commit()

        app_logger.info(f"Training job {job_id} paused")

        # Log pause
        log_entry = ProcessingLog(
            entity_type=EntityType.TRAINING_JOB,
            entity_id=job_id,
            action="training_job_paused",
            status=LogStatus.SUCCESS,
            message=f"Training job manually paused",
            extra_metadata={"video_id": job.video_id}
        )
        db.add(log_entry)
        db.commit()

        return {
            "job_id": job_id,
            "message": f"Training job {job_id} paused successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error pausing training job: {str(e)}", exc_info=True)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/{job_id}/rollback-status", status_code=http_status.HTTP_200_OK)
def get_rollback_status(job_id: int, db: Session = Depends(get_db)):
    """
    Get rollback status for a training job.
    Returns count of frames still in trained status vs selected.
    """
    try:
        job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
        if not job:
            raise HTTPException(
                http_status.HTTP_404_NOT_FOUND,
                detail=f"Training job {job_id} not found"
            )
        
        # Count frames still linked to this job
        trained_count = db.query(ExtractedFrame).filter(
            and_(
                ExtractedFrame.training_job_id == job_id,
                ExtractedFrame.status == FrameStatus.TRAINED
            )
        ).count()
        
        selected_count = db.query(ExtractedFrame).filter(
            and_(
                ExtractedFrame.training_job_id == job_id,
                ExtractedFrame.status == FrameStatus.SELECTED
            )
        ).count()
        
        return {
            "job_id": job_id,
            "job_status": job.status,
            "rolled_back_at": job.rolled_back_at,
            "frames_still_trained": trained_count,
            "frames_reset_to_selected": selected_count,
            "is_rollback_complete": trained_count == 0 and job.status == JobStatus.ROLLED_BACK
        }
    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error getting rollback status: {str(e)}")
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )
