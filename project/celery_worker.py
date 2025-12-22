"""
Celery worker entry point
Run with: celery -A celery_worker worker --loglevel=info --concurrency=4 --pool=solo
Note: On Windows, use --pool=solo
"""
from app.celery_app import celery_app
from app.config import settings
from app.utils.logger import celery_logger

# Import tasks to register them
from app.tasks import extraction, training

celery_logger.info("Celery worker initialized")
celery_logger.info(f"Broker: {settings.CELERY_BROKER_URL}")
celery_logger.info(f"Backend: {settings.CELERY_RESULT_BACKEND}")

if __name__ == '__main__':
    celery_app.start()
