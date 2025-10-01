"""Manifest-related API routes."""

from flask import Blueprint, request
from .manifest import fetch_and_parse_manifest
from .utils import orjson_response
from ..utils import safe_db_name


def create_manifest_routes(fetch_manager):
    """Create manifest routes with dependency injection."""
    manifest_bp = Blueprint('manifest', __name__, url_prefix='/manifest')

    @manifest_bp.route('/status/<db_name>', methods=['GET'])
    def get_manifest_status(db_name: str):
        """Get manifest status for a database."""
        if not safe_db_name(db_name):
            return orjson_response(
                {"error": "invalid_db_name", "details": "Invalid database name"},
                400
            )

        if not fetch_manager.db_manager.db_exists(db_name):
            return orjson_response(
                {"error": "db_not_found", "details": "Database not found"},
                404
            )

        try:
            current_manifest = fetch_manager.db_manager.get_current_manifest(db_name)

            if current_manifest:
                entries = fetch_manager.db_manager.get_manifest_entries(db_name)
                return orjson_response({
                    "has_manifest": True,
                    "url": current_manifest["url"],
                    "date_added": current_manifest["date_added"],
                    "pattern_count": len(entries),
                    "hash": current_manifest["hash"][:8],  # Show first 8 chars of hash
                    "status": current_manifest.get("status", "idle")
                })
            else:
                return orjson_response({
                    "has_manifest": False
                })

        except Exception as e:
            return orjson_response(
                {"error": "internal_error", "details": str(e)},
                500
            )

    @manifest_bp.route('/parse', methods=['POST'])
    def parse_manifest():
        """Parse a manifest file from URL and link objects to manifest entries."""
        data = request.get_json() or {}
        manifest_url = data.get('url')
        db_name = data.get('db_name')

        if not manifest_url:
            return orjson_response(
                {"error": "missing_url", "details": "Manifest URL is required"},
                400
            )

        # db_name is optional for backward compatibility but required for object linking
        if db_name and not safe_db_name(db_name):
            return orjson_response(
                {"error": "invalid_db_name", "details": "Invalid database name"},
                400
            )

        if db_name and not fetch_manager.db_manager.db_exists(db_name):
            return orjson_response(
                {"error": "db_not_found", "details": "Database not found"},
                404
            )

        # Basic URL validation
        if not (manifest_url.startswith('http://') or manifest_url.startswith('https://')):
            return orjson_response(
                {"error": "invalid_url", "details": "URL must start with http:// or https://"},
                400
            )


        try:
            # Step 1: Clear any existing manifest data (only if db_name provided)
            if db_name:
                current_manifest = fetch_manager.db_manager.get_current_manifest(db_name)
                if current_manifest:
                    fetch_manager.db_manager.clear_manifest_links(db_name)

            # Step 2: Parse and store new manifest
            db_manager = fetch_manager.db_manager if db_name else None
            result = fetch_and_parse_manifest(manifest_url, db_manager, db_name)

            if not result["success"]:
                return orjson_response(
                    {"error": "parse_failed", "details": result["error"]},
                    400
                )

            # Step 3: Link objects to manifest entries (only if db_name provided)
            link_stats = None
            if db_name:
                link_stats = fetch_manager.db_manager.link_objects_to_manifest_entries(db_name)

            response_data = {
                "patterns": result["patterns"],
                "artifact_count": result["artifact_count"],
                "patterns_count": result["patterns_count"],
                "message": result.get("message", f"Successfully parsed {result['artifact_count']} artifacts into {result['patterns_count']} patterns"),
                "cached": result.get("cached", False)
            }

            if link_stats:
                response_data["linking_stats"] = link_stats

            return orjson_response(response_data)

        except Exception as e:
            return orjson_response(
                {"error": "internal_error", "details": str(e)},
                500
            )

    @manifest_bp.route('/recalculate/<db_name>', methods=['POST'])
    def recalculate_manifest(db_name: str):
        """Recalculate manifest object links."""
        if not safe_db_name(db_name):
            return orjson_response(
                {"error": "invalid_db_name", "details": "Invalid database name"},
                400
            )

        if not fetch_manager.db_manager.db_exists(db_name):
            return orjson_response(
                {"error": "db_not_found", "details": "Database not found"},
                404
            )

        try:
            # Check if manifest exists
            current_manifest = fetch_manager.db_manager.get_current_manifest(db_name)
            if not current_manifest:
                return orjson_response(
                    {"error": "no_manifest", "details": "No manifest loaded"},
                    400
                )

            # Clear existing links
            fetch_manager.db_manager.clear_manifest_links(db_name)

            # Recalculate links
            link_stats = fetch_manager.db_manager.link_objects_to_manifest_entries(db_name)

            return orjson_response({
                "success": True,
                "message": "Manifest matches recalculated successfully",
                "linking_stats": link_stats or {"total_objects": 0, "linked_objects": 0}
            })

        except Exception as e:
            return orjson_response(
                {"error": "internal_error", "details": str(e)},
                500
            )

    @manifest_bp.route('/clear/<db_name>', methods=['POST'])
    def clear_manifest(db_name: str):
        """Clear manifest data from database."""
        if not safe_db_name(db_name):
            return orjson_response(
                {"error": "invalid_db_name", "details": "Invalid database name"},
                400
            )

        if not fetch_manager.db_manager.db_exists(db_name):
            return orjson_response(
                {"error": "db_not_found", "details": "Database not found"},
                404
            )

        try:
            # Clear manifest links
            fetch_manager.db_manager.clear_manifest_links(db_name)

            # Clear manifest and manifest entries
            db_path = fetch_manager.db_manager.get_db_path(db_name)
            with fetch_manager.db_manager.get_connection(db_path) as conn:
                conn.execute("DELETE FROM manifest_entries")
                conn.execute("DELETE FROM manifest WHERE id = 1")
                conn.commit()

            return orjson_response({
                "success": True,
                "message": "Manifest cleared successfully"
            })

        except Exception as e:
            return orjson_response(
                {"error": "internal_error", "details": str(e)},
                500
            )

    @manifest_bp.route('/entries/<db_name>', methods=['GET'])
    def get_manifest_entries(db_name: str):
        """Get manifest entries for a database."""
        if not safe_db_name(db_name):
            return orjson_response(
                {"error": "invalid_db_name", "details": "Invalid database name"},
                400
            )

        if not fetch_manager.db_manager.db_exists(db_name):
            return orjson_response(
                {"error": "db_not_found", "details": "Database not found"},
                404
            )

        try:
            # Check if manifest exists
            current_manifest = fetch_manager.db_manager.get_current_manifest(db_name)
            if not current_manifest:
                return orjson_response(
                    {"error": "no_manifest", "details": "No manifest loaded"},
                    400
                )

            # Get manifest entries
            entries = fetch_manager.db_manager.get_manifest_entries(db_name)

            return orjson_response({
                "success": True,
                "entries": entries,
                "count": len(entries)
            })

        except Exception as e:
            return orjson_response(
                {"error": "internal_error", "details": str(e)},
                500
            )

    @manifest_bp.route('/debug/<db_name>', methods=['GET'])
    def debug_manifest(db_name: str):
        """Debug manifest state for troubleshooting."""
        if not safe_db_name(db_name):
            return orjson_response(
                {"error": "invalid_db_name", "details": "Invalid database name"},
                400
            )

        if not fetch_manager.db_manager.db_exists(db_name):
            return orjson_response(
                {"error": "db_not_found", "details": "Database not found"},
                404
            )

        try:
            db_path = fetch_manager.db_manager.get_db_path(db_name)
            with fetch_manager.db_manager.get_connection(db_path) as conn:
                # Check if manifest tables exist
                tables = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('manifest', 'manifest_entries')"
                ).fetchall()
                table_names = [t["name"] for t in tables]

                # Get manifest info
                manifest_info = None
                if 'manifest' in table_names:
                    manifest_row = conn.execute("SELECT * FROM manifest WHERE id = 1").fetchone()
                    if manifest_row:
                        manifest_info = dict(manifest_row)

                # Get manifest entries
                manifest_entries = []
                if 'manifest_entries' in table_names:
                    entries = conn.execute("SELECT * FROM manifest_entries ORDER BY id").fetchall()
                    manifest_entries = [dict(e) for e in entries]

                # Check objects table schema
                objects_schema = conn.execute("PRAGMA table_info(objects)").fetchall()
                has_manifest_column = any(col["name"] == "manifest_entry_id" for col in objects_schema)

                # Get sample objects with manifest IDs
                sample_objects = []
                if has_manifest_column:
                    objects = conn.execute(
                        "SELECT name, manifest_entry_id FROM objects WHERE manifest_entry_id IS NOT NULL LIMIT 5"
                    ).fetchall()
                    sample_objects = [dict(o) for o in objects]

                # Get object counts
                total_objects = conn.execute("SELECT COUNT(*) as count FROM objects").fetchone()["count"]
                linked_objects = 0
                if has_manifest_column:
                    linked_objects = conn.execute(
                        "SELECT COUNT(*) as count FROM objects WHERE manifest_entry_id IS NOT NULL"
                    ).fetchone()["count"]

                return orjson_response({
                    "tables_exist": table_names,
                    "has_manifest_column": has_manifest_column,
                    "manifest_info": manifest_info,
                    "manifest_entries_count": len(manifest_entries),
                    "manifest_entries": manifest_entries,
                    "total_objects": total_objects,
                    "linked_objects": linked_objects,
                    "sample_linked_objects": sample_objects
                })

        except Exception as e:
            return orjson_response(
                {"error": "internal_error", "details": str(e)},
                500
            )

    return manifest_bp