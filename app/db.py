"""Database utilities for SQLite operations."""

import os
import sqlite3
import logging
import re
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, List, Optional, Any

from .utils import format_timestamp, safe_db_name

logger = logging.getLogger(__name__)


def _regexp_function(pattern: str, text: str) -> int:
    """Custom REGEXP function for SQLite."""
    try:
        if not pattern or not text:
            return 0
        return 1 if re.search(pattern, text) else 0
    except re.error:
        return 0


class DatabaseManager:
    """Manages SQLite databases for fetch operations."""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

    def get_db_path(self, db_name: str) -> str:
        """Get full path to database file."""
        if not safe_db_name(db_name):
            raise ValueError(f"Invalid database name: {db_name}")
        return os.path.join(self.data_dir, f"{db_name}.db")

    def create_fetch_db(self, db_name: str, bucket_name: str, prefix: Optional[str], started_at: datetime) -> str:
        """Create a new fetch database with schema."""
        db_path = self.get_db_path(db_name)

        with self.get_connection(db_path) as conn:
            # Create tables
            conn.execute("""
                CREATE TABLE fetch (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    bucket_name TEXT NOT NULL,
                    prefix TEXT,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    record_count INTEGER DEFAULT 0,
                    db_size_mb REAL DEFAULT 0.0,
                    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'error', 'canceled')),
                    error TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE objects (
                    name TEXT PRIMARY KEY,
                    size INTEGER NOT NULL,
                    updated TEXT NOT NULL,
                    time_created TEXT,
                    custom_time TEXT
                )
            """)

            # Create indexes for efficient filtering and sorting
            conn.execute("CREATE INDEX idx_objects_name ON objects(name)")
            conn.execute("CREATE INDEX idx_objects_time_created ON objects(time_created)")
            conn.execute("CREATE INDEX idx_objects_custom_time ON objects(custom_time)")
            
            # Composite indexes for common query patterns
            conn.execute("CREATE INDEX idx_objects_time_created_name ON objects(time_created, name)")
            conn.execute("CREATE INDEX idx_objects_custom_time_name ON objects(custom_time, name)")

            # Insert initial fetch record
            conn.execute("""
                INSERT INTO fetch (id, bucket_name, prefix, started_at, status)
                VALUES (1, ?, ?, ?, 'running')
            """, (bucket_name, prefix, format_timestamp(started_at)))

            conn.commit()

        return db_path

    @contextmanager
    def get_connection(self, db_path: str):
        """Get database connection with proper configuration."""
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.create_function("REGEXP", 2, _regexp_function, deterministic=True)
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def get_bulk_connection(self, db_path: str):
        """Get database connection optimized for bulk operations."""
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.create_function("REGEXP", 2, _regexp_function, deterministic=True)

        # Optimize for bulk inserts
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = OFF")
        conn.execute("PRAGMA cache_size = 10000")

        try:
            yield conn
        finally:
            # Restore safe settings
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.close()

    def list_fetches(self) -> List[Dict[str, Any]]:
        """List all available fetches by scanning database files."""
        fetches = []

        for filename in os.listdir(self.data_dir):
            if filename.endswith(".db"):
                db_name = filename[:-3]  # Remove .db extension
                db_path = os.path.join(self.data_dir, filename)

                try:
                    with self.get_connection(db_path) as conn:
                        row = conn.execute("SELECT * FROM fetch WHERE id = 1").fetchone()
                        if row:
                            fetch_info = {
                                "db_name": db_name,
                                "bucket_name": row["bucket_name"],
                                "prefix": row["prefix"],
                                "started_at": row["started_at"],
                                "ended_at": row["ended_at"],
                                "record_count": row["record_count"],
                                "db_size_mb": row["db_size_mb"],
                                "status": row["status"],
                                "error": row["error"]
                            }
                            fetches.append(fetch_info)
                except Exception as e:
                    logger.warning(f"Failed to read fetch info from {filename}: {e}")

        # Sort by started_at descending
        fetches.sort(key=lambda x: x["started_at"], reverse=True)
        return fetches

    def get_fetch_info(self, db_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific fetch."""
        if not safe_db_name(db_name):
            return None

        db_path = self.get_db_path(db_name)
        if not os.path.exists(db_path):
            return None

        try:
            with self.get_connection(db_path) as conn:
                row = conn.execute("SELECT * FROM fetch WHERE id = 1").fetchone()
                if row:
                    return {
                        "db_name": db_name,
                        "bucket_name": row["bucket_name"],
                        "prefix": row["prefix"],
                        "started_at": row["started_at"],
                        "ended_at": row["ended_at"],
                        "record_count": row["record_count"],
                        "db_size_mb": row["db_size_mb"],
                        "status": row["status"],
                        "error": row["error"]
                    }
        except Exception as e:
            logger.warning(f"Failed to read fetch info from {db_name}: {e}")

        return None

    def update_fetch_status(self, db_name: str, status: str, ended_at: Optional[datetime] = None,
                           record_count: Optional[int] = None, error: Optional[str] = None,
                           db_size_mb: Optional[float] = None):
        """Update fetch status and related fields."""
        db_path = self.get_db_path(db_name)

        with self.get_connection(db_path) as conn:
            updates = ["status = ?"]
            params = [status]

            if ended_at:
                updates.append("ended_at = ?")
                params.append(format_timestamp(ended_at))

            if record_count is not None:
                updates.append("record_count = ?")
                params.append(record_count)

            if error is not None:
                updates.append("error = ?")
                params.append(error)

            if db_size_mb is not None:
                updates.append("db_size_mb = ?")
                params.append(db_size_mb)

            query = f"UPDATE fetch SET {', '.join(updates)} WHERE id = 1"
            conn.execute(query, params)
            conn.commit()

    def insert_objects_batch(self, db_name: str, objects: List[Dict[str, Any]]):
        """Insert a batch of objects into the database."""
        db_path = self.get_db_path(db_name)

        with self.get_bulk_connection(db_path) as conn:
            data = []
            for obj in objects:
                data.append((obj["name"], obj["size"], obj["updated"], obj.get("time_created"), obj.get("custom_time")))

            conn.executemany(
                "INSERT OR REPLACE INTO objects (name, size, updated, time_created, custom_time) VALUES (?, ?, ?, ?, ?)",
                data
            )
            conn.commit()

    def get_objects_page(self, db_name: str, page: int = 1, page_size: int = 200,
                        regex_filter: Optional[str] = None, sort: str = "name_asc",
                        created_before: Optional[str] = None, has_custom_time: Optional[str] = None,
                        regex_filters: Optional[List[str]] = None) -> Dict[str, Any]:
        """Get paginated objects with optional filtering."""
        db_path = self.get_db_path(db_name)
        offset = (page - 1) * page_size

        # Build WHERE clause conditions
        where_conditions = []
        params = []

        # Handle regex filters with OR logic
        all_regex_patterns = []
        if regex_filter:
            all_regex_patterns.append(regex_filter)
        if regex_filters:
            all_regex_patterns.extend([f for f in regex_filters if f])

        if all_regex_patterns:
            regex_conditions = []
            for pattern in all_regex_patterns:
                regex_conditions.append("name REGEXP ?")
                params.append(pattern)
            where_conditions.append(f"({' OR '.join(regex_conditions)})")

        # Date filter (created before)
        if created_before:
            where_conditions.append("time_created < ?")
            params.append(created_before)

        # Custom time filter
        if has_custom_time:
            filter_value = has_custom_time.lower() in ['true', 'yes']
            if filter_value:
                where_conditions.append("custom_time IS NOT NULL")
            else:
                where_conditions.append("custom_time IS NULL")

        # Build ORDER BY clause
        if sort == "name_desc":
            order_by = "ORDER BY name DESC"
        elif sort == "time_created_desc":
            order_by = "ORDER BY time_created DESC"
        elif sort == "time_created_asc":
            order_by = "ORDER BY time_created ASC"
        else:  # name_asc
            order_by = "ORDER BY name ASC"

        # Build complete WHERE clause
        where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""

        with self.get_connection(db_path) as conn:
            # Get total count
            count_query = f"SELECT COUNT(*) FROM objects {where_clause}"
            total = conn.execute(count_query, params).fetchone()[0]

            # Get paginated results
            data_query = f"""
                SELECT name, size, updated, time_created, custom_time
                FROM objects
                {where_clause}
                {order_by}
                LIMIT ? OFFSET ?
            """
            data_params = params + [page_size, offset]
            logger.info(f"Executing query: {data_query} with params: {data_params}")
            rows = conn.execute(data_query, data_params).fetchall()

            # Convert to list of dicts
            items = []
            for row in rows:
                items.append({
                    "name": row["name"],
                    "size": row["size"],
                    "updated": row["updated"],
                    "time_created": row["time_created"],
                    "custom_time": row["custom_time"]
                })

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size
        }

    def get_object_names_filtered(self, db_name: str, regex_filter: Optional[str] = None,
                                 created_before: Optional[str] = None, has_custom_time: Optional[str] = None,
                                 regex_filters: Optional[List[str]] = None) -> List[str]:
        """Get all object names with optional filtering for download."""
        db_path = self.get_db_path(db_name)

        # Build WHERE clause conditions
        where_conditions = []
        params = []

        # Handle regex filters with OR logic
        all_regex_patterns = []
        if regex_filter:
            all_regex_patterns.append(regex_filter)
        if regex_filters:
            all_regex_patterns.extend([f for f in regex_filters if f])

        if all_regex_patterns:
            regex_conditions = []
            for pattern in all_regex_patterns:
                regex_conditions.append("name REGEXP ?")
                params.append(pattern)
            where_conditions.append(f"({' OR '.join(regex_conditions)})")

        # Date filter (created before)
        if created_before:
            where_conditions.append("time_created < ?")
            params.append(created_before)

        # Custom time filter
        if has_custom_time:
            filter_value = has_custom_time.lower() in ['true', 'yes']
            if filter_value:
                where_conditions.append("custom_time IS NOT NULL")
            else:
                where_conditions.append("custom_time IS NULL")

        # Build complete WHERE clause
        where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""

        with self.get_connection(db_path) as conn:
            query = f"SELECT name FROM objects {where_clause} ORDER BY name ASC"
            logger.info(f"Executing query: {query} with params: {params}")
            rows = conn.execute(query, params).fetchall()

            response = [row["name"] for row in rows]
        logger.info(f"Fetched object names: {response}")
        return response

    def delete_fetch(self, db_name: str) -> bool:
        """Delete a fetch database file."""
        if not safe_db_name(db_name):
            return False

        db_path = self.get_db_path(db_name)
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
                return True
            except Exception as e:
                logger.error(f"Failed to delete {db_path}: {e}")
        return False

    def db_exists(self, db_name: str) -> bool:
        """Check if database file exists."""
        if not safe_db_name(db_name):
            return False
        return os.path.exists(self.get_db_path(db_name))

    def calculate_db_size_mb(self, db_name: str) -> float:
        """Calculate database file size in MB."""
        if not safe_db_name(db_name):
            return 0.0

        db_path = self.get_db_path(db_name)
        if not os.path.exists(db_path):
            return 0.0

        try:
            size_bytes = os.path.getsize(db_path)
            size_mb = size_bytes / (1024 * 1024)
            return round(size_mb, 2)
        except Exception as e:
            logger.error(f"Failed to calculate size for {db_name}: {e}")
            return 0.0
