"""
Celery task for video frame extraction with FFmpeg
"""
import os
import subprocess
from pathlib import Path
from typing import List
import json
import time
from PIL import Image

from celery import Task
from app.celery_app import celery_app
from app.database import get_db_context
from app.models import VideoBatch, ExtractedFrame, VideoStatus, FrameStatus, ProcessingLog, EntityType, LogStatus
from app.services.s3_service import s3_service
from app.config import settings
from app.utils.logger import celery_logger
import redis

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


@celery_app.task(bind=True, base=CallbackTask, max_retries=3)
def extract_frames_task(self, video_id: int):
    """
    Extract frames from video using FFmpeg with checkpoint-based resumption.

    Process:
    1. Get video details from database
    2. Use FFmpeg to extract frames based on FPS
    3. Process in batches of FRAME_EXTRACTION_BATCH_SIZE (100)
    4. For each batch:
       - Extract frames locally
       - Generate thumbnails
       - Upload to S3
       - Create database records
       - Update checkpoint
       - Broadcast progress via Redis
    5. Delete video file after successful extraction
    6. Update video status to 'extracted'

    Args:
        video_id: ID of video to process
    """
    try:
        with get_db_context() as db:
            # Get video record
            video = db.query(VideoBatch).filter(VideoBatch.id == video_id).first()
            if not video:
                celery_logger.error(f"Video {video_id} not found")
                return

            # Construct video file path
            video_path = os.path.join(settings.TEMP_VIDEO_DIR, f"video_{video_id}_{video.filename}")
            if not os.path.exists(video_path):
                video.status = VideoStatus.FAILED
                video.error_message = "Video file not found"
                db.commit()
                db.refresh(video)
                celery_logger.error(f"Video file not found: {video_path}")
                return

            celery_logger.info(f"Starting frame extraction for video_id={video_id}, fps={video.fps}")

            # Create temp directory for frames
            frames_dir = os.path.join(settings.TEMP_FRAMES_DIR, f"video_{video_id}")
            os.makedirs(frames_dir, exist_ok=True)

            # Get video duration and calculate total frames
            duration_cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_path
            ]
            duration_result = subprocess.run(duration_cmd, capture_output=True, text=True)
            duration = float(duration_result.stdout.strip())
            total_frames_estimate = int(duration * video.fps)

            celery_logger.info(f"Video duration: {duration}s, estimated frames: {total_frames_estimate}")

            # Extract frames using FFmpeg
            output_pattern = os.path.join(frames_dir, "frame_%06d.jpg")
            ffmpeg_cmd = [
                'ffmpeg',
                '-i', video_path,
                '-vf', f'fps={video.fps}',
                '-q:v', '2',  # High quality JPEG
                output_pattern
            ]

            celery_logger.info(f"Running FFmpeg: {' '.join(ffmpeg_cmd)}")
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)

            if result.returncode != 0:
                video.status = VideoStatus.FAILED
                video.error_message = f"FFmpeg error: {result.stderr}"
                db.commit()
                db.refresh(video)
                celery_logger.error(f"FFmpeg extraction failed: {result.stderr}")
                return

            # Get all extracted frame files
            frame_files = sorted([f for f in os.listdir(frames_dir) if f.endswith('.jpg')])
            total_frames = len(frame_files)

            celery_logger.info(f"Extracted {total_frames} frames")

            # Process frames in batches
            batch_size = settings.FRAME_EXTRACTION_BATCH_SIZE
            for batch_start in range(0, total_frames, batch_size):
                batch_end = min(batch_start + batch_size, total_frames)
                batch_files = frame_files[batch_start:batch_end]

                celery_logger.info(f"Processing batch {batch_start}-{batch_end}")

                for idx, frame_file in enumerate(batch_files):
                    frame_number = batch_start + idx + 1
                    frame_path = os.path.join(frames_dir, frame_file)

                    # Generate thumbnail
                    thumbnail_path = os.path.join(frames_dir, f"thumb_{frame_file}")
                    create_thumbnail(frame_path, thumbnail_path)

                    # Upload to S3
                    s3_frame_key = f"{settings.S3_FRAMES_PREFIX}video_{video_id}/frame_{frame_number:06d}.jpg"
                    s3_thumb_key = f"{settings.S3_THUMBNAILS_PREFIX}video_{video_id}/thumb_{frame_number:06d}.jpg"

                    # Upload full frame
                    s3_service.upload_file(frame_path, s3_frame_key, content_type="image/jpeg")

                    # Upload thumbnail
                    s3_service.upload_file(thumbnail_path, s3_thumb_key, content_type="image/jpeg")

                    # Create database record
                    extracted_frame = ExtractedFrame(
                        video_id=video_id,
                        frame_number=frame_number,
                        filename=frame_file,
                        s3_path=s3_frame_key,
                        thumbnail_s3_path=s3_thumb_key,
                        status=FrameStatus.EXTRACTED
                    )
                    db.add(extracted_frame)

                    # Clean up local files
                    os.remove(frame_path)
                    os.remove(thumbnail_path)

                # Commit batch
                db.commit()

                # Update video total_frames
                video.total_frames = batch_end
                db.commit()
                db.refresh(video)

                # Broadcast progress
                progress_percent = (batch_end / total_frames) * 100
                broadcast_extraction_progress(
                    video_id=video_id,
                    current=batch_end,
                    total=total_frames,
                    percent=progress_percent,
                    status="processing"
                )

                celery_logger.info(f"Batch {batch_start}-{batch_end} completed ({progress_percent:.1f}%)")

            # Delete video file (save storage space)
            os.remove(video_path)
            celery_logger.info(f"Video file deleted: {video_path}")

            # Update video status
            video.status = VideoStatus.EXTRACTED
            video.total_frames = total_frames
            # #region agent log
            try:
                with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"G","location":"extraction.py:187","message":"BEFORE video status commit - extraction completed","data":{"video_id":video_id,"status_before":None,"status_after":video.status.value,"total_frames":total_frames},"timestamp":int(time.time()*1000)}) + "\n")
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
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"G","location":"extraction.py:192","message":"AFTER video status commit and refresh","data":{"video_id":video_id,"status_after_refresh":video.status.value,"status_from_query":video_verify.status.value if video_verify else None,"total_frames_after_refresh":video.total_frames,"total_frames_from_query":video_verify.total_frames if video_verify else None},"timestamp":int(time.time()*1000)}) + "\n")
            except:
                pass
            # #endregion

            # Log completion
            log_entry = ProcessingLog(
                entity_type=EntityType.VIDEO,
                entity_id=video_id,
                action="extraction_completed",
                status=LogStatus.SUCCESS,
                message=f"Extracted {total_frames} frames",
                extra_metadata={"total_frames": total_frames, "fps": video.fps}
            )
            db.add(log_entry)
            db.commit()

            # Broadcast completion
            broadcast_extraction_progress(
                video_id=video_id,
                current=total_frames,
                total=total_frames,
                percent=100.0,
                status="completed"
            )

            celery_logger.info(f"Frame extraction completed for video_id={video_id}")

            # Clean up temp directory
            if os.path.exists(frames_dir):
                os.rmdir(frames_dir)

    except Exception as e:
        celery_logger.error(f"Error in extract_frames_task: {str(e)}")

        # Update video status to failed
        with get_db_context() as db:
            video = db.query(VideoBatch).filter(VideoBatch.id == video_id).first()
            if video:
                video.status = VideoStatus.FAILED
                video.error_message = str(e)
                # #region agent log
                try:
                    with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"H","location":"extraction.py:243","message":"BEFORE exception handler commit - video failed","data":{"video_id":video_id,"status_after":video.status.value,"error_message":str(e)[:200]},"timestamp":int(time.time()*1000)}) + "\n")
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
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"H","location":"extraction.py:248","message":"AFTER exception handler commit and refresh","data":{"video_id":video_id,"status_after_refresh":video.status.value,"status_from_query":video_verify.status.value if video_verify else None},"timestamp":int(time.time()*1000)}) + "\n")
                except:
                    pass
                # #endregion

                # Log failure
                log_entry = ProcessingLog(
                    entity_type=EntityType.VIDEO,
                    entity_id=video_id,
                    action="extraction_failed",
                    status=LogStatus.FAILED,
                    message=f"Extraction failed: {str(e)}",
                    extra_metadata={"error": str(e)}
                )
                db.add(log_entry)
                db.commit()

        raise


