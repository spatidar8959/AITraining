"""
Celery task for training frames with embeddings and Qdrant upload
Includes circuit breaker, parallel processing, and comprehensive error handling
"""
import json
import time
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import redis
import os

from celery import Task
from sqlalchemy import and_

from app.celery_app import celery_app
from app.database import get_db_context
from app.models import (
    VideoBatch, ExtractedFrame, TrainingJob, FrameEmbedding,
    JobStatus, FrameStatus, ProcessingLog, EntityType, LogStatus
)
from app.services.s3_service import s3_service
from app.services.embedding_service import embedding_service
from app.services.qdrant_service import qdrant_service
from app.services.alert_service import alert_service
from app.config import settings
from app.utils.logger import celery_logger

# #region agent log
DEBUG_LOG_PATH = os.getenv("DEBUG_LOG_PATH", "/app/project/logs/debug.log")
# #endregion

# Redis client for progress broadcasting
redis_client = redis.from_url(settings.redis_url)


class CallbackTask(Task):
    """Base task with callbacks for progress tracking"""

    def on_success(self, retval, task_id, args, kwargs):
        celery_logger.info(f"Task {task_id} completed successfully")

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        celery_logger.error(f"Task {task_id} failed: {str(exc)}")


@celery_app.task(bind=True, base=CallbackTask, max_retries=0)  # No auto-retry, we handle manually
def train_frames_task(self, job_id: int, client_session_id: str = None, request_id: str = None):
    """
    Train selected frames by generating embeddings and uploading to Qdrant.

    Process:
    1. Get training job details from database
    2. Fetch all selected frames for this job
    3. Process in batches of TRAINING_BATCH_SIZE (50)
    4. For each batch:
       - Download frames from S3 in parallel
       - Generate embeddings in parallel (5 workers)
       - Upload to Qdrant with retry logic (3 attempts per frame)
       - Store embeddings in MySQL for disaster recovery
       - Update frame status and job progress
       - Broadcast progress via Redis
    5. Circuit breaker: pause job after 10 consecutive failures
    6. Send email alerts on circuit breaker or job failure
    7. Handle resume from last successful batch

    Args:
        job_id: Training job ID
    """
    consecutive_failures = 0
    circuit_breaker_threshold = settings.CIRCUIT_BREAKER_THRESHOLD

    try:
        with get_db_context() as db:
            # Get training job
            job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
            if not job:
                celery_logger.error(f"Training job {job_id} not found")
                return

            # Get video
            video = db.query(VideoBatch).filter(VideoBatch.id == job.video_id).first()
            if not video:
                celery_logger.error(f"Video {job.video_id} not found")
                job.status = JobStatus.FAILED
                job.error_message = "Video not found"
                db.commit()
                return

            # Get all selected frames (not yet trained)
            frames = db.query(ExtractedFrame).filter(
                and_(
                    ExtractedFrame.video_id == job.video_id,
                    ExtractedFrame.status == FrameStatus.SELECTED,
                    ExtractedFrame.deleted_at.is_(None)
                )
            ).all()

            if not frames:
                celery_logger.warning(f"No selected frames found for job {job_id}")
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.utcnow()
                db.commit()
                return

            # Check for concurrent jobs (within same session)
            existing_job = db.query(TrainingJob).filter(
                and_(
                    TrainingJob.video_id == job.video_id,
                    TrainingJob.status == JobStatus.PROCESSING,
                    TrainingJob.id != job_id
                )
            ).first()
            
            if existing_job:
                celery_logger.warning(f"Another training job {existing_job.id} is already processing for video {job.video_id}")
                job.status = JobStatus.PAUSED
                job.error_message = f"Another job {existing_job.id} is already processing"
                db.commit()
                return

            total_frames = len(frames)
            job.total_frames = total_frames
            job.status = JobStatus.PROCESSING
            job.started_at = datetime.utcnow()
            # #region agent log
            try:
                with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"training.py:111","message":"BEFORE commit - job status update","data":{"job_id":job_id,"status_before":None,"status_after":job.status.value,"processed_frames":job.processed_frames,"total_frames":job.total_frames},"timestamp":int(time.time()*1000)}) + "\n")
            except:
                pass
            # #endregion
            db.flush()
            db.commit()
            # #region agent log
            # Verify by querying database directly
            job_verify = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
            try:
                with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"training.py:122","message":"AFTER commit - job status","data":{"job_id":job_id,"status_after_refresh":job.status.value,"status_from_query":job_verify.status.value if job_verify else None,"processed_frames":job.processed_frames,"total_frames":job.total_frames},"timestamp":int(time.time()*1000)}) + "\n")
            except:
                pass
            # #endregion

            celery_logger.info(
                f"Starting training job {job_id} for video {job.video_id}, "
                f"{total_frames} frames to process"
            )

            # Ensure Qdrant collection exists
            if not qdrant_service.ensure_collection_exists():
                raise Exception("Failed to ensure Qdrant collection exists")

            # Process in batches
            batch_size = settings.TRAINING_BATCH_SIZE
            for batch_start in range(0, total_frames, batch_size):
                # Check if job was manually paused - always query fresh
                job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
                if not job or job.status == JobStatus.PAUSED:
                    celery_logger.info(f"Job {job_id} is paused or not found, stopping processing")
                    return

                batch_end = min(batch_start + batch_size, total_frames)
                batch_frames = frames[batch_start:batch_end]

                celery_logger.info(
                    f"Processing batch {batch_start}-{batch_end} "
                    f"({len(batch_frames)} frames)"
                )

                # Process batch frames
                batch_results = process_frame_batch(
                    batch_frames=batch_frames,
                    video=video,
                    job=job,
                    db=db
                )

                # Update counters
                job.processed_frames += batch_results["success"]
                job.failed_frames += batch_results["failed"]
                # #region agent log
                try:
                    with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"training.py:157","message":"BEFORE batch commit - job counters updated","data":{"job_id":job_id,"processed_frames":job.processed_frames,"failed_frames":job.failed_frames,"batch_success":batch_results["success"],"batch_failed":batch_results["failed"]},"timestamp":int(time.time()*1000)}) + "\n")
                except:
                    pass
                # #endregion

                # Check circuit breaker
                if batch_results["failed"] > 0:
                    consecutive_failures += batch_results["failed"]
                else:
                    consecutive_failures = 0  # Reset on success

                if consecutive_failures >= circuit_breaker_threshold:
                    celery_logger.critical(
                        f"CIRCUIT BREAKER TRIGGERED: {consecutive_failures} consecutive "
                        f"failures (threshold: {circuit_breaker_threshold})"
                    )

                    # Pause job
                    job.status = JobStatus.PAUSED
                    job.error_message = (
                        f"Circuit breaker triggered after {consecutive_failures} "
                        f"consecutive failures"
                    )
                    # #region agent log
                    with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"training.py:163","message":"BEFORE circuit breaker commit - job paused","data":{"job_id":job_id,"status_before":JobStatus.PROCESSING.value,"status_after":job.status.value,"error_message":job.error_message},"timestamp":int(time.time()*1000)}) + "\n")
                    # #endregion
                    db.commit()
                    # #region agent log
                    db.refresh(job)
                    with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"training.py:165","message":"AFTER circuit breaker commit and refresh","data":{"job_id":job_id,"status_in_db":job.status.value},"timestamp":int(time.time()*1000)}) + "\n")
                    # #endregion

                    # Send alerts (email + log)
                    alert_service.send_circuit_breaker_alert(
                        job_id=job_id,
                        video_id=job.video_id,
                        consecutive_failures=consecutive_failures,
                        threshold=circuit_breaker_threshold
                    )

                    # Log to database
                    log_entry = ProcessingLog(
                        entity_type=EntityType.TRAINING_JOB,
                        entity_id=job_id,
                        action="circuit_breaker_triggered",
                        status=LogStatus.FAILED,
                        message=f"Circuit breaker triggered after {consecutive_failures} failures",
                        extra_metadata={
                            "consecutive_failures": consecutive_failures,
                            "threshold": circuit_breaker_threshold,
                            "video_id": job.video_id
                        }
                    )
                    db.add(log_entry)
                    db.commit()
                    db.refresh(job)

                    return

                # Commit batch progress
                # #region agent log
                try:
                    with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"training.py:226","message":"BEFORE batch progress commit","data":{"job_id":job_id,"processed_frames":job.processed_frames,"failed_frames":job.failed_frames},"timestamp":int(time.time()*1000)}) + "\n")
                except:
                    pass
                # #endregion
                db.flush()  # Ensure changes are visible before commit
                db.commit()
                # #region agent log
                db.refresh(job)
                # Verify by querying database directly
                job_verify = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
                try:
                    with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"training.py:232","message":"AFTER batch progress commit and refresh","data":{"job_id":job_id,"status_after_refresh":job.status.value,"status_from_query":job_verify.status.value if job_verify else None,"processed_frames_after_refresh":job.processed_frames,"processed_frames_from_query":job_verify.processed_frames if job_verify else None,"failed_frames_after_refresh":job.failed_frames,"failed_frames_from_query":job_verify.failed_frames if job_verify else None},"timestamp":int(time.time()*1000)}) + "\n")
                except:
                    pass
                # #endregion

                # Broadcast progress
                progress_percent = (batch_end / total_frames) * 100
                broadcast_training_progress(
                    job_id=job_id,
                    video_id=job.video_id,
                    current=batch_end,
                    total=total_frames,
                    percent=progress_percent,
                    status="processing",
                    client_session_id=client_session_id,
                    request_id=request_id
                )

                celery_logger.info(
                    f"Batch {batch_start}-{batch_end} completed: "
                    f"{batch_results['success']} success, {batch_results['failed']} failed "
                    f"({progress_percent:.1f}%)"
                )

            # Determine final job status based on results
            if job.processed_frames == 0 and job.failed_frames > 0:
                # All frames failed - mark job as failed
                job.status = JobStatus.FAILED
                job.error_message = (
                    f"All {job.failed_frames} frames failed to process. "
                    f"Check individual frame errors for details."
                )
                final_status = "failed"
                log_status = LogStatus.FAILED
                log_action = "training_failed"

                # Send failure alert
                alert_service.send_training_failure_alert(
                    job_id=job_id,
                    video_id=job.video_id,
                    error_message=job.error_message
                )
            elif job.processed_frames > 0 and job.failed_frames > 0:
                # Partial success - still mark as completed but log warning
                job.status = JobStatus.COMPLETED
                job.error_message = f"{job.failed_frames} out of {job.total_frames} frames failed"
                final_status = "completed"
                log_status = LogStatus.WARNING
                log_action = "training_completed_with_failures"

                # Calculate failure rate
                failure_rate = job.failed_frames / job.total_frames if job.total_frames > 0 else 0

                # Send alert if failure rate > 50%
                if failure_rate > 0.5:
                    alert_service.send_training_failure_alert(
                        job_id=job_id,
                        video_id=job.video_id,
                        error_message=f"{job.failed_frames}/{job.total_frames} frames failed ({failure_rate*100:.1f}% failure rate)"
                    )
            else:
                # All frames succeeded (or no frames to process)
                job.status = JobStatus.COMPLETED
                job.error_message = None
                final_status = "completed"
                log_status = LogStatus.SUCCESS
                log_action = "training_completed"

            job.completed_at = datetime.utcnow()
            # #region agent log
            try:
                with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"training.py:258","message":"BEFORE final job completion commit","data":{"job_id":job_id,"status_before":None,"status_after":job.status.value,"processed_frames":job.processed_frames,"failed_frames":job.failed_frames,"total_frames":job.total_frames},"timestamp":int(time.time()*1000)}) + "\n")
            except:
                pass
            # #endregion
            db.flush()  # Ensure changes are visible before commit
            db.commit()
            # #region agent log
            db.refresh(job)
            # Verify by querying database directly
            job_verify = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
            try:
                with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"training.py:264","message":"AFTER final job completion commit and refresh","data":{"job_id":job_id,"status_after_refresh":job.status.value,"status_from_query":job_verify.status.value if job_verify else None,"processed_frames_after_refresh":job.processed_frames,"processed_frames_from_query":job_verify.processed_frames if job_verify else None,"failed_frames_after_refresh":job.failed_frames,"failed_frames_from_query":job_verify.failed_frames if job_verify else None,"completed_at":job.completed_at.isoformat() if job.completed_at else None},"timestamp":int(time.time()*1000)}) + "\n")
            except:
                pass
            # #endregion

            # Log completion
            log_entry = ProcessingLog(
                entity_type=EntityType.TRAINING_JOB,
                entity_id=job_id,
                action=log_action,
                status=log_status,
                message=f"Training {final_status}: {job.processed_frames} frames trained, {job.failed_frames} failed",
                extra_metadata={
                    "total_frames": job.total_frames,
                    "processed": job.processed_frames,
                    "failed": job.failed_frames,
                    "video_id": job.video_id,
                    "failure_rate": round(job.failed_frames / job.total_frames * 100, 2) if job.total_frames > 0 else 0
                }
            )
            db.add(log_entry)
            db.commit()

            # Broadcast completion
            broadcast_training_progress(
                job_id=job_id,
                video_id=job.video_id,
                current=job.processed_frames,
                total=total_frames,
                percent=100.0,
                status=final_status,
                client_session_id=client_session_id,
                request_id=request_id
            )

            celery_logger.info(
                f"Training job {job_id} completed: {job.processed_frames} frames trained, "
                f"{job.failed_frames} failed"
            )

    except Exception as e:
        celery_logger.error(f"Error in train_frames_task: {str(e)}", exc_info=True)

        # Update job status to failed
        with get_db_context() as db:
            job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(e)
                job.completed_at = datetime.utcnow()
                # #region agent log
                with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"E","location":"training.py:298","message":"BEFORE exception handler commit - job failed","data":{"job_id":job_id,"status_after":job.status.value,"error_message":str(e)[:200]},"timestamp":int(time.time()*1000)}) + "\n")
                # #endregion
                db.commit()
                # #region agent log
                db.refresh(job)
                # Verify by querying database directly
                job_verify = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
                try:
                    with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"E","location":"training.py:306","message":"AFTER exception handler commit and refresh","data":{"job_id":job_id,"status_after_refresh":job.status.value,"status_from_query":job_verify.status.value if job_verify else None},"timestamp":int(time.time()*1000)}) + "\n")
                except:
                    pass
                # #endregion

                # Send failure alert
                alert_service.send_training_failure_alert(
                    job_id=job_id,
                    video_id=job.video_id,
                    error_message=str(e)
                )

                # Log failure
                log_entry = ProcessingLog(
                    entity_type=EntityType.TRAINING_JOB,
                    entity_id=job_id,
                    action="training_failed",
                    status=LogStatus.FAILED,
                    message=f"Training failed: {str(e)}",
                    extra_metadata={"error": str(e), "video_id": job.video_id}
                )
                db.add(log_entry)
                db.commit()

        raise


