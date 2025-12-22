"""
Video upload and extraction API endpoints
"""
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
import os
import shutil
import json
import time
from pathlib import Path

from app.database import get_db
from app.models import (
    VideoBatch, ExtractedFrame, FrameEmbedding, TrainingJob,
    VideoStatus, FrameStatus,
    ProcessingLog, EntityType, LogStatus
)
from app.schemas import (
    VideoUploadResponse,
    VideoDuplicateResponse,
    ExtractionTriggerResponse,
    VideoDeletionResponse,
    VideoListResponse,
    VideoDetailResponse
)
from app.utils.hash import calculate_md5_hash
from app.utils.logger import app_logger
from app.config import settings

# #region agent log
DEBUG_LOG_PATH = os.getenv("DEBUG_LOG_PATH", "/app/project/logs/debug.log")
# #endregion

router = APIRouter(prefix="/api/video", tags=["video"])


@router.post("/upload", response_model=VideoUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_video(
    video: UploadFile = File(..., description="Video file to upload"),
    asset_name: str = Form(..., description="Asset name"),
    category: str = Form(..., description="Asset category"),
    model_number: Optional[str] = Form(None, description="Model number"),
    manufacturer: Optional[str] = Form(None, description="Manufacturer name"),
    ai_attributes: Optional[str] = Form(None, description="AI-specific attributes"),
    latitude: Optional[float] = Form(None, description="Latitude coordinate"),
    longitude: Optional[float] = Form(None, description="Longitude coordinate"),
    fps: int = Form(2, ge=1, le=10, description="Frames per second for extraction"),
    db: Session = Depends(get_db)
):
    """
    Upload video with metadata and detect duplicates via MD5 hash.

    Steps:
    1. Validate file type
    2. Calculate MD5 hash
    3. Check for duplicates
    4. Save file temporarily
    5. Create database record
    6. Return video_id
    """
    try:
        # Validate file extension
        file_extension = video.filename.split('.')[-1].lower()
        if file_extension not in settings.ALLOWED_VIDEO_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type. Allowed: {', '.join(settings.ALLOWED_VIDEO_EXTENSIONS)}"
            )

        # Create temp directory if not exists
        os.makedirs(settings.TEMP_VIDEO_DIR, exist_ok=True)

        # Save uploaded file temporarily
        temp_filename = f"temp_{video.filename}"
        temp_path = os.path.join(settings.TEMP_VIDEO_DIR, temp_filename)

        # Save file in chunks
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(video.file, buffer)

        app_logger.info(f"Video saved temporarily: {temp_path}")

        # Calculate MD5 hash
        video_hash = calculate_md5_hash(temp_path)
        app_logger.info(f"Video hash calculated: {video_hash}")

        # Check for duplicate
        existing_video = db.query(VideoBatch).filter(VideoBatch.video_hash == video_hash).first()
        if existing_video:
            # Delete temp file
            os.remove(temp_path)

            app_logger.warning(f"Duplicate video detected: {video_hash} (existing video_id: {existing_video.id})")

            # Log duplicate detection
            log_entry = ProcessingLog(
                entity_type=EntityType.VIDEO,
                entity_id=existing_video.id,
                action="duplicate_upload_attempt",
                status=LogStatus.WARNING,
                message=f"Duplicate upload attempt: {video.filename}",
                extra_metadata={"original_filename": video.filename, "hash": video_hash}
            )
            db.add(log_entry)
            db.commit()

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "duplicate",
                    "existing_video_id": existing_video.id,
                    "message": f"Video already exists with ID {existing_video.id}"
                }
            )

        # Create database record
        video_batch = VideoBatch(
            video_hash=video_hash,
            filename=video.filename,
            asset_name=asset_name,
            model_number=model_number,
            category=category,
            manufacturer=manufacturer,
            ai_attributes=ai_attributes,
            latitude=latitude,
            longitude=longitude,
            fps=fps,
            status=VideoStatus.UPLOADED
        )
        db.add(video_batch)
        db.commit()
        db.refresh(video_batch)

        # Rename temp file with video_id
        final_filename = f"video_{video_batch.id}_{video.filename}"
        final_path = os.path.join(settings.TEMP_VIDEO_DIR, final_filename)
        os.rename(temp_path, final_path)

        app_logger.info(f"Video uploaded successfully: video_id={video_batch.id}, filename={final_filename}")

        # Log successful upload
        log_entry = ProcessingLog(
            entity_type=EntityType.VIDEO,
            entity_id=video_batch.id,
            action="video_uploaded",
            status=LogStatus.SUCCESS,
            message=f"Video uploaded: {video.filename}",
            extra_metadata={
                "filename": video.filename,
                "hash": video_hash,
                "asset_name": asset_name,
                "category": category,
                "fps": fps
            }
        )
        db.add(log_entry)
        db.commit()

        return VideoUploadResponse(
            video_id=video_batch.id,
            status=VideoStatus.UPLOADED,
            message="Video uploaded successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error uploading video: {str(e)}")
        # Clean up temp file if exists
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload video: {str(e)}"
        )


