"""Main API routes module."""

from flask import Blueprint
from .utils import orjson_response
from .manifest_routes import create_manifest_routes
from .fetch_routes import create_fetch_routes

api = Blueprint('api', __name__)


def create_api(fetch_manager):
    """Create API blueprint with fetch manager dependency."""

    @api.route('/health', methods=['GET'])
    def health():
        """Health check endpoint."""
        return orjson_response({"status": "ok"})

    @api.route('/status', methods=['GET'])
    def status():
        """Get current fetch status."""
        return orjson_response(fetch_manager.get_fetch_status())

    # Create and register sub-blueprints with dependency injection
    manifest_bp = create_manifest_routes(fetch_manager)
    api.register_blueprint(manifest_bp)

    fetch_bp = create_fetch_routes(fetch_manager)
    api.register_blueprint(fetch_bp)

    return api