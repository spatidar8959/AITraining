"""
Dashboard statistics API endpoint
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from app.database import get_db
from app.models import VideoBatch, ExtractedFrame, TrainingJob, VideoStatus, FrameStatus, JobStatus
from app.schemas import (
    DashboardResponse,
    DashboardVideosStats,
    DashboardFramesStats,
    DashboardTrainingStats
)
from app.utils.logger import app_logger

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard_stats(db: Session = Depends(get_db)):
    """
    Get system-wide statistics for dashboard.

    Returns:
        Statistics for videos, frames, and training jobs grouped by status
    """
    try:
        # Video statistics
        video_stats = db.query(
            func.count(VideoBatch.id).label('total'),
            func.sum(case((VideoBatch.status == VideoStatus.UPLOADED, 1), else_=0)).label('uploaded'),
            func.sum(case((VideoBatch.status == VideoStatus.EXTRACTING, 1), else_=0)).label('extracting'),
            func.sum(case((VideoBatch.status == VideoStatus.EXTRACTED, 1), else_=0)).label('extracted'),
            func.sum(case((VideoBatch.status == VideoStatus.FAILED, 1), else_=0)).label('failed')
        ).first()

        # Frame statistics
        frame_stats = db.query(
            func.count(ExtractedFrame.id).label('total'),
            func.sum(case((ExtractedFrame.status == FrameStatus.EXTRACTED, 1), else_=0)).label('extracted'),
            func.sum(case((ExtractedFrame.status == FrameStatus.SELECTED, 1), else_=0)).label('selected'),
            func.sum(case((ExtractedFrame.status == FrameStatus.TRAINED, 1), else_=0)).label('trained'),
            func.sum(case((ExtractedFrame.status == FrameStatus.DELETED, 1), else_=0)).label('deleted')
        ).filter(ExtractedFrame.deleted_at.is_(None)).first()

        # Training job statistics
        training_stats = db.query(
            func.count(TrainingJob.id).label('total'),
            func.sum(case((TrainingJob.status == JobStatus.PROCESSING, 1), else_=0)).label('processing'),
            func.sum(case((TrainingJob.status == JobStatus.COMPLETED, 1), else_=0)).label('completed'),
            func.sum(case((TrainingJob.status == JobStatus.FAILED, 1), else_=0)).label('failed')
        ).first()

        # Build response
        return DashboardResponse(
            videos=DashboardVideosStats(
                total=video_stats.total or 0,
                uploaded=video_stats.uploaded or 0,
                extracting=video_stats.extracting or 0,
                extracted=video_stats.extracted or 0,
                failed=video_stats.failed or 0
            ),
            frames=DashboardFramesStats(
                total=frame_stats.total or 0,
                extracted=frame_stats.extracted or 0,
                selected=frame_stats.selected or 0,
                trained=frame_stats.trained or 0,
                deleted=frame_stats.deleted or 0
            ),
            training_jobs=DashboardTrainingStats(
                total=training_stats.total or 0,
                processing=training_stats.processing or 0,
                completed=training_stats.completed or 0,
                failed=training_stats.failed or 0
            )
        )

    except Exception as e:
        app_logger.error(f"Error getting dashboard stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve dashboard statistics: {str(e)}"
        )