@router.post("/{video_id}/extract", response_model=ExtractionTriggerResponse)
async def trigger_extraction(
    video_id: int,
    db: Session = Depends(get_db)
):
    """
    Trigger frame extraction Celery task for uploaded video.

    Steps:
    1. Verify video exists and is in 'uploaded' status
    2. Trigger Celery task for extraction
    3. Update video status to 'extracting'
    4. Return task_id
    """
    try:
        # Get video record
        video = db.query(VideoBatch).filter(VideoBatch.id == video_id).first()
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Video with ID {video_id} not found"
            )

        # Check video status
        if video.status != VideoStatus.UPLOADED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Video is not in 'uploaded' status. Current status: {video.status}"
            )

        # Import Celery task
        from app.tasks.extraction import extract_frames_task

        # Trigger Celery task - .delay() automatically queues for concurrent execution
        task = extract_frames_task.delay(video_id)
        
        # Multiple videos extract करने पर, अगर multiple workers हैं तो concurrent होगा
        # Single worker होने पर sequential होगा (expected behavior)

        # Update video status
        video.status = VideoStatus.EXTRACTING
        # #region agent log
        try:
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"J","location":"video.py:212","message":"BEFORE API commit - video status extracting","data":{"video_id":video_id,"status_before":None,"status_after":video.status.value},"timestamp":int(time.time()*1000)}) + "\n")
        except:
            pass
        # #endregion
        db.flush()  # Ensure changes are visible before commit
        db.commit()
        # #region agent log
        db.refresh(video)
        # Verify by querying database directly
        video_verify = db.query(VideoBatch).filter(VideoBatch.id == video_id).first()
        try:
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"J","location":"video.py:217","message":"AFTER API commit and refresh - video status","data":{"video_id":video_id,"status_after_refresh":video.status.value,"status_from_query":video_verify.status.value if video_verify else None},"timestamp":int(time.time()*1000)}) + "\n")
        except:
            pass
        # #endregion

        app_logger.info(f"Frame extraction triggered for video_id={video_id}, task_id={task.id}")

        # Log extraction trigger
        log_entry = ProcessingLog(
            entity_type=EntityType.VIDEO,
            entity_id=video_id,
            action="extraction_triggered",
            status=LogStatus.SUCCESS,
            message=f"Frame extraction started",
            extra_metadata={"task_id": task.id, "fps": video.fps}
        )
        db.add(log_entry)
        db.commit()

        return ExtractionTriggerResponse(
            task_id=task.id,
            status="extracting",
            message="Extraction started"
        )

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error triggering extraction: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger extraction: {str(e)}"
        )