def create_thumbnail(input_path: str, output_path: str):
    """
    Create thumbnail from image.

    Args:
        input_path: Path to input image
        output_path: Path to save thumbnail
    """
    try:
        with Image.open(input_path) as img:
            # Calculate aspect ratio
            aspect_ratio = img.width / img.height
            thumb_width = settings.THUMBNAIL_WIDTH
            thumb_height = int(thumb_width / aspect_ratio)

            # Resize
            img.thumbnail((thumb_width, thumb_height), Image.Resampling.LANCZOS)
            img.save(output_path, "JPEG", quality=85)

    except Exception as e:
        celery_logger.error(f"Error creating thumbnail: {str(e)}")
        raise


def broadcast_extraction_progress(video_id: int, current: int, total: int, percent: float, status: str):
    """
    Broadcast extraction progress via Redis Pub/Sub.

    Args:
        video_id: Video ID
        current: Current frame count
        total: Total frame count
        percent: Progress percentage
        status: Status message
    """
    try:
        message = {
            "type": "extraction_progress",
            "video_id": video_id,
            "current": current,
            "total": total,
            "percent": round(percent, 2),
            "status": status,
            "message": f"Extracting frames: {current}/{total}"
        }

        redis_client.publish("progress_channel", json.dumps(message))
        celery_logger.debug(f"Progress broadcast: {message}")

    except Exception as e:
        celery_logger.error(f"Error broadcasting progress: {str(e)}")
