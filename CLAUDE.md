# GCS Storage Manager

Local-only web application for managing and exploring Google Cloud Storage artifacts. Built with Python Flask backend and vanilla JavaScript frontend, containerized with Docker.

## Project Structure

- **`project_prompt.md`** - Initial claude prompt to create the project
- **`app/`** - Python Flask backend application
- **`static/`** - Frontend HTML, CSS, and JavaScript assets
- **`requirements.txt`** - Python dependencies (Flask, google-cloud-storage, orjson)
- **`Dockerfile`** - Container build configuration
- **`docker-compose.yml`** - Docker Compose service definition with volume mounting
- **`.env.example`** - Environment configuration template
- **`README.md`** - Complete documentation and usage guide

## Key Features

- Async GCS object fetching with background processing
- SQLite databases for local storage (one per fetch)
- Web interface with pagination, regex filtering, and export
- Real-time fetch status monitoring
- Docker deployment with persistent data volumes

## Development Notes

- Uses Application Default Credentials for GCS authentication
- Single-process Flask app with threading for background tasks
- File-based locking prevents concurrent fetches
- Minimal dependencies for maintainability
