# GCS Storage Manager

A local-only web application for managing and exploring artifacts in Google Cloud Storage (GCS) buckets. This tool allows you to fetch object listings from GCS buckets, store them locally in SQLite databases, and explore them through a web interface.

## Features

- **Fetch GCS objects**: Asynchronously fetch complete object listings from GCS buckets
- **Local storage**: Store fetches in SQLite databases for offline exploration
- **Web interface**: Browse objects with pagination, regex filtering, and sorting
- **Export functionality**: Download filtered object lists as text files
- **Multiple fetches**: Manage multiple fetch sessions with historical tracking
- **Real-time status**: Monitor fetch progress with live updates

## Quick Start

1. **Prerequisites**
   - Docker and Docker Compose
   - Google Cloud CLI (`gcloud`) installed and authenticated
   - Access to a GCS bucket

2. **Authentication Setup**
   ```bash
   # Login to Google Cloud and set up Application Default Credentials
   gcloud auth login --update-adc
   ```

3. **Configuration**
   ```bash
   # Copy environment configuration
   cp .env.example .env

   # Edit .env and set your bucket name
   nano .env
   ```

   Set `BUCKET_NAME` to your GCS bucket name:
   ```
   BUCKET_NAME=your-gcs-bucket-name
   ```

4. **Run the Application**
   ```bash
   # Build and start the application
   docker compose up --build
   ```

