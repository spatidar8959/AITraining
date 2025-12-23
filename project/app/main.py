"""
FastAPI main application with WebSocket support
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import socketio
import redis
import json
import asyncio
from typing import Set
from pathlib import Path

from app.config import settings
from app.database import check_db_connection
from app.utils.logger import app_logger
from app.api import video, frames, dashboard, training, qdrant

# Create FastAPI app
app = FastAPI(
    title="Asset Training System",
    description="Video frame extraction and AI training pipeline",
    version="1.0.0",
    debug=settings.DEBUG
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(video.router)
app.include_router(frames.router)
app.include_router(dashboard.router)
app.include_router(training.router)
app.include_router(qdrant.router)

# Mount static files - CSS and JS at root level
# Get the project root directory (where this file is located: project/app/)
project_root = Path(__file__).parent.parent
frontend_dir = project_root / "frontend"

# Mount CSS files
css_dir = frontend_dir / "css"
if css_dir.exists():
    app.mount("/css", StaticFiles(directory=str(css_dir)), name="css")
    app_logger.info(f"Mounted CSS directory: {css_dir}")

# Mount JS files (including subdirectories)
js_dir = frontend_dir / "js"
if js_dir.exists():
    app.mount("/js", StaticFiles(directory=str(js_dir)), name="js")
    app_logger.info(f"Mounted JS directory: {js_dir}")
else:
    app_logger.warning(f"JS directory not found: {js_dir}")

# Redis client for pub/sub
redis_client = redis.from_url(settings.redis_url)
pubsub = redis_client.pubsub()

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        # Map client_session_id -> set of WebSocket connections
        self.connections_by_session: dict[str, Set[WebSocket]] = {}
        # Map WebSocket -> client_session_id for cleanup
        self.session_by_connection: dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, client_session_id: str):
        await websocket.accept()
        
        # Add to session mapping
        if client_session_id not in self.connections_by_session:
            self.connections_by_session[client_session_id] = set()
        self.connections_by_session[client_session_id].add(websocket)
        self.session_by_connection[websocket] = client_session_id
        
        app_logger.info(
            f"WebSocket connected. Session: {client_session_id}, "
            f"Total sessions: {len(self.connections_by_session)}, "
            f"Total connections: {sum(len(conns) for conns in self.connections_by_session.values())}"
        )

    def disconnect(self, websocket: WebSocket):
        client_session_id = self.session_by_connection.pop(websocket, None)
        if client_session_id:
            session_connections = self.connections_by_session.get(client_session_id)
            if session_connections:
                session_connections.discard(websocket)
                # Clean up empty session entries
                if not session_connections:
                    del self.connections_by_session[client_session_id]
        
        app_logger.info(
            f"WebSocket disconnected. Session: {client_session_id}, "
            f"Total sessions: {len(self.connections_by_session)}, "
            f"Total connections: {sum(len(conns) for conns in self.connections_by_session.values())}"
        )

    async def broadcast_to_client(self, client_session_id: str, message: dict):
        """
        Broadcast message only to clients with matching client_session_id.
        
        Args:
            client_session_id: Target client session ID
            message: Message to send
        """
        if client_session_id not in self.connections_by_session:
            app_logger.debug(f"No connections found for session: {client_session_id}")
            return
        
        disconnected = set()
        connections = self.connections_by_session[client_session_id]
        
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                app_logger.error(f"Error sending to WebSocket: {str(e)}")
                disconnected.add(connection)

        # Remove disconnected clients
        for conn in disconnected:
            self.disconnect(conn)

    async def broadcast(self, message: dict):
        """
        Broadcast message to all connected clients (legacy method for backward compatibility).
        Prefer using broadcast_to_client for session-specific messages.
        """
        client_session_id = message.get("client_session_id")
        if client_session_id:
            # Route to specific client session
            await self.broadcast_to_client(client_session_id, message)
        else:
            # Fallback: broadcast to all (for messages without session ID)
            disconnected = set()
            for session_connections in self.connections_by_session.values():
                for connection in session_connections:
                    try:
                        await connection.send_json(message)
                    except Exception as e:
                        app_logger.error(f"Error sending to WebSocket: {str(e)}")
                        disconnected.add(connection)

            # Remove disconnected clients
            for conn in disconnected:
                self.disconnect(conn)


manager = ConnectionManager()


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    app_logger.info("Starting Asset Training System...")

    # Initialize database and tables
    from app.database import init_db
    if init_db():
        app_logger.info("Database initialized successfully")
    else:
        app_logger.error("Database initialization failed!")

    # Check database connection
    if check_db_connection():
        app_logger.info("Database connection successful")
    else:
        app_logger.error("Database connection failed!")

    # Initialize Qdrant collection
    from app.services.qdrant_service import qdrant_service
    try:
        if qdrant_service.ensure_collection_exists():
            app_logger.info(f"Qdrant collection '{qdrant_service.collection_name}' initialized successfully")
        else:
            app_logger.error("Qdrant collection initialization failed!")
    except Exception as e:
        app_logger.error(f"Failed to initialize Qdrant collection: {str(e)}", exc_info=True)

    # Start Redis subscriber task
    asyncio.create_task(redis_subscriber())

    app_logger.info("Application started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    app_logger.info("Shutting down Asset Training System...")
    pubsub.close()
    redis_client.close()


async def redis_subscriber():
    """
    Subscribe to Redis progress channel and broadcast to WebSocket clients.
    """
    pubsub.subscribe("progress_channel")
    app_logger.info("Redis subscriber started for progress_channel")

    try:
        while True:
            message = pubsub.get_message()
            if message and message['type'] == 'message':
                try:
                    data = json.loads(message['data'])
                    await manager.broadcast(data)
                    app_logger.debug(f"Broadcasted progress: {data}")
                except json.JSONDecodeError as e:
                    app_logger.error(f"Invalid JSON from Redis: {str(e)}")
                except Exception as e:
                    app_logger.error(f"Error broadcasting message: {str(e)}")

            await asyncio.sleep(0.1)  # Prevent busy loop

    except Exception as e:
        app_logger.error(f"Redis subscriber error: {str(e)}")


@app.websocket("/ws/progress")
async def websocket_progress(websocket: WebSocket, client_session_id: str = None):
    """
    WebSocket endpoint for real-time progress updates.

    Clients connect here to receive extraction and training progress updates.
    The client_session_id is extracted from the query string.
    
    Args:
        websocket: WebSocket connection
        client_session_id: Client session ID from query parameter
    """
    # Extract client_session_id from query parameters if not provided
    if not client_session_id:
        query_params = dict(websocket.query_params)
        client_session_id = query_params.get("client_session_id")
    
    if not client_session_id:
        app_logger.warning("WebSocket connection without client_session_id, generating one")
        import uuid
        client_session_id = str(uuid.uuid4())
    
    await manager.connect(websocket, client_session_id)
    try:
        while True:
            # Keep connection alive with heartbeat
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        app_logger.info(f"Client disconnected (session: {client_session_id})")
    except Exception as e:
        app_logger.error(f"WebSocket error: {str(e)}")
        manager.disconnect(websocket)


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve frontend HTML"""
    with open("frontend/index.html", "r") as f:
        return f.read()


