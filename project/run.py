"""
Asset Training System - Single Command Launcher
Run with: python -B run.py
"""
import os
import sys
import subprocess
import time
import signal
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.config import settings
from app.database import init_db, check_db_connection
from app.utils.logger import app_logger


class ProcessManager:
    """Manages FastAPI server and Celery worker processes"""

    def __init__(self):
        self.processes = []
        self.running = True

    def start_server(self):
        """Start FastAPI server"""
        print("🚀 Starting FastAPI Server on http://localhost:8000...")
        cmd = [
            sys.executable, "-m", "uvicorn",
            "app.main:app",
            "--host", settings.APP_HOST,
            "--port", str(settings.APP_PORT)
        ]
        # Only add --reload if debug mode is on
        if settings.DEBUG:
            cmd.append("--reload")

        process = subprocess.Popen(cmd)
        self.processes.append(("FastAPI Server", process))
        return process

    def start_worker(self):
        """Start Celery worker"""
        print("⚙️  Starting Celery Worker...")
        cmd = [
            sys.executable, "-m", "celery",
            "-A", "celery_worker",
            "worker",
            "--loglevel=info",
            "--pool=solo",  # Windows compatible
            "--concurrency=4"
        ]
        process = subprocess.Popen(cmd)
        self.processes.append(("Celery Worker", process))
        return process

    def stop_all(self):
        """Stop all processes gracefully"""
        print("\n🛑 Shutting down all processes...")
        for name, process in self.processes:
            try:
                print(f"   Stopping {name}...")
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print(f"   Force killing {name}...")
                process.kill()
            except Exception as e:
                print(f"   Error stopping {name}: {e}")

        print("✅ All processes stopped")
        self.running = False

    def handle_signal(self, signum, frame):
        """Handle Ctrl+C signal"""
        self.stop_all()
        sys.exit(0)


def check_prerequisites():
    """Check if all required services are available"""
    print("🔍 Checking prerequisites...\n")

    errors = []

    # Check Python version
    if sys.version_info < (3, 10):
        errors.append("❌ Python 3.10+ is required")
    else:
        print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}")

    # Check MySQL server is running (not database - it will be created)
    try:
        from app.config import settings
        from sqlalchemy import create_engine, text
        # Connect without database name to check if MySQL server is running
        temp_url = f"mysql+pymysql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/?charset=utf8mb4"
        temp_engine = create_engine(temp_url)
        with temp_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        temp_engine.dispose()
        print("✅ MySQL server running")
    except Exception as e:
        errors.append(f"❌ MySQL server not accessible: {str(e)}")

    # Check Redis
    try:
        import redis
        r = redis.from_url(settings.redis_url)
        r.ping()
        print("✅ Redis connection successful")
    except Exception as e:
        errors.append(f"❌ Redis connection failed: {str(e)}")

    # Check FFmpeg
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        if result.returncode == 0:
            print("✅ FFmpeg installed")
        else:
            errors.append("❌ FFmpeg not working properly")
    except FileNotFoundError:
        errors.append("❌ FFmpeg not found in PATH")
    except Exception as e:
        errors.append(f"❌ FFmpeg check failed: {str(e)}")

    # Check S3 credentials
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        print("✅ AWS S3 credentials configured")
    else:
        errors.append("❌ AWS S3 credentials not configured in .env")

    return errors


def setup_database():
    """Initialize database and tables"""
    print("\n📦 Setting up database...\n")

    try:
        # Initialize database and tables
        if init_db():
            print("✅ Database and tables created successfully")
            return True
        else:
            print("❌ Database initialization failed")
            return False
    except Exception as e:
        print(f"❌ Database setup error: {str(e)}")
        return False


def main():
    """Main entry point"""
    print("=" * 60)
    print("   Asset Training System - Production Launcher")
    print("=" * 60)
    print()

    # Check prerequisites
    errors = check_prerequisites()

    if errors:
        print("\n❌ Prerequisites check failed:\n")
        for error in errors:
            print(f"   {error}")
        print("\n📖 Please fix the issues and try again.")
        print("   Check README.md for setup instructions.")
        sys.exit(1)

    # Setup database
    if not setup_database():
        print("\n❌ Database setup failed. Please check logs.")
        sys.exit(1)

    # Create necessary directories
    os.makedirs(settings.TEMP_VIDEO_DIR, exist_ok=True)
    os.makedirs(settings.TEMP_FRAMES_DIR, exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    print("✅ Directories created/verified")

    # Initialize process manager
    manager = ProcessManager()

    # Register signal handlers
    signal.signal(signal.SIGINT, manager.handle_signal)
    signal.signal(signal.SIGTERM, manager.handle_signal)

    print("\n" + "=" * 60)
    print("   Starting Services...")
    print("=" * 60)
    print()

    try:
        # Start FastAPI server
        manager.start_server()
        time.sleep(2)  # Wait for server to start

        # Start Celery worker
        manager.start_worker()
        time.sleep(2)  # Wait for worker to start

        print("\n" + "=" * 60)
        print("   ✅ All Services Started Successfully!")
        print("=" * 60)
        print()
        print(f"   🌐 Web Interface: http://localhost:{settings.APP_PORT}")
        print(f"   📊 Dashboard: http://localhost:{settings.APP_PORT}/api/dashboard")
        print(f"   🔍 Health Check: http://localhost:{settings.APP_PORT}/health")
        print()
        print("   Press Ctrl+C to stop all services")
        print("=" * 60)
        print()

        # Keep running until interrupted
        while manager.running:
            time.sleep(1)

            # Check if any process died
            for name, process in manager.processes:
                if process.poll() is not None:
                    print(f"⚠️  {name} stopped unexpectedly!")
                    manager.stop_all()
                    sys.exit(1)

    except KeyboardInterrupt:
        manager.stop_all()
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        manager.stop_all()
        sys.exit(1)


if __name__ == "__main__":
    main()
