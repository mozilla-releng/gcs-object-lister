"""Manifest parsing utilities for Firefox-style release manifests."""

import re
import yaml
import requests
from typing import Set, Dict, Any


MANIFEST_VARIABLES_REGEX = [
    ("build_number",     "__BUILD_PATTERN__",    r'\d+'),
    ("path_platform",    "__PLATFORM_PATTERN__", r'[A-Za-z0-9-_]+'),
    ("tools_platform",   "__PLATFORM_PATTERN__", r'[A-Za-z0-9-_]+'),
    ("locale",           "__LOCALE_PATTERN__",   r'[A-Za-z-]+'),
    ("previous_version", "__VERSION_PATTERN__",  r'\d+\.\d+b?\d?'),
    ("version",          "__VERSION_PATTERN__",  r'\d+\.\d+b?\d?'),
]


def parse_manifest_patterns(manifest_data: Dict[str, Any]) -> Set[str]:
    """Extract file patterns from a Firefox-style manifest using destinations."""
    patterns = set()

    # Get the default configuration and mapping sections
    default_config = manifest_data.get('default', {})
    mapping = manifest_data.get('mapping', {})

    for config in mapping.values():
        # Only include entries that have expiry set
        if not config.get('expiry'):
            continue

        # Get destinations - check artifact config first, then fall back to default
        destinations = config.get('destinations')
        if not destinations:
            destinations = default_config.get('destinations', [])

        if not destinations:
            continue

        # Get the pretty_name for this artifact
        pretty_name = config.get('pretty_name', '')
        if not pretty_name:
            continue  # Skip artifacts without pretty_name

        for destination in destinations:
            # Append pretty_name to destination path
            full_path = f"{destination}/{pretty_name}"

            # Replace template variables with set templates
            # We use placeholders to avoid escaping them in the next step
            # e.g. ${version} -> __VERSION_PATTERN__
            for path_var, template_var, _ in MANIFEST_VARIABLES_REGEX:
                if f"${{{path_var}}}" in full_path:
                    full_path = full_path.replace(f"${{{path_var}}}", template_var)

            # Escape the rest
            pattern = re.escape(full_path)

            # Restore our patterns
            for _, template_var, regex_var in MANIFEST_VARIABLES_REGEX:
                pattern = pattern.replace(template_var, regex_var)

            patterns.add(pattern)

    # Optimize patterns by grouping by directory path
    return _optimize_patterns(patterns)


def _optimize_patterns(patterns: set) -> list:
    """Optimize patterns by grouping by directory path and combining filenames."""
    from collections import defaultdict

    # Group patterns by directory path
    dir_groups = defaultdict(list)

    for pattern in patterns:
        # Split pattern into directory and filename parts
        if '/' in pattern:
            dir_part, filename_part = pattern.rsplit('/', 1)
        else:
            dir_part, filename_part = '', pattern

        dir_groups[dir_part].append(filename_part)

    optimized_patterns = []

    for dir_part, filenames in dir_groups.items():
        if len(filenames) == 1:
            # Single filename - use as-is
            if dir_part:
                optimized_patterns.append(f".*/{dir_part}/{filenames[0]}$")
            else:
                optimized_patterns.append(f".*/{ filenames[0]}$")
        else:
            # Multiple filenames - combine with regex groups
            filename_group = '(?:' + '|'.join(filenames) + ')'
            if dir_part:
                optimized_patterns.append(f".*/{dir_part}/{filename_group}$")
            else:
                optimized_patterns.append(f".*/{filename_group}$")

    return optimized_patterns


def fetch_and_parse_manifest(url: str) -> Dict[str, Any]:
    """Fetch and parse a manifest file from URL."""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        # Try to parse as YAML
        try:
            manifest_data = yaml.safe_load(response.text)
            patterns = list(parse_manifest_patterns(manifest_data))
            # Limit patterns to prevent performance issues
            if len(patterns) > 50:
                patterns = patterns[:50]

            return {
                "success": True,
                "patterns": patterns,
                "artifact_count": len(manifest_data.get('mapping', {})),
                "patterns_count": len(patterns)
            }
        except yaml.YAMLError as e:
            return {
                "success": False,
                "error": f"Invalid YAML format: {str(e)}"
            }

    except requests.RequestException as e:
        return {
            "success": False,
            "error": f"Failed to fetch manifest: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }
