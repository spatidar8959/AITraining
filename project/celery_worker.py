"""
Celery worker entry point

For Docker/Linux (recommended for production):
    celery -A celery_worker worker --loglevel=info --concurrency=4 --pool=prefork

For Windows (development only):
    celery -A celery_worker worker --loglevel=info --pool=solo

Note: 
- Use --pool=prefork on Linux/Docker for true concurrency (multiple processes)
- Use --pool=solo on Windows (single-threaded, no true concurrency)
- Concurrency value should match your CPU cores (4-8 recommended)
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