@router.get("/list", response_model=VideoListResponse)
async def list_videos(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    category_filter: Optional[str] = Query(None, description="Filter by category"),
    db: Session = Depends(get_db)
):
    """
    List all videos with pagination and filtering.

    Args:
        page: Page number
        page_size: Items per page
        status_filter: Filter by video status
        category_filter: Filter by category
        db: Database session

    Returns:
        Paginated list of videos with metadata
    """
    try:
        # Build query
        query = db.query(VideoBatch)

        # Apply filters
        if status_filter:
            try:
                status_enum = VideoStatus(status_filter)
                query = query.filter(VideoBatch.status == status_enum)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status: {status_filter}"
                )

        if category_filter:
            query = query.filter(VideoBatch.category.ilike(f"%{category_filter}%"))

        # Get total count
        total = query.count()

        # Apply pagination
        offset = (page - 1) * page_size
        videos = query.order_by(VideoBatch.created_at.desc()).offset(offset).limit(page_size).all()

        # Build response
        from app.schemas import VideoItem
        video_items = [
            VideoItem(
                id=video.id,
                filename=video.filename,
                asset_name=video.asset_name,
                category=video.category,
                status=video.status,
                total_frames=video.total_frames,
                fps=video.fps,
                model_number=video.model_number,
                manufacturer=video.manufacturer,
                created_at=video.created_at,
                updated_at=video.updated_at
            )
            for video in videos
        ]

        return VideoListResponse(
            total=total,
            page=page,
            page_size=page_size,
            videos=video_items
        )

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error listing videos: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list videos: {str(e)}"
        )


@router.get("/{video_id}", response_model=VideoDetailResponse)
async def get_video_detail(video_id: int, db: Session = Depends(get_db)):
    """
    Get detailed information about a specific video.

    Args:
        video_id: Video ID
        db: Database session

    Returns:
        Detailed video information with frame counts by status
    """
    try:
        # Get video - use fresh query with explicit refresh
        video = db.query(VideoBatch).filter(VideoBatch.id == video_id).first()
        if video:
            db.refresh(video)  # Ensure we have latest state
        # #region agent log
        try:
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"K","location":"video.py:356","message":"API read video status","data":{"video_id":video_id,"status_in_db":video.status.value if video else None},"timestamp":int(time.time()*1000)}) + "\n")
        except Exception as log_err:
            pass  # Don't fail API call if logging fails
        # #endregion
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Video {video_id} not found"
            )

        # Get frame counts by status
        from sqlalchemy import func, case
        frame_stats = db.query(
            func.sum(case((ExtractedFrame.status == FrameStatus.EXTRACTED, 1), else_=0)).label('extracted'),
            func.sum(case((ExtractedFrame.status == FrameStatus.SELECTED, 1), else_=0)).label('selected'),
            func.sum(case((ExtractedFrame.status == FrameStatus.TRAINED, 1), else_=0)).label('trained'),
            func.sum(case((ExtractedFrame.status == FrameStatus.DELETED, 1), else_=0)).label('deleted')
        ).filter(
            ExtractedFrame.video_id == video_id,
            ExtractedFrame.deleted_at.is_(None)
        ).first()

        # Get training job count
        training_jobs_count = db.query(TrainingJob).filter(TrainingJob.video_id == video_id).count()

        return VideoDetailResponse(
            id=video.id,
            filename=video.filename,
            asset_name=video.asset_name,
            category=video.category,
            status=video.status,
            total_frames=video.total_frames,
            fps=video.fps,
            model_number=video.model_number,
            manufacturer=video.manufacturer,
            ai_attributes=video.ai_attributes,
            latitude=video.latitude,
            longitude=video.longitude,
            frames_extracted=frame_stats.extracted or 0,
            frames_selected=frame_stats.selected or 0,
            frames_trained=frame_stats.trained or 0,
            frames_deleted=frame_stats.deleted or 0,
            training_jobs_count=training_jobs_count,
            created_at=video.created_at,
            updated_at=video.updated_at
        )

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error getting video detail: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get video detail: {str(e)}"
        )


