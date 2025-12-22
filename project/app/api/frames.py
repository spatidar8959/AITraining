"""
Frame listing, selection, and deletion API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List

from app.database import get_db
from app.models import ExtractedFrame, VideoBatch, FrameStatus, ProcessingLog, EntityType, LogStatus
from app.schemas import (
    FrameListResponse,
    FrameResponse,
    FrameSelectionRequest,
    FrameSelectionResponse,
    FrameDeleteResponse,
    BulkFrameDeleteRequest,
    BulkFrameDeleteResponse
)
from app.services.s3_service import s3_service
from app.utils.logger import app_logger

router = APIRouter(prefix="/api", tags=["frames"])


@router.get("/video/{video_id}/frames", response_model=FrameListResponse)
async def get_video_frames(
    video_id: int,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(None, description="Filter by status: extracted, selected, trained, deleted"),
    db: Session = Depends(get_db)
):
    """
    Get extracted frames for a video with pagination and filtering.

    Args:
        video_id: Video ID
        page: Page number (starts at 1)
        page_size: Number of frames per page (max 100)
        status_filter: Optional status filter

    Returns:
        Paginated list of frames with presigned thumbnail URLs
    """
    try:
        # Verify video exists
        video = db.query(VideoBatch).filter(VideoBatch.id == video_id).first()
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Video with ID {video_id} not found"
            )

        # Build query
        query = db.query(ExtractedFrame).filter(ExtractedFrame.video_id == video_id)

        # Apply status filter
        if status_filter:
            try:
                status_enum = FrameStatus(status_filter)
                query = query.filter(ExtractedFrame.status == status_enum)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status: {status_filter}"
                )

        # Exclude soft-deleted frames (unless explicitly filtering for 'deleted')
        if status_filter != 'deleted':
            query = query.filter(ExtractedFrame.deleted_at.is_(None))

        # Get total count
        total = query.count()

        # Apply pagination
        offset = (page - 1) * page_size
        frames = query.order_by(ExtractedFrame.frame_number).offset(offset).limit(page_size).all()

        # Generate presigned URLs for thumbnails
        frame_responses = []
        for frame in frames:
            thumbnail_url = ""
            if frame.thumbnail_s3_path:
                thumbnail_url = s3_service.generate_presigned_url(frame.thumbnail_s3_path, expiration=3600)

            frame_responses.append(FrameResponse(
                id=frame.id,
                frame_number=frame.frame_number,
                thumbnail_url=thumbnail_url or "",
                status=frame.status
            ))

        return FrameListResponse(
            total=total,
            page=page,
            page_size=page_size,
            frames=frame_responses
        )

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error getting frames: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve frames: {str(e)}"
        )


@router.patch("/frames/selection", response_model=FrameSelectionResponse)
async def update_frame_selection(
    request: FrameSelectionRequest,
    db: Session = Depends(get_db)
):
    """
    Bulk update frame selection status.
    Prevents selecting frames that are trained, deleted, or in training.
    """
    try:
        # Validate all frames exist and belong to same video
        frames = db.query(ExtractedFrame).filter(ExtractedFrame.id.in_(request.frame_ids)).all()

        if len(frames) != len(request.frame_ids):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Some frame IDs not found"
            )

        # Check all frames belong to same video
        video_ids = set(frame.video_id for frame in frames)
        if len(video_ids) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="All frames must belong to the same video"
            )

        # If selecting, check that frames are not trained, deleted, or in training
        if request.action == 'select':
            invalid_frames = []
            for frame in frames:
                if frame.status in [FrameStatus.TRAINED, FrameStatus.DELETED, FrameStatus.TRAINING]:
                    invalid_frames.append({
                        "id": frame.id,
                        "status": frame.status.value,
                        "reason": f"Frame is {frame.status.value} and cannot be selected"
                    })
            
            if invalid_frames:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot select frames that are trained, deleted, or in training: {[f['id'] for f in invalid_frames]}"
                )

        # Update status
        if request.action == 'select':
            new_status = FrameStatus.SELECTED
        else:  # deselect
            new_status = FrameStatus.EXTRACTED

        updated_count = 0
        for frame in frames:
            # Only update if not already in target status
            if frame.status != new_status:
                frame.status = new_status
                updated_count += 1

        db.commit()
        # Refresh frames to ensure state is updated
        for frame in frames:
            db.refresh(frame)

        app_logger.info(f"Updated {updated_count} frames to status '{new_status}'")

        # Log selection update
        log_entry = ProcessingLog(
            entity_type=EntityType.VIDEO,
            entity_id=list(video_ids)[0],
            action=f"frames_{request.action}ed",
            status=LogStatus.SUCCESS,
            message=f"{updated_count} frames {request.action}ed",
            extra_metadata={"frame_count": updated_count, "frame_ids": request.frame_ids}
        )
        db.add(log_entry)
        db.commit()

        return FrameSelectionResponse(
            updated=updated_count,
            message=f"{updated_count} frames {request.action}ed"
        )

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error updating frame selection: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update frame selection: {str(e)}"
        )


@router.patch("/frames/{frame_id}", status_code=status.HTTP_200_OK)
async def update_frame_metadata(
    frame_id: int,
    metadata: dict,
    db: Session = Depends(get_db)
):
    """
    Update frame metadata and propagate changes to Qdrant.

    Args:
        frame_id: Frame ID
        metadata: Dictionary of metadata to update
        db: Database session

    Returns:
        Success message with Qdrant update status
    """
    try:
        from app.services.qdrant_service import qdrant_service

        # Get frame
        frame = db.query(ExtractedFrame).filter(ExtractedFrame.id == frame_id).first()
        if not frame:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Frame {frame_id} not found"
            )

        # Get associated video for metadata
        video = db.query(VideoBatch).filter(VideoBatch.id == frame.video_id).first()

        updated_in_qdrant = False

        # If frame is trained, update Qdrant point payload
        if frame.status == FrameStatus.TRAINED and frame.qdrant_point_id:
            # Build updated payload
            updated_payload = {
                "asset_name": metadata.get("asset_name", video.asset_name),
                "image_id": str(frame.id),
                "model_id": metadata.get("model_number", video.model_number or ""),
                "category": metadata.get("category", video.category),
                "manufacturer_name": metadata.get("manufacturer", video.manufacturer or ""),
                "image_path": frame.s3_path,
                "ai_attributes": metadata.get("ai_attributes", video.ai_attributes or ""),
                "location": {
                    "lon": float(metadata.get("longitude", video.longitude or 0)),
                    "lat": float(metadata.get("latitude", video.latitude or 0))
                }
            }

            # Update Qdrant point payload
            try:
                qdrant_service.update_point_payload(frame.qdrant_point_id, updated_payload)
                updated_in_qdrant = True
                app_logger.info(f"Updated Qdrant point {frame.qdrant_point_id} for frame {frame_id}")
            except Exception as e:
                app_logger.error(f"Failed to update Qdrant point: {str(e)}")

        db.commit()

        # Log update
        log_entry = ProcessingLog(
            entity_type=EntityType.FRAME,
            entity_id=frame_id,
            action="frame_metadata_updated",
            status=LogStatus.SUCCESS,
            message="Frame metadata updated",
            extra_metadata={
                "metadata": metadata,
                "updated_in_qdrant": updated_in_qdrant
            }
        )
        db.add(log_entry)
        db.commit()

        return {
            "message": "Frame metadata updated successfully",
            "frame_id": frame_id,
            "updated_in_qdrant": updated_in_qdrant
        }

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error updating frame metadata: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update frame metadata: {str(e)}"
        )


# IMPORTANT: Bulk delete must come BEFORE {frame_id} route to avoid path matching conflicts
@router.delete("/frames/bulk", response_model=BulkFrameDeleteResponse)
async def bulk_delete_frames(
    request: BulkFrameDeleteRequest,
    db: Session = Depends(get_db)
):
    """
    Bulk delete multiple frames (soft or hard delete).

    Args:
        request: Frame IDs and deletion type
        db: Database session

    Returns:
        Deletion summary
    """
    try:
        from app.services.qdrant_service import qdrant_service
        from app.services.s3_service import s3_service
        from app.models import FrameEmbedding

        # Get all frames
        frames = db.query(ExtractedFrame).filter(ExtractedFrame.id.in_(request.frame_ids)).all()

        if not frames:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No frames found with provided IDs"
            )

        deleted_count = 0
        failed_count = 0
        qdrant_deleted = 0
        s3_deleted = 0

        if request.permanent:
            # Hard delete
            qdrant_point_ids = []
            s3_keys = []

            # Collect all S3 keys and Qdrant point IDs
            for frame in frames:
                if frame.qdrant_point_id:
                    qdrant_point_ids.append(frame.qdrant_point_id)
                if frame.s3_path:
                    s3_keys.append(frame.s3_path)
                if frame.thumbnail_s3_path:
                    s3_keys.append(frame.thumbnail_s3_path)

            # Bulk delete from Qdrant
            if qdrant_point_ids:
                try:
                    result = qdrant_service.delete_batch(qdrant_point_ids)
                    qdrant_deleted = result["success"]
                    app_logger.info(f"Deleted {qdrant_deleted} points from Qdrant")
                except Exception as e:
                    app_logger.error(f"Failed to delete from Qdrant: {e}")

            # Bulk delete from S3
            if s3_keys:
                try:
                    # Delete in batches of 1000
                    for i in range(0, len(s3_keys), 1000):
                        batch = s3_keys[i:i+1000]
                        if s3_service.delete_files_batch(batch):
                            s3_deleted += len(batch)
                    app_logger.info(f"Deleted {s3_deleted} S3 files")
                except Exception as e:
                    app_logger.error(f"Failed to delete from S3: {e}")

            # Delete embeddings and frames from database
            for frame in frames:
                try:
                    # Delete embedding
                    embedding = db.query(FrameEmbedding).filter(FrameEmbedding.frame_id == frame.id).first()
                    if embedding:
                        db.delete(embedding)

                    # Delete frame
                    db.delete(frame)
                    deleted_count += 1
                except Exception as e:
                    app_logger.error(f"Failed to delete frame {frame.id}: {e}")
                    failed_count += 1

            db.commit()

            app_logger.info(f"Bulk hard delete: {deleted_count} frames deleted, {failed_count} failed")

            # Log bulk deletion
            log_entry = ProcessingLog(
                entity_type=EntityType.FRAME,
                entity_id=0,  # No specific frame ID for bulk operation
                action="frames_bulk_hard_deleted",
                status=LogStatus.SUCCESS,
                message=f"Bulk hard delete: {deleted_count} frames",
                extra_metadata={
                    "deleted_count": deleted_count,
                    "failed_count": failed_count,
                    "qdrant_deleted": qdrant_deleted,
                    "s3_deleted": s3_deleted,
                    "frame_ids": request.frame_ids
                }
            )
            db.add(log_entry)
            db.commit()

        else:
            # Soft delete
            for frame in frames:
                try:
                    frame.status = FrameStatus.DELETED
                    frame.deleted_at = func.now()
                    deleted_count += 1
                except Exception as e:
                    app_logger.error(f"Failed to soft delete frame {frame.id}: {e}")
                    failed_count += 1

            db.commit()
            # Refresh frames to ensure state is updated
            for frame in frames:
                db.refresh(frame)

            app_logger.info(f"Bulk soft delete: {deleted_count} frames marked as deleted")

            # Log bulk deletion
            log_entry = ProcessingLog(
                entity_type=EntityType.FRAME,
                entity_id=0,
                action="frames_bulk_soft_deleted",
                status=LogStatus.SUCCESS,
                message=f"Bulk soft delete: {deleted_count} frames",
                extra_metadata={
                    "deleted_count": deleted_count,
                    "failed_count": failed_count,
                    "frame_ids": request.frame_ids
                }
            )
            db.add(log_entry)
            db.commit()

        return BulkFrameDeleteResponse(
            deleted_count=deleted_count,
            failed_count=failed_count,
            qdrant_deleted=qdrant_deleted,
            s3_deleted=s3_deleted,
            message=f"Deleted {deleted_count} frames, {failed_count} failed"
        )

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error in bulk delete: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to bulk delete frames: {str(e)}"
        )


@router.delete("/frames/{frame_id}", response_model=FrameDeleteResponse)
async def delete_frame(
    frame_id: int,
    permanent: bool = Query(False, description="If true, permanently delete from S3 and Qdrant"),
    db: Session = Depends(get_db)
):
    """
    Delete a frame (soft delete by default, or hard delete with permanent=true).

    Soft delete: Mark as deleted, keep S3 files and Qdrant entry
    Hard delete: Remove from S3, Qdrant, and database completely

    Args:
        frame_id: Frame ID to delete
        permanent: If true, permanently delete everywhere

    Returns:
        Success message
    """
    try:
        from app.services.qdrant_service import qdrant_service
        from app.services.s3_service import s3_service
        from app.models import FrameEmbedding

        # Get frame
        frame = db.query(ExtractedFrame).filter(ExtractedFrame.id == frame_id).first()
        if not frame:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Frame with ID {frame_id} not found"
            )

        if permanent:
            # Hard delete - remove from everywhere
            deleted_from_qdrant = False
            deleted_from_s3 = False

            # Delete from Qdrant if trained
            if frame.qdrant_point_id:
                try:
                    qdrant_service.delete_point(frame.qdrant_point_id)
                    deleted_from_qdrant = True
                    app_logger.info(f"Deleted frame {frame_id} from Qdrant")
                except Exception as e:
                    app_logger.error(f"Failed to delete frame {frame_id} from Qdrant: {e}")

            # Delete from S3
            s3_keys = []
            if frame.s3_path:
                s3_keys.append(frame.s3_path)
            if frame.thumbnail_s3_path:
                s3_keys.append(frame.thumbnail_s3_path)

            if s3_keys:
                try:
                    deleted_from_s3 = s3_service.delete_files_batch(s3_keys)
                    app_logger.info(f"Deleted {len(s3_keys)} S3 files for frame {frame_id}")
                except Exception as e:
                    app_logger.error(f"Failed to delete S3 files for frame {frame_id}: {e}")

            # Delete embedding from database (CASCADE will handle this, but explicit is better)
            embedding = db.query(FrameEmbedding).filter(FrameEmbedding.frame_id == frame_id).first()
            if embedding:
                db.delete(embedding)

            # Delete frame from database
            db.delete(frame)
            db.commit()

            app_logger.info(f"Frame {frame_id} permanently deleted")

            # Log deletion
            log_entry = ProcessingLog(
                entity_type=EntityType.FRAME,
                entity_id=frame_id,
                action="frame_hard_deleted",
                status=LogStatus.SUCCESS,
                message=f"Frame permanently deleted",
                extra_metadata={
                    "video_id": frame.video_id,
                    "frame_number": frame.frame_number,
                    "deleted_from_qdrant": deleted_from_qdrant,
                    "deleted_from_s3": deleted_from_s3
                }
            )
            db.add(log_entry)
            db.commit()

            return FrameDeleteResponse(
                message="Frame permanently deleted from all systems"
            )

        else:
            # Soft delete
            frame.status = FrameStatus.DELETED
            frame.deleted_at = func.now()
            db.commit()
            db.refresh(frame)

            app_logger.info(f"Frame {frame_id} marked as deleted")

            # Log deletion
            log_entry = ProcessingLog(
                entity_type=EntityType.FRAME,
                entity_id=frame_id,
                action="frame_soft_deleted",
                status=LogStatus.SUCCESS,
                message=f"Frame soft deleted",
                extra_metadata={"video_id": frame.video_id, "frame_number": frame.frame_number}
            )
            db.add(log_entry)
            db.commit()

            return FrameDeleteResponse(
                message="Frame marked as deleted (soft delete)"
            )

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error deleting frame: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete frame: {str(e)}"
        )
