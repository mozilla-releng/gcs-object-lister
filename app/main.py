"""Main Flask application."""

import os
import logging
from flask import Flask, send_from_directory, request

from .api import create_api
from .fetcher import FetchManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def create_app():
    """Create Flask application."""
    # Get the parent directory of the app directory to find static files
    static_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')
    app = Flask(__name__, static_folder=static_folder)

    # Load configuration from environment
    app.config.update(
        APP_HOST=os.getenv('APP_HOST', '0.0.0.0'),
        APP_PORT=int(os.getenv('APP_PORT', 8080)),
        GCP_PROJECT=os.getenv('GOOGLE_CLOUD_PROJECT'),
        BUCKET_NAME=os.getenv('BUCKET_NAME'),
        GCS_PREFIX=os.getenv('GCS_PREFIX'),
        DATA_DIR=os.getenv('DATA_DIR', '/data/fetches')
    )

    # Validate required configuration
    if not app.config['BUCKET_NAME']:
        logger.warning("BUCKET_NAME not set - fetch requests must include bucket parameter")

    # Initialize fetch manager
    fetch_manager = FetchManager(app.config['DATA_DIR'], app.config['GCP_PROJECT'])

    # Register API blueprint
    api_blueprint = create_api(fetch_manager)
    app.register_blueprint(api_blueprint, url_prefix='/api')

    # Static file routes
    @app.route('/static/<path:filename>')
    def static_files(filename):
        """Serve static files."""
        return send_from_directory(static_folder, filename)

    @app.route('/')
    def index():
        """Serve main page."""
        return send_from_directory(static_folder, 'index.html')

    @app.route('/<db_name>')
    def fetch_view(db_name):
        """Serve fetch view page."""
        # Validate db_name for security
        from .utils import safe_db_name
        if not safe_db_name(db_name):
            return "Invalid database name", 400
        return send_from_directory(static_folder, 'fetch.html')

    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        """Handle 404 errors."""
        if request.path.startswith('/api/'):
            from .api.utils import orjson_response
            return orjson_response({"error": "not_found", "details": "Endpoint not found"}, 404)
        return "Page not found", 404

    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors."""
        logger.error(f"Internal error: {error}")
        if request.path.startswith('/api/'):
            from .api.utils import orjson_response
            return orjson_response({"error": "internal_error", "details": "Internal server error"}, 500)
        return "Internal server error", 500

    return app


def main():
    """Run the application."""
    app = create_app()

    host = app.config['APP_HOST']
    port = app.config['APP_PORT']

    logger.info(f"Starting GCS Storage Manager on {host}:{port}")

    if app.config['GCP_PROJECT']:
        logger.info(f"GCP Project: {app.config['GCP_PROJECT']}")
    if app.config['BUCKET_NAME']:
        logger.info(f"Default bucket: {app.config['BUCKET_NAME']}")
    if app.config['GCS_PREFIX']:
        logger.info(f"Default prefix: {app.config['GCS_PREFIX']}")

    logger.info(f"Data directory: {app.config['DATA_DIR']}")
    logger.info(f"Visit http://localhost:{port}/ to use the application")

    app.run(host=host, port=port, debug=False)


if __name__ == '__main__':
    main()
