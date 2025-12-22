# AI Training System

A comprehensive video processing and AI training system that extracts video frames, generates embeddings using Google Vertex AI, and stores them in Qdrant vector database.

## 📋 Table of Contents

- [Prerequisites](#prerequisites)
- [Project Structure](#project-structure)
- [Setup Instructions](#setup-instructions)
- [Configuration](#configuration)
- [Docker Commands](#docker-commands)
- [Accessing the Application](#accessing-the-application)
- [Troubleshooting](#troubleshooting)

## 🔧 Prerequisites

The following software must be installed on your system:

- **Docker** (version 20.10 or higher)
- **Docker Compose** (version 2.0 or higher)
- **Git** (for cloning the project)

## 📁 Project Structure

```
AITraining/
├── project/
│   ├── app/                    # Main application code
│   ├── frontend/               # Frontend files
│   ├── .env                    # Environment variables (create this)
│   └── cogent-tine-468410-k7-a3e226214d9a.json  # Google credentials (place here)
├── docker-compose.yml          # Docker Compose configuration
├── Dockerfile                  # Docker image definition
├── pyproject.toml              # Python dependencies
└── README.md                   # This file
```

## 🚀 Setup Instructions

### Step 1: Clone the Repository

```bash
git clone <repository-url>
cd AITraining
```

### Step 2: Create `.env` File

Create a `.env` file inside the `project/` folder:

```bash
# Windows PowerShell
New-Item -Path "project\.env" -ItemType File

# Linux/Mac
touch project/.env
```

### Step 3: Configure Environment Variables

Add the following variables to the `project/.env` file:

```env
# Database Configuration
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=Mysql12345
DB_NAME=asset_training

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=Redis12345

# AWS S3 Configuration (Required)
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
AWS_REGION=us-east-1
S3_BUCKET_NAME=asset-training-frames
S3_FRAMES_PREFIX=frames/
S3_THUMBNAILS_PREFIX=thumbnails/

# Google Vertex AI Configuration (Required)
VERTEX_PROJECT=your-google-cloud-project-id
VERTEX_LOCATION=us-central1
GOOGLE_APPLICATION_CREDENTIALS=/app/project/cogent-tine-468410-k7-a3e226214d9a.json

# Qdrant Configuration
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION_NAME=assets-beta

# Application Configuration
APP_HOST=0.0.0.0
APP_PORT=8000
DEBUG=false
LOG_LEVEL=INFO

# Email Alert Configuration (Optional)
ALERT_EMAIL_ENABLED=false
ALERT_EMAIL_TO=admin@example.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
```

### Step 4: Place Google Credentials JSON File

Place your Google Cloud service account credentials JSON file in the `project/` folder:

**File Location:** `project/cogent-tine-468410-k7-a3e226214d9a.json`

**Important Notes:**
- The file name should be `cogent-tine-468410-k7-a3e226214d9a.json` (or update the path in docker-compose.yml)
- Download this file from Google Cloud Console
- The file must have proper service account permissions (Vertex AI access)

### Step 5: Build Docker Images

```bash
docker-compose build
```

For the first build or after updating dependencies:

```bash
docker-compose build --no-cache
```

## 🐳 Docker Commands

### Start All Services

```bash
docker-compose up
```

To run in the background:

```bash
docker-compose up -d
```

### Stop All Services

```bash
docker-compose down
```

### View Logs

To view logs from all services:

```bash
docker-compose logs -f
```

For logs from a specific service:

```bash
# API logs
docker-compose logs -f aitraining-api

# Worker logs
docker-compose logs -f aitraining-worker

# MySQL logs
docker-compose logs -f aitraining-mysql

# Redis logs
docker-compose logs -f aitraining-redis

# Qdrant logs
docker-compose logs -f aitraining-qdrant
```

### Restart Services

```bash
# Restart all services
docker-compose restart

# Restart specific service
docker-compose restart aitraining-api
```

### Rebuild and Restart

```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Check Service Status

```bash
docker-compose ps
```

### Execute Commands in Container

```bash
# Run command in API container
docker-compose exec aitraining-api bash

# Run command in Worker container
docker-compose exec aitraining-worker bash
```

## 🌐 Accessing the Application

### Web Interface

After starting the application, open in your browser:

```
http://localhost:8000
```

### API Documentation

FastAPI automatic documentation:

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

### Health Check

```bash
curl http://localhost:8000/health
```

### Service Ports

- **FastAPI Application:** `8000`
- **MySQL Database:** `3307` (on host machine)
- **Redis:** `6379` (on host machine)
- **Qdrant:** `6333` (HTTP), `6334` (gRPC)

## 🔍 Troubleshooting

### Issue: ModuleNotFoundError

**Error:** `ModuleNotFoundError: No module named 'pydantic_settings'`

**Solution:**
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up
```

### Issue: Database Connection Failed

**Error:** MySQL connection error

**Solution:**
1. Check if MySQL container is healthy: `docker-compose ps`
2. Verify correct database credentials in `.env` file
3. Restart MySQL container: `docker-compose restart aitraining-mysql`

### Issue: Google Credentials Not Found

**Error:** `GOOGLE_APPLICATION_CREDENTIALS` file not found

**Solution:**
1. Verify that JSON file exists in `project/` folder
2. Check if file name is correct
3. Check file permissions (should be readable)

### Issue: Port Already in Use

**Error:** Port 8000 already in use

**Solution:**
1. Change `APP_PORT` in `docker-compose.yml`
2. Or stop the existing service using that port

### View Container Logs

```bash
# Real-time logs
docker-compose logs -f

# Last 100 lines
docker-compose logs --tail=100
```

### Clean Up Everything

**Warning:** This command will delete all containers, volumes, and data:

```bash
docker-compose down -v
```

## 📝 Additional Notes

- **Database Data:** MySQL data persists in `aitraining_mysql_data` volume
- **Redis Data:** Redis data persists in `aitraining_redis_data` volume
- **Qdrant Data:** Qdrant data persists in `aitraining_qdrant_data` volume
- **Logs:** Application logs are available in `logs/` folder
- **Temp Files:** Temporary video and frame files are stored in `temp/` folder

## 🛠️ Development

For local development:

```bash
# Install dependencies locally
pip install -r requirements.txt

# Run application locally (MySQL, Redis, Qdrant should be running in Docker)
python project/run.py
```

## 📞 Support

For issues or questions, please create an issue in the GitHub Issues section.
