"""
Configuration management with environment variables
"""
from pydantic_settings import BaseSettings
from pydantic import Field, validator
from typing import Optional
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Database Configuration
    DB_HOST: str = Field(default="localhost", description="MySQL host")
    DB_PORT: int = Field(default=3306, description="MySQL port")
    DB_USER: str = Field(default="root", description="MySQL username")
    DB_PASSWORD: str = Field(default="", description="MySQL password")
    DB_NAME: str = Field(default="asset_training", description="Database name")

    # Redis Configuration
    REDIS_HOST: str = Field(default="localhost", description="Redis host")
    REDIS_PORT: int = Field(default=6379, description="Redis port")
    REDIS_DB: int = Field(default=0, description="Redis database number")
    REDIS_PASSWORD: Optional[str] = Field(default=None, description="Redis password")

    # AWS S3 Configuration
    AWS_ACCESS_KEY_ID: str = Field(..., description="AWS access key ID")
    AWS_SECRET_ACCESS_KEY: str = Field(..., description="AWS secret access key")
    AWS_REGION: str = Field(default="us-east-1", description="AWS region")
    S3_BUCKET_NAME: str = Field(default="asset-training-frames", description="S3 bucket name")
    S3_FRAMES_PREFIX: str = Field(default="frames/", description="S3 prefix for frames")
    S3_THUMBNAILS_PREFIX: str = Field(default="thumbnails/", description="S3 prefix for thumbnails")

    # Celery Configuration
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None
    CELERY_TASK_TIMEOUT: int = Field(default=7200, description="Task timeout in seconds (2 hours)")
    CELERY_MAX_RETRIES: int = Field(default=3, description="Max retry attempts")
    CELERY_RETRY_BACKOFF: int = Field(default=1, description="Initial retry delay in seconds")

    # Application Configuration
    APP_HOST: str = Field(default="0.0.0.0", description="FastAPI host")
    APP_PORT: int = Field(default=8000, description="FastAPI port")
    DEBUG: bool = Field(default=False, description="Debug mode")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    # File Processing Configuration
    TEMP_VIDEO_DIR: str = Field(default="temp/videos", description="Temporary video storage")
    TEMP_FRAMES_DIR: str = Field(default="temp/frames", description="Temporary frames storage")
    ALLOWED_VIDEO_EXTENSIONS: list = Field(
        default=["mp4", "mov", "avi", "mkv"],
        description="Allowed video file extensions"
    )
    MAX_VIDEO_SIZE_MB: int = Field(default=2048, description="Max video size in MB (2GB)")
    FRAME_EXTRACTION_BATCH_SIZE: int = Field(default=100, description="Frames per checkpoint")
    THUMBNAIL_WIDTH: int = Field(default=320, description="Thumbnail width in pixels")
    THUMBNAIL_HEIGHT: int = Field(default=240, description="Thumbnail height in pixels")

    # WebSocket Configuration
    WS_HEARTBEAT_INTERVAL: int = Field(default=30, description="WebSocket heartbeat interval (seconds)")

    # Google Vertex AI Configuration
    GOOGLE_APPLICATION_CREDENTIALS: str = Field(..., description="Path to Google service account JSON")
    VERTEX_PROJECT: str = Field(..., description="Google Cloud project ID")
    VERTEX_LOCATION: str = Field(default="us-central1", description="Vertex AI location")
    EMBEDDING_DIMENSION: int = Field(default=1408, description="Embedding vector dimension")
    EMBEDDING_TIMEOUT: int = Field(default=60, description="Vertex AI API timeout (seconds)")

    # Qdrant Configuration
    QDRANT_URL: str = Field(default="http://localhost:6333", description="Qdrant server URL")
    QDRANT_API_KEY: Optional[str] = Field(default=None, description="Qdrant API key (if authentication enabled)")
    QDRANT_COLLECTION_NAME: str = Field(default="assets-beta", description="Qdrant collection name")
    QDRANT_DISTANCE_METRIC: str = Field(default="COSINE", description="Distance metric: COSINE, DOT, or EUCLID")

    # Training Configuration
    TRAINING_BATCH_SIZE: int = Field(default=50, description="Frames to process per batch during training")
    TRAINING_RETRY_ATTEMPTS: int = Field(default=3, description="Retry attempts per frame on failure")
    TRAINING_RETRY_BACKOFF: list = Field(default=[1, 5, 15], description="Retry backoff intervals (seconds)")
    CIRCUIT_BREAKER_THRESHOLD: int = Field(default=10, description="Consecutive failures to trigger circuit breaker")
    CIRCUIT_BREAKER_RESET_TIMEOUT: int = Field(default=300, description="Circuit breaker reset timeout (seconds)")
    PARALLEL_EMBEDDING_WORKERS: int = Field(default=5, description="Parallel workers for embedding generation")

    # Email Alert Configuration
    ALERT_EMAIL_ENABLED: bool = Field(default=True, description="Enable email alerts")
    ALERT_EMAIL_TO: str = Field(default="admin@example.com", description="Alert recipient email")
    ALERT_EMAIL_FROM: str = Field(default="noreply@example.com", description="Alert sender email")
    SMTP_HOST: str = Field(default="smtp.gmail.com", description="SMTP server host")
    SMTP_PORT: int = Field(default=587, description="SMTP server port")
    SMTP_USER: str = Field(default="", description="SMTP username")
    SMTP_PASSWORD: str = Field(default="", description="SMTP password")
    SMTP_USE_TLS: bool = Field(default=True, description="Use TLS for SMTP")

    @validator("CELERY_BROKER_URL", pre=True, always=True)
    def set_celery_broker_url(cls, v, values):
        """Auto-generate Celery broker URL from Redis config"""
        if v is None:
            redis_host = values.get("REDIS_HOST", "localhost")
            redis_port = values.get("REDIS_PORT", 6379)
            redis_db = values.get("REDIS_DB", 0)
            redis_password = values.get("REDIS_PASSWORD")

            if redis_password:
                return f"redis://:{redis_password}@{redis_host}:{redis_port}/{redis_db}"
            else:
                return f"redis://{redis_host}:{redis_port}/{redis_db}"
        return v

    @validator("CELERY_RESULT_BACKEND", pre=True, always=True)
    def set_celery_result_backend(cls, v, values):
        """Auto-generate Celery result backend URL from Redis config"""
        if v is None:
            redis_host = values.get("REDIS_HOST", "localhost")
            redis_port = values.get("REDIS_PORT", 6379)
            redis_db = values.get("REDIS_DB", 0)
            redis_password = values.get("REDIS_PASSWORD")

            if redis_password:
                return f"redis://:{redis_password}@{redis_host}:{redis_port}/{redis_db}"
            else:
                return f"redis://{redis_host}:{redis_port}/{redis_db}"
        return v

    @property
    def database_url(self) -> str:
        """Generate SQLAlchemy database URL"""
        return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"

    @property
    def redis_url(self) -> str:
        """Generate Redis connection URL"""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        else:
            return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Create settings instance
settings = Settings()

# Ensure temp directories exist
os.makedirs(settings.TEMP_VIDEO_DIR, exist_ok=True)
os.makedirs(settings.TEMP_FRAMES_DIR, exist_ok=True)
os.makedirs("logs", exist_ok=True)
