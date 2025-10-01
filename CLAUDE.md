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
- Database-level manifest matching with pre-computed object links for performance
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
- Database-level manifest matching using JOINs vs runtime REGEXP operations
- Pre-computed manifest entry links stored as foreign keys for fast filtering

## Manifest Filtering Architecture

The application implements a sophisticated manifest filtering system for Firefox-style release artifacts:

### Design Evolution
- **Phase 1**: Runtime regex pattern matching against object names (performance bottleneck)
- **Phase 2**: Database-level filtering using pre-computed object-to-manifest-entry links (current)

### Key Components
- **Manifest Parser**: Converts YAML manifests with template variables (${version}, ${build_number}) to regex patterns
- **Object Linking**: Maps stored objects to manifest entries using pattern matching during manifest load
- **Database Schema**: Foreign key relationships (manifest_entry_id) enable fast JOIN operations
- **Filtering Strategies**: Three modes - no filter, matches manifest (JOIN), excludes manifest (IS NULL)

### Template Variable Processing
Manifests use template variables that get converted to regex patterns:
- `${version}` → `\d+\.\d+b?\d?` (matches version numbers like 123.0, 124.0b1)
- `${build_number}` → `\d+` (matches build numbers)
- `${path_platform}` → `[A-Za-z0-9-_]+` (matches platform identifiers)
- `${locale}` → `[A-Za-z-]+` (matches locale codes)

### Performance Benefits
- **Fast Filtering**: JOIN operations vs REGEXP matching (10x+ performance improvement)
- **Scalable**: Works efficiently with thousands of manifest patterns and millions of objects
- **Real-time Updates**: Recalculate manifest matches without re-fetching objects
- **Schema Migration**: Automatically adds manifest tables to existing databases
