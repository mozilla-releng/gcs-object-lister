"""Flask API routes for the GCS Storage Manager."""

from flask import current_app, Blueprint, request, send_file
import orjson

from .fetcher import FetchManager
from .utils import validate_regex, safe_db_name

api = Blueprint('api', __name__)


def create_api(fetch_manager: FetchManager):
    """Create API blueprint with fetch manager dependency."""

    @api.route('/health', methods=['GET'])
    def health():
        """Health check endpoint."""
        return orjson_response({"status": "ok"})

    @api.route('/status', methods=['GET'])
    def status():
        """Get current fetch status."""
        return orjson_response(fetch_manager.get_fetch_status())

    @api.route('/fetches', methods=['POST'])
    def start_fetch():
        """Start a new fetch operation."""
        import logging
        logger = logging.getLogger(__name__)
        logger.info("POST /api/fetches received")
        try:
            data = request.get_json() or {}
            prefix = data.get('prefix')
            bucket_name = current_app.config.get('BUCKET_NAME')
            logger.info(f"Bucket name from config: {bucket_name}")
            logger.info(f"Request data: {data}")
            
            if not bucket_name:
                logger.error("BUCKET_NAME not configured")
                return orjson_response(
                    {"error": "bucket_name_required", "details": "BUCKET_NAME not configured"},
                    400
                )

            if prefix is None:
                prefix = current_app.config.get('GCS_PREFIX')
            
            logger.info(f"Starting fetch with bucket='{bucket_name}', prefix='{prefix}'")
            result = fetch_manager.start_fetch(bucket_name, prefix)
            logger.info(f"Fetch started successfully: {result}")
            return orjson_response(result, 201)

        except RuntimeError as e:
            logger.error(f"RuntimeError in start_fetch: {e}")
            if "already running" in str(e):
                return orjson_response(
                    {"error": "fetch_already_running", "details": str(e)},
                    409
                )
            return orjson_response(
                {"error": "fetch_failed", "details": str(e)},
                500
            )
        except Exception as e:
            logger.error(f"Unexpected error in start_fetch: {e}", exc_info=True)
            return orjson_response(
                {"error": "internal_error", "details": str(e)},
                500
            )

    @api.route('/fetches', methods=['GET'])
    def list_fetches():
        """List all available fetches."""
        try:
            fetches = fetch_manager.db_manager.list_fetches()
            return orjson_response(fetches)
        except Exception as e:
            return orjson_response(
                {"error": "internal_error", "details": str(e)},
                500
            )

    @api.route('/fetches/<db_name>', methods=['DELETE'])
    def delete_fetch(db_name: str):
        """Delete a fetch database."""
        if not safe_db_name(db_name):
            return orjson_response(
                {"error": "invalid_db_name", "details": "Invalid database name"},
                400
            )

        # Check if fetch is running
        if fetch_manager.is_fetch_running():
            current_status = fetch_manager.get_fetch_status()
            if current_status.get("db_name") == db_name:
                return orjson_response(
                    {"error": "fetch_running", "details": "Cannot delete running fetch"},
                    409
                )

        # Check if database exists
        if not fetch_manager.db_manager.db_exists(db_name):
            return orjson_response(
                {"error": "not_found", "details": "Fetch not found"},
                404
            )

        try:
            success = fetch_manager.db_manager.delete_fetch(db_name)
            if success:
                return orjson_response({"message": "deleted"})
            else:
                return orjson_response(
                    {"error": "delete_failed", "details": "Failed to delete fetch"},
                    500
                )
        except Exception as e:
            return orjson_response(
                {"error": "internal_error", "details": str(e)},
                500
            )

    @api.route('/fetches/<db_name>/objects', methods=['GET'])
    def list_objects(db_name: str):
        """Get paginated objects with optional regex filtering."""
        if not safe_db_name(db_name):
            return orjson_response(
                {"error": "invalid_db_name", "details": "Invalid database name"},
                400
            )

        if not fetch_manager.db_manager.db_exists(db_name):
            return orjson_response(
                {"error": "not_found", "details": "Fetch not found"},
                404
            )

        # Parse query parameters
        regex_filter = request.args.get('regex')  # Single regex (backward compatibility)
        regex_filters = request.args.getlist('regex_filters[]')  # Multiple regex patterns
        created_before = request.args.get('created_before')
        has_custom_time = request.args.get('has_custom_time')
        page = int(request.args.get('page', 1))
        page_size = min(int(request.args.get('page_size', 200)), 1000)
        sort = request.args.get('sort', 'name_asc')

        # Validate regex patterns
        if regex_filter:
            error_msg = validate_regex(regex_filter)
            if error_msg:
                return orjson_response(
                    {"error": "invalid_regex", "details": f"Single regex: {error_msg}"},
                    400
                )
        
        if regex_filters:
            for i, pattern in enumerate(regex_filters):
                if pattern:  # Skip empty patterns
                    error_msg = validate_regex(pattern)
                    if error_msg:
                        return orjson_response(
                            {"error": "invalid_regex", "details": f"Filter {i+1}: {error_msg}"},
                            400
                        )

        # Validate date parameter if provided
        if created_before:
            try:
                from datetime import datetime
                datetime.fromisoformat(created_before.replace('Z', '+00:00'))
            except ValueError:
                return orjson_response(
                    {"error": "invalid_date", "details": "Date must be in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)"},
                    400
                )

        # Validate has_custom_time parameter
        if has_custom_time and has_custom_time.lower() not in ['true', 'false', 'yes', 'no']:
            return orjson_response(
                {"error": "invalid_boolean", "details": "has_custom_time must be true/false or yes/no"},
                400
            )

        # Validate sort parameter
        if sort not in ['name_asc', 'name_desc']:
            sort = 'name_asc'

        try:
            result = fetch_manager.db_manager.get_objects_page(
                db_name, page, page_size, regex_filter, sort, created_before, has_custom_time, regex_filters
            )
            return orjson_response(result)
        except Exception as e:
            return orjson_response(
                {"error": "internal_error", "details": str(e)},
                500
            )

    @api.route('/fetches/<db_name>/download', methods=['GET'])
    def download_object_list(db_name: str):
        """Download list of object names as text file."""
        if not safe_db_name(db_name):
            return orjson_response(
                {"error": "invalid_db_name", "details": "Invalid database name"},
                400
            )

        if not fetch_manager.db_manager.db_exists(db_name):
            return orjson_response(
                {"error": "not_found", "details": "Fetch not found"},
                404
            )

        # Parse query parameters
        regex_filter = request.args.get('regex')  # Single regex (backward compatibility)
        regex_filters = request.args.getlist('regex_filters[]')  # Multiple regex patterns
        created_before = request.args.get('created_before')
        has_custom_time = request.args.get('has_custom_time')

        # Validate regex patterns
        if regex_filter:
            error_msg = validate_regex(regex_filter)
            if error_msg:
                return orjson_response(
                    {"error": "invalid_regex", "details": f"Single regex: {error_msg}"},
                    400
                )
        
        if regex_filters:
            for i, pattern in enumerate(regex_filters):
                if pattern:  # Skip empty patterns
                    error_msg = validate_regex(pattern)
                    if error_msg:
                        return orjson_response(
                            {"error": "invalid_regex", "details": f"Filter {i+1}: {error_msg}"},
                            400
                        )

        # Validate date parameter if provided
        if created_before:
            try:
                from datetime import datetime
                datetime.fromisoformat(created_before.replace('Z', '+00:00'))
            except ValueError:
                return orjson_response(
                    {"error": "invalid_date", "details": "Date must be in ISO format"},
                    400
                )

        # Validate has_custom_time parameter
        if has_custom_time and has_custom_time.lower() not in ['true', 'false', 'yes', 'no']:
            return orjson_response(
                {"error": "invalid_boolean", "details": "has_custom_time must be true/false or yes/no"},
                400
            )

        try:
            object_names = fetch_manager.db_manager.get_object_names_filtered(
                db_name, regex_filter, created_before, has_custom_time, regex_filters
            )

            # Create text content
            content = "\n".join(object_names)

            # Create in-memory file
            from io import BytesIO
            output = BytesIO()
            output.write(content.encode('utf-8'))
            output.seek(0)

            filename = f"{db_name}_files.txt"

            return send_file(
                output,
                mimetype='text/plain',
                as_attachment=True,
                download_name=filename
            )

        except Exception as e:
            return orjson_response(
                {"error": "internal_error", "details": str(e)},
                500
            )

    return api


def orjson_response(data, status_code=200):
    """Create JSON response using orjson."""
    from flask import Response
    return Response(
        orjson.dumps(data),
        status=status_code,
        mimetype='application/json'
    )
