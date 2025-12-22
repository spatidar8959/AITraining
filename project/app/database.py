"""
Database connection and session management
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from typing import Generator
from contextlib import contextmanager

from app.config import settings
from app.utils.logger import app_logger


# Create SQLAlchemy engine with connection pooling
engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connections before using
    pool_recycle=3600,  # Recycle connections after 1 hour
    echo=settings.DEBUG,  # Log SQL queries in debug mode
)

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI routes to get database session.

    Usage:
        @app.get("/")
        def route(db: Session = Depends(get_db)):
            ...

    Yields:
        Database session
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        app_logger.error(f"Database session error: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    Context manager for database session (for use in Celery tasks).

    Usage:
        with get_db_context() as db:
            db.query(...)

    Yields:
        Database session
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        app_logger.error(f"Database context error: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()


def create_database():
    """
    Create database if it doesn't exist.
    """
    from sqlalchemy import create_engine, text
    try:
        # Create engine without database name
        temp_url = f"mysql+pymysql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/?charset=utf8mb4"
        temp_engine = create_engine(temp_url)

        with temp_engine.connect() as conn:
            # Create database if not exists
            conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {settings.DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
            conn.commit()

        temp_engine.dispose()
        app_logger.info(f"Database '{settings.DB_NAME}' created/verified successfully")
        return True
    except Exception as e:
        app_logger.error(f"Failed to create database: {str(e)}")
        return False


def init_db():
    """
    Initialize database - create all tables if they don't exist.
    Uses checkfirst=True to avoid errors on existing tables.
    """
    from app.models import Base
    try:
        # First create database
        create_database()

        # Then create all tables (checkfirst=True avoids errors for existing tables)
        Base.metadata.create_all(bind=engine, checkfirst=True)
        app_logger.info("Database tables initialized successfully")
        return True
    except Exception as e:
        app_logger.error(f"Failed to initialize database: {str(e)}")
        return False


def check_db_connection() -> bool:
    """
    Check if database connection is working.

    Returns:
        True if connection successful, False otherwise
    """
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        app_logger.info("Database connection successful")
        return True
    except Exception as e:
        app_logger.error(f"Database connection failed: {str(e)}")
        return False
