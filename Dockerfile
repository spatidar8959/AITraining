# Multi-stage build for smaller final image
FROM python:3.13-slim AS builder

# Install system dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Enable bytecode compilation for faster startup
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies (no-install-project for better caching)
# Don't use --locked to allow fresh dependency resolution
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project --no-dev

# Production stage
FROM python:3.13-slim

# Install runtime dependencies only (FFmpeg for video processing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    wget \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install uv in production image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy dependency files for uv sync
COPY pyproject.toml ./

# Sync project (installs project itself)
# Don't use --locked to allow fresh dependency resolution
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev

# Copy project files
COPY project/ /app/project/

# Activate virtual environment
ENV PATH="/app/.venv/bin:$PATH"

# Python optimizations
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONOPTIMIZE=1 \
    UV_COMPILE_BYTECODE=1

# Create necessary directories with proper permissions
RUN mkdir -p /app/project/logs /app/project/temp/videos /app/project/temp/frames && \
    chmod -R 755 /app/project/logs /app/project/temp

# Change to project directory
WORKDIR /app/project

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=5).raise_for_status()" || exit 1

# Default command (can be overridden in docker-compose)
CMD ["python", "-B", "run.py"]
