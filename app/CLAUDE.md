# Backend Application Directory

This directory contains the Python Flask backend for the GCS Storage Manager.

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

Dependencies: Flask, google-cloud-storage, PyYAML, requests, and built-in sqlite3.