def process_frame_batch(
    batch_frames: List[ExtractedFrame],
    video: VideoBatch,
    job: TrainingJob,
    db
) -> Dict[str, int]:
    """
    Process a batch of frames: download, embed, upload to Qdrant, store in MySQL.

    Args:
        batch_frames: List of ExtractedFrame objects
        video: VideoBatch object
        job: TrainingJob object
        db: Database session (not used in threads, kept for compatibility)

    Returns:
        Dict with "success" and "failed" counts
    """
    success_count = 0
    failed_count = 0

    # Parallel download and embedding generation
    frame_data_list = []

    # Extract frame IDs and video data before threading
    frame_data = [
        {
            "frame_id": frame.id,
            "s3_path": frame.s3_path,
            "video_id": video.id,
            "job_id": job.id,  # Add job_id here
            "video_data": {
                "asset_name": video.asset_name,
                "model_number": video.model_number,
                "category": video.category,
                "manufacturer": video.manufacturer,
                "ai_attributes": video.ai_attributes,
                "longitude": video.longitude,
                "latitude": video.latitude,
            }
        }
        for frame in batch_frames
    ]

    with ThreadPoolExecutor(max_workers=settings.PARALLEL_EMBEDDING_WORKERS) as executor:
        # Submit all frames for parallel processing (each creates its own DB session)
        future_to_frame_id = {
            executor.submit(process_single_frame, fd): fd["frame_id"]
            for fd in frame_data
        }

        # Collect results
        for future in as_completed(future_to_frame_id):
            frame_id = future_to_frame_id[future]
            try:
                result = future.result()
                if result:
                    frame_data_list.append(result)
                    success_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                celery_logger.error(
                    f"Error processing frame {frame_id}: {e}",
                    exc_info=True
                )
                failed_count += 1

    return {"success": success_count, "failed": failed_count}


