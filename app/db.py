"""Database utilities for SQLite operations."""

import os
import sqlite3
import logging
import re
from contextlib import contextmanager
from datetime import datetime, timezone
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
                    custom_time TEXT,
                    manifest_entry_id INTEGER,
                    FOREIGN KEY (manifest_entry_id) REFERENCES manifest_entries (id)
                )
            """)

            conn.execute("""
                CREATE TABLE manifest (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    url TEXT NOT NULL,
                    hash TEXT NOT NULL,
                    date_added TEXT NOT NULL,
                    pattern_count INTEGER DEFAULT 0
                )
            """)

            conn.execute("""
                CREATE TABLE manifest_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mapping_key TEXT NOT NULL,
                    pretty_name TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    regex_pattern TEXT NOT NULL
                )
            """)

            # Create indexes for efficient filtering and sorting
            conn.execute("CREATE INDEX idx_objects_name ON objects(name)")
            conn.execute("CREATE INDEX idx_objects_time_created ON objects(time_created)")
            conn.execute("CREATE INDEX idx_objects_custom_time ON objects(custom_time)")
            conn.execute("CREATE INDEX idx_objects_manifest_entry_id ON objects(manifest_entry_id)")

            # Composite indexes for common query patterns
            conn.execute("CREATE INDEX idx_objects_time_created_name ON objects(time_created, name)")
            conn.execute("CREATE INDEX idx_objects_custom_time_name ON objects(custom_time, name)")

            # Manifest table indexes
            conn.execute("CREATE INDEX idx_manifest_entries_id ON manifest_entries(id)")

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
                        regex_filters: Optional[List[str]] = None,
                        use_manifest_filtering: bool = False,
                        exclude_manifest_matches: bool = False) -> Dict[str, Any]:
        """Get paginated objects with optional filtering."""
        db_path = self.get_db_path(db_name)
        offset = (page - 1) * page_size

        # Build WHERE clause conditions
        where_conditions = []
        params = []
        from_clause = "objects"
        join_clause = ""

        # Determine filtering strategy
        if use_manifest_filtering:
            # Use manifest-based filtering (fast JOIN approach)
            from_clause = "objects o"
            join_clause = "JOIN manifest_entries me ON o.manifest_entry_id = me.id"
            # Filter is handled by the JOIN, so only objects with manifest_entry_id will be included
        elif exclude_manifest_matches:
            # Filter out objects that match manifest
            from_clause = "objects"
            where_conditions.append("manifest_entry_id IS NULL")
        else:
            # Handle regex filters with OR logic (slower REGEXP approach)
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

        # Build ORDER BY clause - adjust for table alias if using JOIN
        table_prefix = "o." if use_manifest_filtering else ""
        if sort == "name_desc":
            order_by = f"ORDER BY {table_prefix}name DESC"
        elif sort == "time_created_desc":
            order_by = f"ORDER BY {table_prefix}time_created DESC"
        elif sort == "time_created_asc":
            order_by = f"ORDER BY {table_prefix}time_created ASC"
        else:  # name_asc
            order_by = f"ORDER BY {table_prefix}name ASC"

        # Build complete WHERE clause
        where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""

        with self.get_connection(db_path) as conn:
            # Get total count
            if use_manifest_filtering:
                count_query = f"SELECT COUNT(*) FROM {from_clause} {join_clause} {where_clause}"
            else:
                count_query = f"SELECT COUNT(*) FROM {from_clause} {where_clause}"

            total = conn.execute(count_query, params).fetchone()[0]

            # Get paginated results
            if use_manifest_filtering:
                data_query = f"""
                    SELECT o.name, o.size, o.updated, o.time_created, o.custom_time, o.manifest_entry_id
                    FROM {from_clause}
                    {join_clause}
                    {where_clause}
                    {order_by}
                    LIMIT ? OFFSET ?
                """
            else:
                data_query = f"""
                    SELECT name, size, updated, time_created, custom_time, manifest_entry_id
                    FROM {from_clause}
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
                    "custom_time": row["custom_time"],
                    "manifest_entry_id": row["manifest_entry_id"]
                })

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size
        }

    def get_object_names_filtered(self, db_name: str, regex_filter: Optional[str] = None,
                                 created_before: Optional[str] = None, has_custom_time: Optional[str] = None,
                                 regex_filters: Optional[List[str]] = None,
                                 use_manifest_filtering: bool = False,
                                 exclude_manifest_matches: bool = False) -> List[str]:
        """Get all object names with optional filtering for download."""
        db_path = self.get_db_path(db_name)

        # Build WHERE clause conditions
        where_conditions = []
        params = []
        from_clause = "objects"
        join_clause = ""

        # Determine filtering strategy
        if use_manifest_filtering:
            # Use manifest-based filtering (fast JOIN approach)
            from_clause = "objects o"
            join_clause = "JOIN manifest_entries me ON o.manifest_entry_id = me.id"
        elif exclude_manifest_matches:
            # Filter out objects that match manifest
            from_clause = "objects"
            where_conditions.append("manifest_entry_id IS NULL")
        else:
            # Handle regex filters with OR logic (slower REGEXP approach)
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

        # Date filter (created before) - adjust for table alias
        table_prefix = "o." if use_manifest_filtering else ""
        if created_before:
            where_conditions.append(f"{table_prefix}time_created < ?")
            params.append(created_before)

        # Custom time filter
        if has_custom_time:
            filter_value = has_custom_time.lower() in ['true', 'yes']
            if filter_value:
                where_conditions.append(f"{table_prefix}custom_time IS NOT NULL")
            else:
                where_conditions.append(f"{table_prefix}custom_time IS NULL")

        # Build complete WHERE clause
        where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""

        with self.get_connection(db_path) as conn:
            if use_manifest_filtering:
                query = f"SELECT o.name FROM {from_clause} {join_clause} {where_clause} ORDER BY o.name ASC"
            else:
                query = f"SELECT name FROM {from_clause} {where_clause} ORDER BY name ASC"

            logger.info(f"Executing query: {query} with params: {params}")
            rows = conn.execute(query, params).fetchall()

            response = [row["name"] for row in rows]
        return response

    def get_current_manifest(self, db_name: str) -> Optional[Dict[str, Any]]:
        """Get the current manifest record if it exists."""
        if not safe_db_name(db_name):
            return None

        db_path = self.get_db_path(db_name)
        if not os.path.exists(db_path):
            return None

        try:
            with self.get_connection(db_path) as conn:
                # Check if manifest table exists (for migration compatibility)
                tables = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='manifest'"
                ).fetchall()

                if not tables:
                    return None

                # Trigger migration to ensure status column exists
                self._ensure_manifest_tables_exist(conn)

                row = conn.execute("SELECT * FROM manifest WHERE id = 1").fetchone()
                if row:
                    # Check if status column exists (migration compatibility)
                    try:
                        status = row["status"]
                    except (KeyError, IndexError):
                        status = "idle"

                    return {
                        "url": row["url"],
                        "hash": row["hash"],
                        "date_added": row["date_added"],
                        "pattern_count": row["pattern_count"],
                        "status": status
                    }
        except Exception as e:
            logger.warning(f"Failed to read manifest from {db_name}: {e}")

        return None

    def store_manifest(self, db_name: str, url: str, manifest_hash: str, patterns: List[Dict[str, str]]):
        """Store or replace manifest data. Clear existing entries if hash differs."""
        db_path = self.get_db_path(db_name)

        with self.get_connection(db_path) as conn:
            # Check if tables exist (for migration compatibility)
            self._ensure_manifest_tables_exist(conn)

            # Get current manifest
            current = conn.execute("SELECT hash FROM manifest WHERE id = 1").fetchone()
            current_hash = current["hash"] if current else None

            # If hash differs, clear all existing data
            if current_hash != manifest_hash:
                logger.info(f"Manifest hash changed for {db_name}, clearing existing data")

                # Clear all manifest links from objects
                conn.execute("UPDATE objects SET manifest_entry_id = NULL")

                # Delete all manifest entries
                conn.execute("DELETE FROM manifest_entries")

                # Replace manifest record
                conn.execute("""
                    INSERT OR REPLACE INTO manifest (id, url, hash, date_added, pattern_count, status)
                    VALUES (1, ?, ?, ?, ?, 'idle')
                """, (url, manifest_hash, format_timestamp(datetime.now(timezone.utc)), len(patterns)))

                # Insert new manifest entries
                for i, pattern_data in enumerate(patterns):
                    logger.info(f"Storing manifest entry {i+1}: {pattern_data}")
                    conn.execute("""
                        INSERT INTO manifest_entries (mapping_key, pretty_name, destination, regex_pattern)
                        VALUES (?, ?, ?, ?)
                    """, (
                        pattern_data.get('mapping_key', ''),
                        pattern_data.get('pretty_name', ''),
                        pattern_data.get('destination', ''),
                        pattern_data.get('regex_pattern', '')
                    ))

                conn.commit()
                logger.info(f"Stored {len(patterns)} manifest patterns for {db_name}")

                # Log what was actually stored
                stored_entries = conn.execute("SELECT id, pretty_name, regex_pattern FROM manifest_entries").fetchall()
                logger.info(f"Verified {len(stored_entries)} entries in database:")
                for entry in stored_entries:
                    logger.info(f"  ID {entry['id']}: {entry['pretty_name']} -> {entry['regex_pattern']}")

    def clear_manifest_links(self, db_name: str):
        """Clear all manifest_entry_id links from objects table."""
        db_path = self.get_db_path(db_name)

        with self.get_connection(db_path) as conn:
            conn.execute("UPDATE objects SET manifest_entry_id = NULL")
            conn.commit()

    def get_manifest_entries(self, db_name: str) -> List[Dict[str, Any]]:
        """Get all manifest entries for this database."""
        db_path = self.get_db_path(db_name)

        with self.get_connection(db_path) as conn:
            # Check if manifest_entries table exists
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='manifest_entries'"
            ).fetchall()

            if not tables:
                return []

            rows = conn.execute("""
                SELECT id, mapping_key, pretty_name, destination, regex_pattern
                FROM manifest_entries
                ORDER BY id
            """).fetchall()

            return [
                {
                    "id": row["id"],
                    "mapping_key": row["mapping_key"],
                    "pretty_name": row["pretty_name"],
                    "destination": row["destination"],
                    "regex_pattern": row["regex_pattern"]
                }
                for row in rows
            ]

    def _ensure_manifest_tables_exist(self, conn):
        """Ensure manifest tables exist for migration compatibility."""
        # Check if manifest table exists
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='manifest'"
        ).fetchall()

        if not tables:
            # Create manifest tables
            conn.execute("""
                CREATE TABLE manifest (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    url TEXT NOT NULL,
                    hash TEXT NOT NULL,
                    date_added TEXT NOT NULL,
                    pattern_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'idle'
                )
            """)

            conn.execute("""
                CREATE TABLE manifest_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mapping_key TEXT NOT NULL,
                    pretty_name TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    regex_pattern TEXT NOT NULL
                )
            """)

            # Add manifest_entry_id column to objects if it doesn't exist
            try:
                conn.execute("ALTER TABLE objects ADD COLUMN manifest_entry_id INTEGER")
            except Exception:
                # Column might already exist
                pass

            # Create indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_objects_manifest_entry_id ON objects(manifest_entry_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_manifest_entries_id ON manifest_entries(id)")

            conn.commit()
        else:
            # Migration for existing databases - add status column if it doesn't exist
            try:
                conn.execute("ALTER TABLE manifest ADD COLUMN status TEXT DEFAULT 'idle'")
                conn.commit()
                logger.info(f"Added status column to existing manifest table")
            except Exception:
                # Column might already exist
                pass

    def update_manifest_status(self, db_name: str, status: str):
        """Update manifest processing status."""
        db_path = self.get_db_path(db_name)

        with self.get_connection(db_path) as conn:
            self._ensure_manifest_tables_exist(conn)
            conn.execute("UPDATE manifest SET status = ? WHERE id = 1", (status,))
            conn.commit()
            logger.info(f"Updated manifest status to: {status}")

    def link_objects_to_manifest_entries(self, db_name: str):
        """Link objects to manifest entries by matching regex patterns."""
        db_path = self.get_db_path(db_name)

        with self.get_connection(db_path) as conn:
            # First, check if manifest tables exist and ensure migration
            self._ensure_manifest_tables_exist(conn)

            # Set status to processing
            conn.execute("UPDATE manifest SET status = 'processing' WHERE id = 1")
            conn.commit()

            # Get all manifest entries
            entries = conn.execute("""
                SELECT id, regex_pattern, pretty_name
                FROM manifest_entries
                ORDER BY id
            """).fetchall()

            if not entries:
                logger.info(f"No manifest entries found for {db_name}")
                return {"total_objects": 0, "linked_objects": 0}

            logger.info(f"Found {len(entries)} manifest entries to process for {db_name}")

            updated_count = 0

            # For each manifest entry, update objects that match the regex pattern
            for entry in entries:
                entry_id = entry["id"]
                pattern = entry["regex_pattern"]
                pretty_name = entry["pretty_name"]

                logger.info(f"Processing manifest entry {entry_id} ('{pretty_name}') with pattern: {pattern}")

                try:
                    # Update objects that match this pattern and don't already have a manifest_entry_id
                    result = conn.execute("""
                        UPDATE objects
                        SET manifest_entry_id = ?
                        WHERE name REGEXP ? AND manifest_entry_id IS NULL
                    """, (entry_id, pattern))

                    matches_count = result.rowcount
                    updated_count += matches_count
                    logger.info(f"Pattern '{pattern}' matched and linked {matches_count} objects")

                    # Log some sample matches for debugging (optional)
                    if matches_count > 0:
                        sample_matches = conn.execute("""
                            SELECT name FROM objects
                            WHERE manifest_entry_id = ?
                            LIMIT 3
                        """, (entry_id,)).fetchall()

                        for i, match in enumerate(sample_matches):
                            logger.info(f"  Sample match {i+1}: {match['name']}")
                        if matches_count > 3:
                            logger.info(f"  ... and {matches_count - 3} more objects")

                except Exception as e:
                    logger.warning(f"Failed to process pattern {pattern}: {e}")
                    continue

            conn.commit()
            logger.info(f"Successfully linked {updated_count} objects to manifest entries for {db_name}")

            # Set status back to idle when complete
            conn.execute("UPDATE manifest SET status = 'idle' WHERE id = 1")
            conn.commit()

            # Return statistics
            total_objects = conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
            linked_objects = conn.execute("SELECT COUNT(*) FROM objects WHERE manifest_entry_id IS NOT NULL").fetchone()[0]

            logger.info(f"Manifest linking complete: {linked_objects}/{total_objects} objects linked")
            return {"total_objects": total_objects, "linked_objects": linked_objects}

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