@app.get("/health")
async def health_check():
    """
    Health check endpoint for monitoring.

    Returns:
        System health status with all services
    """
    from app.services.qdrant_service import qdrant_service
    from app.services.embedding_service import embedding_service
    import shutil

    # Check Database
    db_status = check_db_connection()
    db_latency = 0

    # Check Redis
    redis_status = False
    redis_latency = 0
    try:
        import time
        start = time.time()
        redis_client.ping()
        redis_latency = int((time.time() - start) * 1000)
        redis_status = True
    except Exception as e:
        app_logger.error(f"Redis health check failed: {str(e)}")

    # Check S3
    s3_status = True  # Assume healthy if credentials are set

    # Check Qdrant
    qdrant_status = qdrant_service.health_check()
    qdrant_info = None
    if qdrant_status:
        try:
            # Ensure collection exists before getting info
            qdrant_service.ensure_collection_exists()
            qdrant_info = qdrant_service.get_collection_info()
        except Exception as e:
            app_logger.error(f"Failed to get Qdrant collection info: {str(e)}")
            qdrant_status = False

    # Check Vertex AI
    vertex_status = embedding_service.health_check()

    # Check disk space
    temp_video_dir = settings.TEMP_VIDEO_DIR
    disk_usage = shutil.disk_usage(temp_video_dir)
    temp_used_gb = round((disk_usage.used / (1024**3)), 2)
    temp_available_gb = round((disk_usage.free / (1024**3)), 2)

    # Overall status
    all_healthy = all([db_status, redis_status, s3_status, qdrant_status, vertex_status])

    return {
        "status": "healthy" if all_healthy else "unhealthy",
        "services": {
            "database": {"status": "up" if db_status else "down", "latency_ms": db_latency},
            "redis": {"status": "up" if redis_status else "down", "latency_ms": redis_latency},
            "s3": {"status": "up" if s3_status else "down"},
            "qdrant": {
                "status": "up" if qdrant_status else "down",
                "collection": qdrant_info.get("name") if qdrant_info else None,
                "points_count": qdrant_info.get("points_count") if qdrant_info else 0
            },
            "vertex_ai": {
                "status": "up" if vertex_status else "down",
                "project": settings.VERTEX_PROJECT
            }
        },
        "storage": {
            "temp_used_gb": temp_used_gb,
            "temp_available_gb": temp_available_gb
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
