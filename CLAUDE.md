# GCS Storage Manager

Local-only web application for managing and exploring Google Cloud Storage artifacts. Built with Python Flask backend and vanilla JavaScript frontend, containerized with Docker.

## Project Structure

- **`project_prompt.md`** - Initial claude prompt to create the project
- **`app/`** - Python Flask backend application with modular API structure
- **`static/`** - Frontend HTML, CSS, and JavaScript assets
- **`assets/`** - Example files and test data (e.g., example.manifest.yml)
- **`requirements.txt`** - Python dependencies (Flask, google-cloud-storage, PyYAML, requests)
- **`Dockerfile`** - Container build configuration
- **`docker-compose.yml`** - Docker Compose service definition with volume mounting
- **`.env.example`** - Environment configuration template
- **`README.md`** - Complete documentation and usage guide

## Key Features

- Async GCS object fetching with background processing and live progress tracking
- SQLite databases for local storage (one per fetch) with optimized indexes
- Web interface with pagination, multiple regex filtering (OR logic), date/custom_time filters
- Manifest-based filtering for Firefox-style release artifacts with template variable substitution
- Real-time fetch status monitoring with object count updates
- Database size calculation and display for storage management
- Docker deployment with persistent data volumes

## Development Notes

- Uses Application Default Credentials for GCS authentication
- Single-process Flask app with threading for background tasks
- File-based locking prevents concurrent fetches
- SQLite REGEXP function for database-level filtering performance
- Modular API architecture with separated concerns (manifest, fetch, utils)
- Minimal dependencies for maintainability
- Optimized database schema without raw metadata storage

## Performance Optimizations

- Database indexes on name, time_created, custom_time, and composite indexes
- SQL-based filtering and pagination instead of Python-level processing
- Custom SQLite REGEXP function for efficient regex matching
- Regex pattern optimization (combines 20+ patterns into single OR expressions)
- Batch processing with live progress updates every 1000 objects
- Manifest filtering with template variable regex substitution