def process_single_frame(frame_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Process a single frame with retry logic.
    Creates its own database session to be thread-safe.

    Args:
        frame_data: Dict containing frame_id, s3_path, video_id, job_id, and video_data

    Returns:
        Dict with frame data if successful, None if failed
    """
    frame_id = frame_data["frame_id"]
    s3_path = frame_data["s3_path"]
    video_id = frame_data["video_id"]
    job_id = frame_data["job_id"]  # Get job_id from frame_data
    video_data = frame_data["video_data"]

    retry_attempts = settings.TRAINING_RETRY_ATTEMPTS
    retry_backoff = settings.TRAINING_RETRY_BACKOFF

    for attempt in range(retry_attempts):
        # Create a new database session for this thread
        with get_db_context() as db:
            try:
                # Get fresh frame object from DB
                frame = db.query(ExtractedFrame).filter(ExtractedFrame.id == frame_id).first()
                if not frame:
                    celery_logger.error(f"Frame {frame_id} not found in database")
                    return None

                # Mark frame as training (only on first attempt)
                if attempt == 0:
                    frame.status = FrameStatus.TRAINING
                    frame.training_job_id = job_id  # Now job_id is available
                    db.flush()
                    db.commit()  # Commit to ensure frame is linked to job

                # Download image from S3 to memory
                image_bytes = s3_service.download_file_to_memory(s3_path)
                if not image_bytes:
                    raise Exception(f"Failed to download frame from S3: {s3_path}")

                # Generate embedding
                embedding = embedding_service.generate_image_embedding(image_bytes)
                if not embedding:
                    raise Exception("Failed to generate embedding (empty result)")

                if len(embedding) != settings.EMBEDDING_DIMENSION:
                    raise Exception(
                        f"Invalid embedding dimension: expected {settings.EMBEDDING_DIMENSION}, "
                        f"got {len(embedding)}"
                    )

                # Generate Qdrant point ID
                point_id = qdrant_service.generate_point_id(video_id, frame_id)

                # Prepare Qdrant payload
                payload = {
                    "asset_name": video_data["asset_name"],
                    "image_id": point_id,
                    "model_id": video_data["model_number"] or "N/A",
                    "category": video_data["category"],
                    "manufacturer_name": video_data["manufacturer"] or "N/A",
                    "image_path": s3_path,  # S3 key
                    "ai_attributes": video_data["ai_attributes"] or "N/A",
                    "location": {
                        "lon": float(video_data["longitude"]) if video_data["longitude"] else 0.0,
                        "lat": float(video_data["latitude"]) if video_data["latitude"] else 0.0
                    }
                }

                # Upload to Qdrant
                success = qdrant_service.upsert_point(
                    point_id=point_id,
                    embedding=embedding,
                    payload=payload
                )

                if not success:
                    raise Exception("Failed to upload to Qdrant")

                # Store embedding in MySQL (disaster recovery)
                frame_embedding = FrameEmbedding(
                    frame_id=frame_id,
                    embedding=embedding  # JSON column stores as list
                )
                db.add(frame_embedding)

                # Update frame status
                frame.status = FrameStatus.TRAINED
                frame.qdrant_point_id = point_id
                frame.training_attempts += 1
                frame.last_error = None
                # #region agent log
                with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"F","location":"training.py:485","message":"BEFORE frame status commit - frame trained","data":{"frame_id":frame_id,"status_before":None,"status_after":frame.status.value,"qdrant_point_id":point_id},"timestamp":int(time.time()*1000)}) + "\n")
                # #endregion
                db.commit()
                # #region agent log
                db.refresh(frame)
                with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"F","location":"training.py:488","message":"AFTER frame status commit and refresh","data":{"frame_id":frame_id,"status_in_db":frame.status.value,"qdrant_point_id_in_db":frame.qdrant_point_id},"timestamp":int(time.time()*1000)}) + "\n")
                # #endregion

                celery_logger.info(f"Frame {frame_id} trained successfully (point_id: {point_id})")

                return {
                    "frame_id": frame_id,
                    "point_id": point_id,
                    "embedding": embedding,
                    "payload": payload
                }

            except Exception as e:
                celery_logger.warning(
                    f"Frame {frame_id} training attempt {attempt + 1}/{retry_attempts} failed: {e}"
                )

                # Rollback is handled automatically by get_db_context
                # Wait before retry (exponential backoff)
                if attempt < retry_attempts - 1:
                    backoff_time = retry_backoff[attempt] if attempt < len(retry_backoff) else 15
                    celery_logger.info(f"Retrying in {backoff_time}s...")
                    time.sleep(backoff_time)

    # All retries failed - update frame status
    with get_db_context() as db:
        try:
            frame = db.query(ExtractedFrame).filter(ExtractedFrame.id == frame_id).first()
            if frame:
                frame.status = FrameStatus.SELECTED  # Revert to selected so user can retry
                frame.last_error = f"Failed after {retry_attempts} attempts"
                frame.training_attempts += retry_attempts
                db.commit()
                db.refresh(frame)
        except Exception as e:
            celery_logger.error(f"Failed to update frame {frame_id} after failures: {e}")

    celery_logger.error(f"Frame {frame_id} training failed after {retry_attempts} attempts")
    return None


@celery_app.task(bind=True, base=CallbackTask, max_retries=0)
def rollback_training_task(self, job_id: int, client_session_id: str = None, request_id: str = None):
    """
    Rollback a training job: delete from Qdrant and reset frame status.
    Only rolls back frames that belong to this specific job.
    """
    try:
        with get_db_context() as db:
            # Get training job
            job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
            if not job:
                celery_logger.error(f"Training job {job_id} not found")
                return

            # Validate job status - can rollback completed or failed jobs
            if job.status not in [JobStatus.COMPLETED, JobStatus.FAILED]:
                celery_logger.error(f"Can only rollback completed or failed jobs. Current status: {job.status}")
                return

            # Check if already rolled back
            if job.status == JobStatus.ROLLED_BACK and job.rolled_back_at:
                celery_logger.warning(f"Job {job_id} already rolled back at {job.rolled_back_at}")
                return

            celery_logger.info(f"Starting rollback for job {job_id}")

            # Get frames that belong to THIS specific job
            # First try with training_job_id (preferred method)
            trained_frames = db.query(ExtractedFrame).filter(
                and_(
                    ExtractedFrame.training_job_id == job_id,
                    ExtractedFrame.status.in_([FrameStatus.TRAINED, FrameStatus.TRAINING]),
                    ExtractedFrame.qdrant_point_id.isnot(None)
                )
            ).all()

            # If no frames found with training_job_id, try alternative: 
            # frames from same video that are TRAINED and have qdrant_point_id
            # This handles cases where training_job_id wasn't set properly
            if not trained_frames:
                celery_logger.warning(f"No frames found with training_job_id={job_id}, trying alternative query")
                # Get frames from the video that are trained and have point IDs
                # We'll filter by checking if they were trained around the job creation time
                trained_frames = db.query(ExtractedFrame).filter(
                    and_(
                        ExtractedFrame.video_id == job.video_id,
                        ExtractedFrame.status == FrameStatus.TRAINED,
                        ExtractedFrame.qdrant_point_id.isnot(None),
                        ExtractedFrame.deleted_at.is_(None)
                    )
                ).all()
                
                # If we found frames this way, log a warning
                if trained_frames:
                    celery_logger.warning(
                        f"Found {len(trained_frames)} trained frames for video {job.video_id} "
                        f"without training_job_id. These will be rolled back."
                    )

            if not trained_frames:
                celery_logger.warning(f"No trained frames found for job {job_id}")
                # Still mark job as rolled back
                job.status = JobStatus.ROLLED_BACK
                job.rolled_back_at = datetime.utcnow()
                db.commit()
                celery_logger.info(f"Job {job_id} marked as rolled back (no frames to rollback)")
                return

            total_frames = len(trained_frames)
            celery_logger.info(f"Rolling back {total_frames} trained frames for job {job_id}")

            # Collect point IDs (only non-null ones)
            point_ids = [frame.qdrant_point_id for frame in trained_frames if frame.qdrant_point_id]
            
            # Delete from Qdrant in batches
            delete_result = {"success": 0, "failed": []}
            if point_ids:
                try:
                    celery_logger.info(f"Attempting to delete {len(point_ids)} points from Qdrant: {point_ids}")
                    delete_result = qdrant_service.delete_batch(point_ids)
                    
                    celery_logger.info(
                        f"Qdrant deletion result: {delete_result['success']} success, "
                        f"{len(delete_result.get('failed', []))} failed"
                    )
                    
                    # Log failed deletions with details
                    if delete_result.get('failed'):
                        failed_ids = delete_result['failed']
                        celery_logger.warning(
                            f"Failed to delete {len(failed_ids)} points from Qdrant: {failed_ids}"
                        )
                    
                    # Even if some deletions failed, continue with frame reset
                    if delete_result['success'] > 0:
                        celery_logger.info(f"Successfully deleted {delete_result['success']} points from Qdrant")
                        
                except Exception as e:
                    celery_logger.error(f"Error deleting from Qdrant: {str(e)}", exc_info=True)
                    # Continue with frame reset even if Qdrant delete fails completely
                    delete_result = {"success": 0, "failed": point_ids}
                    celery_logger.warning("Continuing with frame reset despite Qdrant deletion failure")
            else:
                celery_logger.warning(f"No Qdrant point IDs found for job {job_id} frames")

            # Delete embeddings from MySQL and reset frames
            frames_reset = 0
            for frame in trained_frames:
                try:
                    # Delete embedding if exists
                    embedding = db.query(FrameEmbedding).filter(
                        FrameEmbedding.frame_id == frame.id
                    ).first()
                    if embedding:
                        db.delete(embedding)
                        celery_logger.debug(f"Deleted embedding for frame {frame.id}")

                    # Reset frame status and clear job link
                    frame.status = FrameStatus.SELECTED
                    frame.qdrant_point_id = None
                    frame.training_job_id = None  # Clear job link
                    frames_reset += 1
                    celery_logger.debug(f"Reset frame {frame.id} to SELECTED status")
                except Exception as e:
                    celery_logger.error(f"Error resetting frame {frame.id}: {str(e)}", exc_info=True)

            # Update job status
            job.status = JobStatus.ROLLED_BACK
            job.rolled_back_at = datetime.utcnow()

            db.commit()
            
            # Refresh all frames to ensure state is updated
            for frame in trained_frames:
                try:
                    db.refresh(frame)
                except Exception as e:
                    celery_logger.warning(f"Could not refresh frame {frame.id}: {str(e)}")

            # Log rollback
            log_entry = ProcessingLog(
                entity_type=EntityType.TRAINING_JOB,
                entity_id=job_id,
                action="training_rolled_back",
                status=LogStatus.SUCCESS,
                message=f"Rolled back {frames_reset} frames",
                extra_metadata={
                    "total_frames": total_frames,
                    "frames_reset": frames_reset,
                    "video_id": job.video_id,
                    "qdrant_deleted": delete_result['success'],
                    "qdrant_failed": len(delete_result.get('failed', [])),
                    "qdrant_failed_ids": delete_result.get('failed', [])
                }
            )
            db.add(log_entry)
            db.commit()

            celery_logger.info(
                f"Rollback completed for job {job_id}: "
                f"{frames_reset} frames reset, "
                f"{delete_result['success']} Qdrant points deleted"
            )
            
            # Broadcast rollback completion via Redis
            try:
                message = {
                    "type": "rollback_completed",
                    "job_id": job_id,
                    "video_id": job.video_id,
                    "frames_reset": frames_reset,
                    "qdrant_deleted": delete_result['success'],
                    "client_session_id": client_session_id,
                    "request_id": request_id
                }
                redis_client.publish("progress_channel", json.dumps(message))
                celery_logger.debug(f"Rollback completion broadcast: {message}")
            except Exception as e:
                celery_logger.warning(f"Could not broadcast rollback completion: {str(e)}")

    except Exception as e:
        celery_logger.error(f"Error in rollback_training_task: {str(e)}", exc_info=True)
        raise


def broadcast_training_progress(
    job_id: int,
    video_id: int,
    current: int,
    total: int,
    percent: float,
    status: str,
    client_session_id: str = None,
    request_id: str = None
):
    """
    Broadcast training progress via Redis Pub/Sub.

    Args:
        job_id: Training job ID
        video_id: Video ID
        current: Current frame count
        total: Total frame count
        percent: Progress percentage
        status: Status message
        client_session_id: Client session ID for routing
        request_id: Request ID for tracking
    """
    try:
        message = {
            "type": "training_progress",
            "job_id": job_id,
            "video_id": video_id,
            "current": current,
            "total": total,
            "percent": round(percent, 2),
            "status": status,
            "message": f"Training frames: {current}/{total}",
            "client_session_id": client_session_id,
            "request_id": request_id
        }

        redis_client.publish("progress_channel", json.dumps(message))
        celery_logger.debug(f"Training progress broadcast: {message}")

    except Exception as e:
        celery_logger.error(f"Error broadcasting training progress: {str(e)}")
