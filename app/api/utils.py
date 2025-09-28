"""API utility functions."""

from flask import Response
import orjson


def orjson_response(data, status_code=200):
    """Create JSON response using orjson."""
    return Response(
        orjson.dumps(data),
        status=status_code,
        mimetype='application/json'
    )


def optimize_regex_patterns(patterns_list):
    """Optimize regex patterns by combining them if there are too many."""
    if len(patterns_list) > 20:
        # Combine patterns into a single OR regex for better performance
        escaped_patterns = [f"({pattern})" for pattern in patterns_list]
        combined_pattern = "|".join(escaped_patterns)
        return [combined_pattern]
    return patterns_list