@router.patch("/{video_id}", status_code=status.HTTP_200_OK)
async def update_video_metadata(
    video_id: int,
    asset_name: Optional[str] = None,
    category: Optional[str] = None,
    model_number: Optional[str] = None,
    manufacturer: Optional[str] = None,
    ai_attributes: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    db: Session = Depends(get_db)
):
    """
    Update video metadata.

    Args:
        video_id: Video ID
        asset_name: New asset name
        category: New category
        model_number: New model number
        manufacturer: New manufacturer
        ai_attributes: New AI attributes
        latitude: New latitude
        longitude: New longitude
        db: Database session

    Returns:
        Success message
    """
    try:
        # Get video
        video = db.query(VideoBatch).filter(VideoBatch.id == video_id).first()
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Video {video_id} not found"
            )

        # Update fields
        if asset_name is not None:
            video.asset_name = asset_name
        if category is not None:
            video.category = category
        if model_number is not None:
            video.model_number = model_number
        if manufacturer is not None:
            video.manufacturer = manufacturer
        if ai_attributes is not None:
            video.ai_attributes = ai_attributes
        if latitude is not None:
            video.latitude = latitude
        if longitude is not None:
            video.longitude = longitude

        db.commit()
        db.refresh(video)

        app_logger.info(f"Video {video_id} metadata updated")

        # Log update
        log_entry = ProcessingLog(
            entity_type=EntityType.VIDEO,
            entity_id=video_id,
            action="video_updated",
            status=LogStatus.SUCCESS,
            message="Video metadata updated",
            extra_metadata={
                "asset_name": asset_name,
                "category": category
            }
        )
        db.add(log_entry)
        db.commit()

        return {
            "message": "Video metadata updated successfully",
            "video_id": video_id
        }

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error updating video: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update video: {str(e)}"
        )


@router.delete("/{video_id}", response_model=VideoDeletionResponse)
async def delete_video(video_id: int, db: Session = Depends(get_db)):
    """
    Delete video and all associated data (CASCADE).

    Deletes:
    - All frames from database (with embeddings via CASCADE)
    - All S3 files (frames and thumbnails)
    - All Qdrant vector points
    - All training jobs
    - Video record itself

    Args:
        video_id: Video ID to delete
        db: Database session

    Returns:
        VideoDeletionResponse with deletion summary
    """
    try:
        from app.services.s3_service import s3_service
        from app.services.qdrant_service import qdrant_service

        # Get video
        video = db.query(VideoBatch).filter(VideoBatch.id == video_id).first()
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Video {video_id} not found"
            )

        app_logger.info(f"Starting deletion of video {video_id}")

        # Get all frames (including soft-deleted)
        frames = db.query(ExtractedFrame).filter(ExtractedFrame.video_id == video_id).all()
        frames_count = len(frames)

        # Collect S3 keys and Qdrant point IDs
        s3_keys_to_delete = []
        qdrant_point_ids = []

        for frame in frames:
            if frame.s3_path:
                s3_keys_to_delete.append(frame.s3_path)
            if frame.thumbnail_s3_path:
                s3_keys_to_delete.append(frame.thumbnail_s3_path)
            if frame.qdrant_point_id:
                qdrant_point_ids.append(frame.qdrant_point_id)

        # Delete from S3
        s3_deleted = 0
        if s3_keys_to_delete:
            # Delete in batches of 1000 (S3 limit)
            for i in range(0, len(s3_keys_to_delete), 1000):
                batch = s3_keys_to_delete[i:i+1000]
                if s3_service.delete_files_batch(batch):
                    s3_deleted += len(batch)

        app_logger.info(f"Deleted {s3_deleted}/{len(s3_keys_to_delete)} S3 files for video {video_id}")

        # Delete from Qdrant
        qdrant_deleted = 0
        if qdrant_point_ids:
            result = qdrant_service.delete_batch(qdrant_point_ids)
            qdrant_deleted = result["success"]

        app_logger.info(f"Deleted {qdrant_deleted}/{len(qdrant_point_ids)} Qdrant points for video {video_id}")

        # Delete from database (CASCADE will handle frames, embeddings, training_jobs)
        db.delete(video)
        db.commit()

        # Log deletion
        log_entry = ProcessingLog(
            entity_type=EntityType.VIDEO,
            entity_id=video_id,
            action="video_deleted",
            status=LogStatus.SUCCESS,
            message=f"Video deleted with {frames_count} frames",
            extra_metadata={
                "frames_count": frames_count,
                "s3_files_deleted": s3_deleted,
                "qdrant_points_deleted": qdrant_deleted
            }
        )
        db.add(log_entry)
        db.commit()

        app_logger.info(f"Video {video_id} deleted successfully")

        return VideoDeletionResponse(
            video_id=video_id,
            frames_deleted=frames_count,
            s3_files_deleted=s3_deleted,
            qdrant_points_deleted=qdrant_deleted,
            message=f"Video and {frames_count} frames deleted successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error deleting video: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete video: {str(e)}"
        )
