"""Manifest parsing utilities for Firefox-style release manifests."""

import re
import yaml
import requests
import hashlib
from typing import Set, Dict, Any, List


MANIFEST_VARIABLES_REGEX = [
    ("build_number",     "__BUILD_PATTERN__",    r'\d+'),
    ("path_platform",    "__PLATFORM_PATTERN__", r'[A-Za-z0-9-_]+'),
    ("tools_platform",   "__PLATFORM_PATTERN__", r'[A-Za-z0-9-_]+'),
    ("locale",           "__LOCALE_PATTERN__",   r'[A-Za-z-]+'),
    ("previous_version", "__VERSION_PATTERN__",  r'\d+\.\d+b?\d?'),
    ("version",          "__VERSION_PATTERN__",  r'\d+\.\d+b?\d?'),
    ("source_path_mod",  "__SPM__",              r'[A-Za-z0-9-_]*/?'),  # Source path modifier may add locale between destination and filename
]


def parse_manifest_patterns(manifest_data: Dict[str, Any]) -> Set[str]:
    """Extract file patterns from a Firefox-style manifest using destinations."""
    patterns = set()

    # Get the default configuration and mapping sections
    default_config = manifest_data.get('default', {})
    bucket_path = manifest_data.get("s3_bucket_paths", "")
    if isinstance(bucket_path, dict):
        # by-platform
        bucket_path = bucket_path.get("by-platform", {}).get("default", [""])[0]

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
            full_path = f"{bucket_path}/{destination}/__SPM__{pretty_name}"

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

            final_pattern = f"^{pattern}$"
            patterns.add(final_pattern)

    return patterns


# def _optimize_patterns(patterns: set) -> list:
#     """Optimize patterns by grouping by directory path and combining filenames."""
#     from collections import defaultdict

#     # Group patterns by directory path
#     dir_groups = defaultdict(list)

#     for pattern in patterns:
#         # Split pattern into directory and filename parts
#         if '/' in pattern:
#             dir_part, filename_part = pattern.rsplit('/', 1)
#         else:
#             dir_part, filename_part = '', pattern

#         dir_groups[dir_part].append(filename_part)

#     optimized_patterns = []

#     for dir_part, filenames in dir_groups.items():
#         if len(filenames) == 1:
#             # Single filename - use as-is
#             if dir_part:
#                 optimized_patterns.append(f"^{dir_part}/{filenames[0]}$")
#             else:
#                 optimized_patterns.append(f"^{filenames[0]}$")
#         else:
#             # Multiple filenames - combine with regex groups
#             filename_group = '(?:' + '|'.join(filenames) + ')'
#             if dir_part:
#                 optimized_patterns.append(f"^{dir_part}/{filename_group}$")
#             else:
#                 optimized_patterns.append(f"^{filename_group}$")

#     return optimized_patterns


def fetch_and_parse_manifest(url: str, db_manager=None, db_name: str = None) -> Dict[str, Any]:
    """Fetch and parse a manifest file from URL with database storage."""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        # Calculate hash of manifest content for caching
        manifest_hash = hashlib.sha256(response.text.encode('utf-8')).hexdigest()

        # Check if we already have this manifest stored
        if db_manager and db_name:
            current_manifest = db_manager.get_current_manifest(db_name)
            if current_manifest and current_manifest['hash'] == manifest_hash:
                # Return existing patterns from database
                existing_entries = db_manager.get_manifest_entries(db_name)
                patterns = [entry['regex_pattern'] for entry in existing_entries]

                return {
                    "success": True,
                    "patterns": patterns,
                    "artifact_count": current_manifest.get('pattern_count', 0),
                    "patterns_count": len(patterns),
                    "message": f"Manifest already loaded ({len(patterns)} patterns)",
                    "cached": True
                }

        # Try to parse as YAML
        try:
            manifest_data = yaml.safe_load(response.text)
            patterns = list(parse_manifest_patterns(manifest_data))

            # Store manifest in database if db_manager provided
            if db_manager and db_name:
                # Prepare pattern data for storage
                pattern_entries = []
                mapping = manifest_data.get('mapping', {})

                for config in mapping.values():
                    if not config.get('expiry'):
                        continue

                    pretty_name = config.get('pretty_name', '')
                    if not pretty_name:
                        continue

                    destinations = config.get('destinations', [])
                    if not destinations:
                        default_config = manifest_data.get('default', {})
                        destinations = default_config.get('destinations', [])
                    bucket_path = manifest_data.get("s3_bucket_paths", "")
                    if isinstance(bucket_path, dict):
                        # by-platform
                        bucket_path = bucket_path.get("by-platform", {}).get("default", [""])[0]

                    for destination in destinations:
                        # Process the destination + pretty_name to create the full pattern
                        full_path = f"{bucket_path}/{destination}/__SPM__{pretty_name}"


                        # Replace template variables with regex patterns
                        pattern = full_path
                        for path_var, template_var, _ in MANIFEST_VARIABLES_REGEX:
                            if f"${{{path_var}}}" in pattern:
                                pattern = pattern.replace(f"${{{path_var}}}", template_var)

                        # Escape the rest
                        escaped_pattern = re.escape(pattern)

                        # Restore our patterns
                        for _, template_var, regex_var in MANIFEST_VARIABLES_REGEX:
                            escaped_pattern = escaped_pattern.replace(template_var, regex_var)

                        # Make it match full paths - handle both with and without leading separators
                        final_pattern = f"^{escaped_pattern}$"

                        pattern_entries.append({
                            'mapping_key': pretty_name,  # Use pretty_name as mapping key
                            'pretty_name': pretty_name,
                            'destination': destination,
                            'regex_pattern': final_pattern
                        })

                db_manager.store_manifest(db_name, url, manifest_hash, pattern_entries)

            return {
                "success": True,
                "patterns": patterns,
                "artifact_count": len(manifest_data.get('mapping', {})),
                "patterns_count": len(patterns),
                "message": f"Manifest loaded successfully ({len(patterns)} patterns)",
                "cached": False
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