5. **Access the Web Interface**
   - Open your browser to [http://localhost:8080](http://localhost:8080)
   - Click "Fetch Current Files" to start fetching objects from your bucket
   - Monitor progress and explore fetched objects

## Configuration Options

The application is configured via environment variables in the `.env` file:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BUCKET_NAME` | Yes* | - | Default GCS bucket name to fetch from |
| `GCS_PREFIX` | No | - | Optional prefix filter for objects |
| `APP_HOST` | No | `0.0.0.0` | Application host interface |
| `APP_PORT` | No | `8080` | Application port |
| `DATA_DIR` | No | `/data/fetches` | Directory for storing SQLite databases |

*Required unless provided in fetch requests

## Data Storage

- **Location**: SQLite databases stored in Docker volume `data`
- **Format**: One database per fetch, named with UTC timestamp (e.g., `2025-08-18T14-32-10Z.db`)
- **Content**: Complete GCS object metadata including name, size, timestamps, and full blob properties
- **Persistence**: Data persists across container restarts via Docker volume

### Database Schema

Each fetch database contains:

- **`fetch` table**: Single row with fetch metadata (bucket, status, timing, counts)
- **`objects` table**: One row per GCS object with name, size, timestamps, and raw metadata

## API Reference

### Health Check
```
GET /api/health
Response: {"status": "ok"}
```

### Fetch Status
```
GET /api/status
Response: {
  "running": boolean,
  "started_at"?: string,
  "db_name"?: string,
  "processed"?: number,
  "message"?: string
}
```

### Start Fetch
```
POST /api/fetches
Body: {
  "bucket"?: string,  // Optional override
  "prefix"?: string   // Optional filter
}
Response: {
  "db_name": string,
  "started_at": string
}
```

### List Fetches
```
GET /api/fetches
Response: Array of fetch objects with:
{
  "db_name": string,
  "bucket_name": string,
  "prefix": string|null,
  "started_at": string,
  "ended_at": string|null,
  "record_count": number,
  "status": "running"|"success"|"error"|"canceled",
  "error": string|null
}
```

### Delete Fetch
```
DELETE /api/fetches/{db_name}
Response: {"message": "deleted"}
```

### List Objects
```
GET /api/fetches/{db_name}/objects?regex={pattern}&page={num}&page_size={size}&sort={order}
Parameters:
- regex: Optional regex filter (Python re syntax)
- page: Page number (default: 1)
- page_size: Items per page (default: 200, max: 1000)
- sort: name_asc (default) or name_desc

Response: {
  "items": Array of {"name": string, "size": number, "updated": string},
  "total": number,
  "page": number,
  "page_size": number
}
```

### Download Object List
```
GET /api/fetches/{db_name}/download?regex={pattern}
Parameters:
- regex: Optional regex filter

Response: Plain text file (Content-Type: text/plain)
One object name per line
```

## Troubleshooting

### Permission Denied Errors
```bash
# Ensure you're logged in with Application Default Credentials
gcloud auth application-default login

# Check your credentials are working
gcloud auth application-default print-access-token
```

### Bucket Access Issues
```bash
# Verify bucket exists and you have access
gsutil ls gs://your-bucket-name

# Check bucket permissions
gsutil iam get gs://your-bucket-name
```

### Windows Credentials Path
If you're on Windows, modify `docker-compose.yml` to use the Windows credentials path:
```yaml
volumes:
  # Windows path for gcloud credentials
  - ${USERPROFILE}/.config/gcloud:/root/.config/gcloud:ro
```

### Container Won't Start
- Check that port 8080 isn't already in use
- Verify Docker and Docker Compose are installed
- Check the logs: `docker compose logs app`

### Large Bucket Performance
- The tool is designed for large buckets and may run for extended periods
- Monitor progress through the web interface
- Each object requires one API call to get full metadata
- Consider using `GCS_PREFIX` to limit scope if needed

## Data Management

### Viewing Stored Data
- Each fetch creates a timestamped SQLite database
- Databases are stored in the Docker volume `data`
- Use the web interface to explore historical fetches

### Cleaning Up Data
```bash
# Stop the application
docker compose down

# Remove all data (WARNING: This deletes all fetches)
docker volume rm gcs-storage-manager_data

# Or selectively delete through the web interface
```

### Backup Data
```bash
# Backup the entire data volume
docker run --rm -v gcs-storage-manager_data:/data -v $(pwd):/backup alpine tar czf /backup/gcs-data-backup.tar.gz -C /data .

# Restore from backup
docker run --rm -v gcs-storage-manager_data:/data -v $(pwd):/backup alpine tar xzf /backup/gcs-data-backup.tar.gz -C /data
```

## Manual Testing Plan

### Basic Functionality
1. **Start Application**
   - `docker compose up --build`
   - Verify startup logs show correct configuration
   - Access http://localhost:8080

2. **Trigger Fetch**
   - Click "Fetch Current Files"
   - Verify button becomes disabled with spinner
   - Observe status updates every 2 seconds
   - Verify fetch appears in historical list

3. **Concurrent Fetch Test**
   - Try starting another fetch while one is running
   - Verify 409 error message is displayed
   - Confirm only one fetch runs at a time

4. **Explore Fetch Results**
   - Click "Open" on completed fetch
   - Verify object list loads with pagination
   - Test regex filtering with patterns like:
     - `\.jpg$` (JPEG files)
     - `^logs/` (files in logs directory)
     - `2024.*\.json$` (2024 JSON files)
   - Test invalid regex patterns and verify error handling

5. **Download Functionality**
   - Apply a regex filter
   - Click "Download File List"
   - Verify file downloads with correct filtered contents
   - Check filename format: `{db_name}_files.txt`

6. **Delete Fetch**
   - Try deleting a running fetch (should be blocked)
   - Delete a completed fetch
   - Verify confirmation dialog
   - Confirm fetch disappears from list

7. **Navigation**
   - Test back/forward browser navigation
   - Verify direct URLs work: `http://localhost:8080/{db_name}`

### Error Conditions
1. **Invalid Database Names**
   - Try accessing `/invalid..name` (should show 400 error)
   - Try accessing non-existent fetch (should show 404)

2. **Network Issues**
   - Stop internet connection during fetch
   - Verify error handling and status updates

3. **Permission Issues**
   - Test with invalid bucket name
   - Test with bucket you don't have access to

## Architecture

- **Backend**: Python Flask with minimal dependencies
- **Frontend**: Plain HTML/CSS/JS with Pico.css styling
- **Database**: SQLite for local storage
- **Authentication**: Google Cloud Application Default Credentials
- **Deployment**: Docker with volume persistence

The application is designed for local development and testing use cases, prioritizing simplicity and reliability over scalability.
