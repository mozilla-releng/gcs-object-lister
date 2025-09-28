"""Manifest-related API routes."""

from flask import Blueprint, request
from .manifest import fetch_and_parse_manifest
from .utils import orjson_response

manifest_bp = Blueprint('manifest', __name__, url_prefix='/manifest')


@manifest_bp.route('/parse', methods=['POST'])
def parse_manifest():
    """Parse a manifest file from URL and return filtering patterns."""
    data = request.get_json() or {}
    manifest_url = data.get('url')

    if not manifest_url:
        return orjson_response(
            {"error": "missing_url", "details": "Manifest URL is required"},
            400
        )

    # Basic URL validation
    if not (manifest_url.startswith('http://') or manifest_url.startswith('https://')):
        return orjson_response(
            {"error": "invalid_url", "details": "URL must start with http:// or https://"},
            400
        )

    try:
        result = fetch_and_parse_manifest(manifest_url)
        if result["success"]:
            return orjson_response({
                "patterns": result["patterns"],
                "artifact_count": result["artifact_count"],
                "patterns_count": result["patterns_count"],
                "message": f"Successfully parsed {result['artifact_count']} artifacts into {result['patterns_count']} patterns"
            })
        else:
            return orjson_response(
                {"error": "parse_failed", "details": result["error"]},
                400
            )
    except Exception as e:
        return orjson_response(
            {"error": "internal_error", "details": str(e)},
            500
        )