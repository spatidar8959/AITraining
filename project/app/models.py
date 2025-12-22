"""
SQLAlchemy ORM Models for Asset Training System
"""
from sqlalchemy import Column, BigInteger, String, Integer, DECIMAL, Enum, Text, TIMESTAMP, ForeignKey, JSON, CHAR
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()


# Enums
class VideoStatus(str, enum.Enum):
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    FAILED = "failed"


class FrameStatus(str, enum.Enum):
    EXTRACTED = "extracted"
    SELECTED = "selected"
    TRAINING = "training"
    TRAINED = "trained"
    DELETED = "deleted"


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    ROLLED_BACK = "rolled_back"  # Add this


class EntityType(str, enum.Enum):
    VIDEO = "video"
    FRAME = "frame"
    TRAINING_JOB = "training_job"


class LogStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"
    WARNING = "warning"


# Models
class VideoBatch(Base):
    """Video batch tracking table"""
    __tablename__ = "video_batches"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    video_hash = Column(CHAR(32), unique=True, nullable=False, index=True)
    filename = Column(String(500), nullable=False)
    asset_name = Column(String(200), nullable=False)
    model_number = Column(String(100), nullable=True)
    category = Column(String(100), nullable=False)
    manufacturer = Column(String(100), nullable=True)
    ai_attributes = Column(Text, nullable=True)
    latitude = Column(DECIMAL(10, 7), nullable=True)
    longitude = Column(DECIMAL(10, 7), nullable=True)
    fps = Column(Integer, nullable=False, default=2)
    status = Column(Enum(VideoStatus, native_enum=True, values_callable=lambda x: [e.value for e in x]), nullable=False, default=VideoStatus.UPLOADING, index=True)
    total_frames = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), index=True)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relationships
    frames = relationship("ExtractedFrame", back_populates="video", cascade="all, delete-orphan")
    training_jobs = relationship("TrainingJob", back_populates="video", cascade="all, delete-orphan")


class ExtractedFrame(Base):
    """Extracted frame metadata table"""
    __tablename__ = "extracted_frames"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    video_id = Column(BigInteger, ForeignKey("video_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    frame_number = Column(Integer, nullable=False)
    filename = Column(String(300), nullable=False)
    s3_path = Column(String(500), nullable=True)
    thumbnail_s3_path = Column(String(500), nullable=True)
    status = Column(Enum(FrameStatus, native_enum=True, values_callable=lambda x: [e.value for e in x]), nullable=False, default=FrameStatus.EXTRACTED, index=True)
    qdrant_point_id = Column(String(100), nullable=True, unique=True)
    training_job_id = Column(BigInteger, ForeignKey("training_jobs.id", ondelete="SET NULL"), nullable=True, index=True)  # Add this
    training_attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    deleted_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    video = relationship("VideoBatch", back_populates="frames")
    embedding = relationship("FrameEmbedding", back_populates="frame", uselist=False, cascade="all, delete-orphan")
    training_job = relationship("TrainingJob", foreign_keys=[training_job_id])  # Add this

    # Composite indexes handled in table creation


class FrameEmbedding(Base):
    """Frame embeddings storage table - stores vector embeddings for disaster recovery"""
    __tablename__ = "frame_embeddings"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    frame_id = Column(BigInteger, ForeignKey("extracted_frames.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    embedding = Column(JSON, nullable=False, comment="1408-dimensional vector from Google Vertex AI multimodalembedding@001")
    created_at = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    frame = relationship("ExtractedFrame", back_populates="embedding")


class TrainingJob(Base):
    """Training job tracking table"""
    __tablename__ = "training_jobs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    video_id = Column(BigInteger, ForeignKey("video_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    celery_task_id = Column(String(100), unique=True, nullable=True)
    status = Column(Enum(JobStatus, native_enum=True, values_callable=lambda x: [e.value for e in x]), nullable=False, default=JobStatus.PENDING, index=True)
    total_frames = Column(Integer, nullable=False, default=0)
    processed_frames = Column(Integer, nullable=False, default=0)
    failed_frames = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(TIMESTAMP, nullable=True)
    completed_at = Column(TIMESTAMP, nullable=True)
    rolled_back_at = Column(TIMESTAMP, nullable=True)  # Add this
    created_at = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    video = relationship("VideoBatch", back_populates="training_jobs")
    frames = relationship("ExtractedFrame", foreign_keys="ExtractedFrame.training_job_id", back_populates="training_job")  # Add this


class ProcessingLog(Base):
    """Processing logs and audit trail table"""
    __tablename__ = "processing_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    entity_type = Column(Enum(EntityType, native_enum=True, values_callable=lambda x: [e.value for e in x]), nullable=False, index=True)
    entity_id = Column(BigInteger, nullable=False, index=True)
    action = Column(String(100), nullable=False)
    status = Column(Enum(LogStatus, native_enum=True, values_callable=lambda x: [e.value for e in x]), nullable=False, index=True)
    message = Column(Text, nullable=True)
    extra_metadata = Column('metadata', JSON, nullable=True)  # 'metadata' is reserved in SQLAlchemy
    created_at = Column(TIMESTAMP, server_default=func.now(), index=True)
