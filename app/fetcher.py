"""Background fetch operations with locking mechanism."""

import os
import threading
import logging
import time
from datetime import datetime, timezone
from google.cloud import storage
from typing import Optional, Dict, Any

from .db import DatabaseManager
from .utils import create_db_name, format_timestamp

logger = logging.getLogger(__name__)


class FetchManager:
    """Manages background fetch operations with locking."""

    def __init__(self, data_dir: str, gcp_project: Optional[str] = None):
        self.data_dir = data_dir
        self.db_manager = DatabaseManager(data_dir)
        self.gcs_client = storage.Client(project=gcp_project)
        self.lock_file = os.path.join(data_dir, ".lock")
        self._thread_lock = threading.Lock()
        self._current_fetch: Optional[Dict[str, Any]] = None
        self._fetch_thread: Optional[threading.Thread] = None

        # Clear stale lock on startup
        self._clear_stale_lock()

    def _clear_stale_lock(self):
        """Clear stale lock file (older than 4 hours) on startup."""
        if os.path.exists(self.lock_file):
            try:
                stat = os.stat(self.lock_file)
                age_hours = (time.time() - stat.st_mtime) / 3600
                if age_hours > 4:
                    os.remove(self.lock_file)
                    logger.info("Cleared stale lock file")
            except Exception as e:
                logger.warning(f"Failed to check/clear lock file: {e}")

    def is_fetch_running(self) -> bool:
        """Check if a fetch is currently running."""
        with self._thread_lock:
            return self._is_fetch_running_locked()

    def _is_fetch_running_locked(self) -> bool:
        """Check if a fetch is currently running (assumes lock is already held)."""
        return self._current_fetch is not None and os.path.exists(self.lock_file)

    def get_fetch_status(self) -> Dict[str, Any]:
        """Get current fetch status."""
        with self._thread_lock:
            if self._current_fetch and os.path.exists(self.lock_file):
                # Get current progress from database
                db_name = self._current_fetch["db_name"]
                fetch_info = self.db_manager.get_fetch_info(db_name)

                return {
                    "running": True,
                    "started_at": self._current_fetch["started_at"],
                    "db_name": db_name,
                    "processed": fetch_info["record_count"] if fetch_info else 0,
                    "message": f"Fetching from {self._current_fetch['bucket_name']}..."
                }
            else:
                return {"running": False}

    def start_fetch(self, bucket_name: str, prefix: Optional[str] = None) -> Dict[str, str]:
        """
        Start a new fetch operation.

        Returns dict with db_name and started_at.
        Raises RuntimeError if fetch is already running.
        """
        with self._thread_lock:
            if self._is_fetch_running_locked():
                raise RuntimeError("Fetch already running")

            # Create lock file
            try:
                with open(self.lock_file, "w") as f:
                    f.write(f"{os.getpid()}\n{datetime.now(timezone.utc).isoformat()}")
            except Exception as e:
                raise RuntimeError(f"Failed to create lock file: {e}")

            # Setup fetch metadata
            started_at = datetime.now(timezone.utc)
            db_name = create_db_name(started_at)

            self._current_fetch = {
                "db_name": db_name,
                "bucket_name": bucket_name,
                "prefix": prefix,
                "started_at": format_timestamp(started_at)
            }

            # Create database
            try:
                self.db_manager.create_fetch_db(db_name, bucket_name, prefix, started_at)
            except Exception as e:
                self._cleanup_fetch()
                raise RuntimeError(f"Failed to create database: {e}")

            # Start background thread
            self._fetch_thread = threading.Thread(
                target=self._run_fetch,
                args=(db_name, bucket_name, prefix),
                daemon=True
            )
            self._fetch_thread.start()

            return {
                "db_name": db_name,
                "started_at": self._current_fetch["started_at"]
            }

    def _run_fetch(self, db_name: str, bucket_name: str, prefix: Optional[str]):
        """Run the actual fetch operation in background thread."""
        start_time = time.time()
        processed_count = 0
        batch = []
        batch_size = 1000

        try:
            logger.info(f"Starting fetch from bucket {bucket_name}, prefix={prefix}")

            # Stream objects from GCS
            bucket = self.gcs_client.bucket(bucket_name)
            logger.info(f"Fetching from bucket: {bucket_name}")
            for blob in bucket.list_blobs(prefix=prefix):
                # Convert blob to dictionary format expected by database
                obj_data = {
                    "name": blob.name,
                    "size": blob.size or 0,
                    "updated": blob.updated.isoformat() if blob.updated else None,
                    "time_created": blob.time_created.isoformat() if blob.time_created else None,
                    "custom_time": blob.custom_time.isoformat() if blob.custom_time else None
                }

                batch.append(obj_data)
                processed_count += 1

                # Insert batch when full
                if len(batch) >= batch_size:
                    self.db_manager.insert_objects_batch(db_name, batch)
                    batch = []

                    # Update record count in database for live progress
                    self.db_manager.update_fetch_status(db_name, "running", record_count=processed_count)

                    # Log progress
                    elapsed = time.time() - start_time
                    rate = processed_count / elapsed if elapsed > 0 else 0
                    logger.info(f"Processed {processed_count} objects ({rate:.1f}/sec)")

            # Insert remaining batch
            if batch:
                self.db_manager.insert_objects_batch(db_name, batch)

            # Mark as successful and calculate database size
            ended_at = datetime.now(timezone.utc)
            db_size_mb = self.db_manager.calculate_db_size_mb(db_name)
            self.db_manager.update_fetch_status(
                db_name, "success", ended_at=ended_at, record_count=processed_count,
                db_size_mb=db_size_mb
            )

            elapsed = time.time() - start_time
            logger.info(f"Fetch completed: {processed_count} objects in {elapsed:.1f}s, DB size: {db_size_mb} MB")

        except Exception as e:
            logger.error(f"Fetch failed: {e}")
            self.db_manager.update_fetch_status(
                db_name, "error", ended_at=datetime.now(timezone.utc),
                record_count=processed_count, error=str(e)
            )
        finally:
            self._cleanup_fetch()

    def _cleanup_fetch(self):
        """Clean up after fetch completion or failure."""
        with self._thread_lock:
            self._current_fetch = None
            self._fetch_thread = None

            # Remove lock file
            try:
                if os.path.exists(self.lock_file):
                    os.remove(self.lock_file)
            except Exception as e:
                logger.warning(f"Failed to remove lock file: {e}")
