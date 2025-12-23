"""
Celery application configuration
"""
from celery import Celery
from app.config import settings

# Create Celery app
celery_app = Celery(
    'asset_training',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=settings.CELERY_TASK_TIMEOUT,
    task_soft_time_limit=settings.CELERY_TASK_TIMEOUT - 300,  # 5 min before hard timeout
    worker_prefetch_multiplier=1,  # Prefetch 1 task at a time for better load balancing
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks to prevent memory leaks (increased for better performance)
    task_acks_late=True,  # Acknowledge task after completion (prevents task loss on worker crash)
    task_reject_on_worker_lost=True,  # Reject task if worker crashes
    result_expires=3600,  # Result expires after 1 hour
    # Concurrency settings for better multi-user support
    worker_disable_rate_limits=False,  # Enable rate limiting for fairness
    task_ignore_result=False,  # Keep results for status tracking
    # Broker connection settings for stability
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
)

# Auto-discover tasks
celery_app.autodiscover_tasks(['app.tasks'])
