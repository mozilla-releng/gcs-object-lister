# Backend Application Directory

This directory contains the Python Flask backend for the GCS Object Lister.

## Structure

- **`main.py`** - Flask application factory and entry point with configuration loading
- **`api/`** - Modular REST API with separated concerns (manifest, fetch routes, utilities)
- **`db.py`** - SQLite database management with REGEXP function, optimized indexes, and size tracking
- **`fetcher.py`** - Background fetch orchestration with live progress updates and size calculation
- **`utils.py`** - Utility functions for formatting, validation, and data transformation

## Architecture

Modular Python design with clear separation of concerns:
- Single-threaded Flask app with background fetch threads
- SQLite per-fetch databases for data isolation with optimized performance
- File-based locking to prevent concurrent fetches
- Custom SQLite REGEXP function for database-level regex filtering
- Modular API structure with blueprint-based organization
- ADC authentication for GCS access

## Key Implementation Details

- **Database Performance**: Custom REGEXP function, multiple indexes, SQL-based filtering/pagination
- **Live Progress**: Record count updates every 1000 objects during fetch
- **Size Management**: Database size calculation and storage in metadata table
- **Memory Efficiency**: Removed raw object metadata storage to reduce database size
- **Filter Support**: Multiple regex patterns with OR logic, date filters, custom_time filters, manifest-based filtering
- **API Architecture**: Separated routes into logical modules (manifest parsing, fetch operations, utilities)
- **Pattern Optimization**: Combines 20+ regex patterns into single OR expressions for performance

## Manifest Filtering Implementation

### Database Schema Extensions
- **manifest table**: Stores manifest metadata (URL, hash, date_added, pattern_count)
- **manifest_entries table**: Stores individual manifest patterns with regex and metadata
- **objects.manifest_entry_id**: Foreign key linking objects to manifest entries
- **Schema Migration**: Automatic table creation for existing databases

### Object Linking Algorithm
```python
def link_objects_to_manifest_entries(db_name: str) -> Dict[str, int]:
    # 1. Clear existing links
    # 2. Fetch all manifest patterns
    # 3. For each object, test against patterns using REGEXP
    # 4. Store first match as manifest_entry_id
    # 5. Return statistics (total_objects, linked_objects)
```

### Filtering Performance Strategies
- **matches_manifest=true**: `INNER JOIN manifest_entries` (fast JOIN operation)
- **matches_manifest=false**: `WHERE manifest_entry_id IS NULL` (indexed lookup)
- **matches_manifest=unset**: No JOIN, returns all objects (fastest)

### Template Variable Processing
Manifest template variables are converted to precise regex patterns:
- Pattern generation uses `re.escape()` for safe literal matching
- Template variables replaced before escaping to preserve regex functionality
- Final patterns anchored with `.*/{pattern}$` for full path matching

### Error Handling & Debugging
- Comprehensive logging during manifest loading and object linking
- Debug endpoint provides schema inspection and link statistics
- Graceful handling of malformed manifests and network errors
- Transaction-based operations for data consistency

Dependencies: Flask, google-cloud-storage, PyYAML, requests, and built-in sqlite3.