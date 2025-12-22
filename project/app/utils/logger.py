"""
Logging utilities with file rotation and structured logging
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
import json
from datetime import datetime
from typing import Dict, Any, Optional


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields if present
        if hasattr(record, "extra_data"):
            log_data["extra"] = record.extra_data

        return json.dumps(log_data)


def setup_logger(
    name: str,
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    structured: bool = False
) -> logging.Logger:
    """
    Setup logger with file and console handlers.

    Args:
        name: Logger name
        log_file: Path to log file (optional)
        level: Logging level
        max_bytes: Max file size before rotation
        backup_count: Number of backup files to keep
        structured: Use structured JSON logging

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    # Remove existing handlers
    logger.handlers.clear()

    # Create formatters
    if structured:
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler with rotation (if log file specified)
    if log_file:
        # Ensure log directory exists
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def log_with_context(logger: logging.Logger, level: int, message: str, extra_data: Optional[Dict[str, Any]] = None):
    """
    Log message with additional context data.

    Args:
        logger: Logger instance
        level: Log level (e.g., logging.INFO)
        message: Log message
        extra_data: Additional context data
    """
    if extra_data:
        logger.log(level, message, extra={"extra_data": extra_data})
    else:
        logger.log(level, message)


# Default application logger
app_logger = setup_logger(
    name="asset_training",
    log_file="logs/asset_training.log",
    level=logging.INFO,
    structured=False
)

# Celery task logger
celery_logger = setup_logger(
    name="celery_tasks",
    log_file="logs/celery_tasks.log",
    level=logging.INFO,
    structured=False
)
