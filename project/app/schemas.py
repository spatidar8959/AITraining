"""
Pydantic schemas for request/response validation
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

from app.models import VideoStatus, FrameStatus, JobStatus


# ==================== Request Schemas ====================

class VideoUploadMetadata(BaseModel):
    """Metadata for video upload"""
    model_config = {"protected_namespaces": ()}

    asset_name: str = Field(..., min_length=1, max_length=200, description="Asset name")
    model_number: Optional[str] = Field(None, max_length=100, description="Model number")
    category: str = Field(..., min_length=1, max_length=100, description="Asset category")
    manufacturer: Optional[str] = Field(None, max_length=100, description="Manufacturer name")
    ai_attributes: Optional[str] = Field(None, description="AI-specific attributes (usually null)")
    latitude: Optional[Decimal] = Field(None, ge=-90, le=90, description="Latitude coordinate")
    longitude: Optional[Decimal] = Field(None, ge=-180, le=180, description="Longitude coordinate")
    fps: int = Field(2, ge=1, le=10, description="Frames per second for extraction")

    @validator('fps')
    def validate_fps(cls, v):
        if v < 1 or v > 10:
            raise ValueError('FPS must be between 1 and 10')
        return v


class FrameSelectionRequest(BaseModel):
    """Request for bulk frame selection/deselection"""
    frame_ids: List[int] = Field(..., min_items=1, description="List of frame IDs")
    action: str = Field(..., description="Action: 'select' or 'deselect'")

    @validator('action')
    def validate_action(cls, v):
        if v not in ['select', 'deselect']:
            raise ValueError("Action must be 'select' or 'deselect'")
        return v


# ==================== Response Schemas ====================

class VideoUploadResponse(BaseModel):
    """Response for video upload"""
    video_id: int
    status: VideoStatus
    message: str


class VideoDuplicateResponse(BaseModel):
    """Response for duplicate video"""
    error: str = "duplicate"
    existing_video_id: int
    message: str


class ExtractionTriggerResponse(BaseModel):
    """Response for extraction trigger"""
    task_id: str
    status: str
    message: str


class FrameResponse(BaseModel):
    """Single frame response"""
    id: int
    frame_number: int
    thumbnail_url: str
    status: FrameStatus  # This should serialize to string automatically
    
    class Config:
        use_enum_values = True  # Ensure enum values are used, not enum objects


class FrameListResponse(BaseModel):
    """Response for frame listing with pagination"""
    total: int
    page: int
    page_size: int
    frames: List[FrameResponse]


class FrameSelectionResponse(BaseModel):
    """Response for frame selection"""
    updated: int
    message: str


class FrameDeleteResponse(BaseModel):
    """Response for frame deletion"""
    message: str


class DashboardVideosStats(BaseModel):
    """Dashboard video statistics"""
    total: int
    uploaded: int
    extracting: int
    extracted: int
    failed: int


class DashboardFramesStats(BaseModel):
    """Dashboard frame statistics"""
    total: int
    extracted: int
    selected: int
    trained: int
    deleted: int


class DashboardTrainingStats(BaseModel):
    """Dashboard training statistics"""
    total: int
    processing: int
    completed: int
    failed: int


class DashboardResponse(BaseModel):
    """Response for dashboard statistics"""
    videos: DashboardVideosStats
    frames: DashboardFramesStats
    training_jobs: DashboardTrainingStats


class WebSocketProgressMessage(BaseModel):
    """WebSocket progress update message"""
    type: str  # "extraction_progress" or "training_progress"
    video_id: int
    job_id: Optional[int] = None
    current: int
    total: int
    percent: float
    status: str
    message: str


class ErrorResponse(BaseModel):
    """Generic error response"""
    error: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class HealthCheckResponse(BaseModel):
    """Health check response"""
    status: str
    database: bool
    redis: bool
    s3: bool
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ==================== Database Model Response Schemas ====================

class VideoBatchSchema(BaseModel):
    """Video batch schema for API responses"""
    model_config = {"protected_namespaces": (), "from_attributes": True}

    id: int
    video_hash: str
    filename: str
    asset_name: str
    model_number: Optional[str]
    category: str
    manufacturer: Optional[str]
    ai_attributes: Optional[str]
    latitude: Optional[Decimal]
    longitude: Optional[Decimal]
    fps: int
    status: VideoStatus
    total_frames: int
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime


class ExtractedFrameSchema(BaseModel):
    """Extracted frame schema for API responses"""
    id: int
    video_id: int
    frame_number: int
    filename: str
    s3_path: Optional[str]
    thumbnail_s3_path: Optional[str]
    status: FrameStatus
    qdrant_point_id: Optional[str]
    training_attempts: int
    last_error: Optional[str]
    deleted_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class TrainingJobSchema(BaseModel):
    """Training job schema for API responses"""
    id: int
    video_id: int
    celery_task_id: Optional[str]
    status: JobStatus
    total_frames: int
    processed_frames: int
    failed_frames: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== Training Request/Response Schemas ====================

class TrainingExecuteRequest(BaseModel):
    """Request for training execution"""
    video_id: int = Field(..., description="Video ID to train frames from")
    frame_ids: Optional[List[int]] = Field(None, description="Specific frame IDs to train (if empty, trains all selected)")


class TrainingExecuteResponse(BaseModel):
    """Response for training execution"""
    job_id: int
    task_id: str
    total_frames: int
    message: str


class TrainingStatusResponse(BaseModel):
    """Response for training job status"""
    job_id: int
    status: JobStatus
    total_frames: int
    processed_frames: int
    failed_frames: int
    progress_percent: float
    started_at: Optional[datetime]
    estimated_completion: Optional[datetime]


class TrainingRollbackResponse(BaseModel):
    """Response for training rollback"""
    rollback_job_id: int
    message: str


class TrainingJobItem(BaseModel):
    """Training job item for listing"""
    id: int
    video_id: int
    video_name: str
    status: JobStatus
    total_frames: int
    processed_frames: int
    failed_frames: int
    progress_percent: float
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    rolled_back_at: Optional[datetime]  # Add this
    created_at: datetime

    class Config:
        from_attributes = True


class TrainingJobListResponse(BaseModel):
    """Response for training job listing"""
    total: int
    page: int
    page_size: int
    jobs: List[TrainingJobItem]


class VideoDeletionResponse(BaseModel):
    """Response for video deletion with cascade"""
    video_id: int
    frames_deleted: int
    s3_files_deleted: int
    qdrant_points_deleted: int
    message: str


# ==================== Video Management Schemas ====================

class VideoItem(BaseModel):
    """Video item for listing"""
    model_config = {"protected_namespaces": (), "from_attributes": True}

    id: int
    filename: str
    asset_name: str
    category: str
    status: VideoStatus
    total_frames: int
    fps: int
    model_number: Optional[str]
    manufacturer: Optional[str]
    created_at: datetime
    updated_at: datetime


class VideoListResponse(BaseModel):
    """Response for video listing"""
    total: int
    page: int
    page_size: int
    videos: List[VideoItem]


class VideoDetailResponse(BaseModel):
    """Detailed video response with frame statistics"""
    model_config = {"protected_namespaces": (), "from_attributes": True}

    id: int
    filename: str
    asset_name: str
    category: str
    status: VideoStatus
    total_frames: int
    fps: int
    model_number: Optional[str]
    manufacturer: Optional[str]
    ai_attributes: Optional[str]
    latitude: Optional[Decimal]
    longitude: Optional[Decimal]
    frames_extracted: int
    frames_selected: int
    frames_trained: int
    frames_deleted: int
    training_jobs_count: int
    created_at: datetime
    updated_at: datetime


# ==================== Frame Update Schemas ====================

class FrameUpdateRequest(BaseModel):
    """Request for updating frame metadata"""
    frame_id: int
    metadata: Optional[dict] = None


class FrameUpdateResponse(BaseModel):
    """Response for frame update"""
    frame_id: int
    message: str
    updated_in_qdrant: bool


# ==================== Qdrant/Vector DB Schemas ====================

class QdrantPointSearchRequest(BaseModel):
    """Request for searching Qdrant points"""
    query_text: Optional[str] = None
    query_image_path: Optional[str] = None
    limit: int = Field(10, ge=1, le=100)
    score_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    filter_category: Optional[str] = None


class QdrantPointResponse(BaseModel):
    """Single Qdrant point response"""
    point_id: str
    score: Optional[float]
    payload: dict


class QdrantSearchResponse(BaseModel):
    """Response for Qdrant search"""
    results: List[QdrantPointResponse]
    total: int


class QdrantCollectionInfoResponse(BaseModel):
    """Response for Qdrant collection info"""
    collection_name: str
    vectors_count: int
    points_count: int
    status: str


class QdrantPointDeleteRequest(BaseModel):
    """Request for deleting Qdrant points"""
    point_ids: List[str] = Field(..., min_items=1)


class QdrantPointDeleteResponse(BaseModel):
    """Response for Qdrant point deletion"""
    deleted_count: int
    message: str


# ==================== Bulk Frame Delete Schemas ====================

class BulkFrameDeleteRequest(BaseModel):
    """Request for bulk frame deletion"""
    frame_ids: List[int] = Field(..., min_items=1, description="List of frame IDs to delete")
    permanent: bool = Field(False, description="If true, permanently delete (hard delete)")


class BulkFrameDeleteResponse(BaseModel):
    """Response for bulk frame deletion"""
    deleted_count: int = Field(..., description="Number of frames successfully deleted")
    failed_count: int = Field(0, description="Number of frames that failed to delete")
    qdrant_deleted: int = Field(0, description="Number of Qdrant points deleted")
    s3_deleted: int = Field(0, description="Number of S3 files deleted")
    message: str = Field(..., description="Summary message")
