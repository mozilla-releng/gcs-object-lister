# Backend Application Directory

This directory contains the Python Flask backend for the GCS Storage Manager.

## Structure

- **`main.py`** - Flask application factory and entry point with configuration loading
- **`api.py`** - REST API routes and JSON response handling using orjson
- **`db.py`** - SQLite database management, schema creation, and data operations
- **`fetcher.py`** - Background fetch orchestration with thread management and locking
- **`gcs.py`** - Google Cloud Storage client wrapper for object listing and metadata
- **`utils.py`** - Utility functions for formatting, validation, and data transformation

## Architecture

Modular Python design with clear separation of concerns:
- Single-threaded Flask app with background fetch threads
- SQLite per-fetch databases for data isolation
- File-based locking to prevent concurrent fetches
- ADC authentication for GCS access

Dependencies are minimal: Flask, google-cloud-storage, orjson, and built-in sqlite3.