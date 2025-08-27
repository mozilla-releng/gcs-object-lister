"""Utility functions for the GCS Storage Manager."""

import re
from datetime import datetime
from typing import Optional


def humanize_bytes(size: int) -> str:
    """Convert bytes to human readable format."""
    if size == 0:
        return "0 B"
    
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    size_float = float(size)
    
    while size_float >= 1024 and unit_index < len(units) - 1:
        size_float /= 1024
        unit_index += 1
    
    if unit_index == 0:
        return f"{int(size_float)} {units[unit_index]}"
    else:
        return f"{size_float:.1f} {units[unit_index]}"


def format_timestamp(dt: datetime) -> str:
    """Format datetime as ISO-8601 UTC string."""
    return dt.isoformat() + "Z"


def parse_timestamp(timestamp_str: str) -> datetime:
    """Parse ISO-8601 UTC timestamp string."""
    if timestamp_str.endswith("Z"):
        timestamp_str = timestamp_str[:-1]
    return datetime.fromisoformat(timestamp_str)


def create_db_name(timestamp: datetime) -> str:
    """Create database filename from timestamp."""
    return timestamp.strftime("%Y-%m-%dT%H-%M-%SZ")


def validate_regex(pattern: str) -> Optional[str]:
    """Validate regex pattern. Returns error message if invalid, None if valid."""
    if not pattern:
        return None  # Empty pattern is valid (matches everything)
    
    # Check for common regex mistakes
    common_mistakes = [
        (r'^[*+?{]', "Pattern cannot start with a quantifier (*+?{})"),
        (r'[*+?][*+?]', "Cannot have consecutive quantifiers"),
        (r'\*\*+', "Use .* instead of ** for wildcard matching"),
        (r'^\*', "Use .* at the start instead of just *"),
    ]
    
    for mistake_pattern, message in common_mistakes:
        if re.search(mistake_pattern, pattern):
            return message
    
    try:
        re.compile(pattern)
        return None
    except re.error as e:
        error_msg = str(e)
        
        # Provide more helpful error messages
        if "nothing to repeat" in error_msg:
            return "Invalid quantifier usage. Quantifiers (*+?{}) must follow a character or group."
        elif "bad character range" in error_msg:
            return "Invalid character range in brackets. Use [a-z] format."
        elif "unbalanced parenthesis" in error_msg:
            return "Unmatched parentheses in pattern."
        elif "bad escape" in error_msg:
            return "Invalid escape sequence. Use \\\\ for literal backslash."
        else:
            return f"Invalid regex: {error_msg}"


def safe_db_name(db_name: str) -> bool:
    """Check if database name is safe (no path traversal)."""
    return ".." not in db_name and "/" not in db_name and "\\" not in db_name