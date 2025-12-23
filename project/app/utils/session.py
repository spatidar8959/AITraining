"""
Session management utilities for client session tracking
"""
from fastapi import Header, Request
from typing import Optional
import uuid

from app.utils.logger import app_logger


def get_client_session_id(
    x_client_session_id: Optional[str] = Header(None, alias="X-Client-Session-Id")
) -> str:
    """
    Extract client session ID from request header or generate a new one.
    
    This dependency can be used in FastAPI routes to get the client's session ID.
    If not provided in headers, generates a new UUID for this request.
    
    Args:
        x_client_session_id: Optional client session ID from X-Client-Session-Id header
        
    Returns:
        Client session ID string
    """
    if x_client_session_id:
        return x_client_session_id
    
    # Generate a new session ID if not provided
    new_session_id = str(uuid.uuid4())
    app_logger.debug(f"Generated new client session ID: {new_session_id}")
    return new_session_id


def get_request_id() -> str:
    """
    Generate a unique request ID for tracking a single request through the system.
    
    Returns:
        Request ID string (UUID)
    """
    return str(uuid.uuid4())

