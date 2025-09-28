# API Module

Modular REST API implementation with separated concerns for different functionality areas.

## Structure

- **`__init__.py`** - Module initialization exposing clean interface via create_api()
- **`routes.py`** - Main API blueprint with health/status endpoints and sub-blueprint registration
- **`manifest.py`** - Manifest parsing utilities for Firefox-style release manifests
- **`manifest_routes.py`** - REST endpoints for manifest URL fetching and pattern extraction
- **`fetch_routes.py`** - REST endpoints for fetch operations (start, list, delete, objects, download)
- **`utils.py`** - Shared API utilities (JSON responses, pattern optimization)

## Key Features

### Manifest Processing
- **YAML Parsing**: Fetches and parses Firefox release manifests from URLs
- **Template Substitution**: Converts `${version}`, `${build_number}`, `${path_platform}`, `${locale}` to regex patterns
- **Destination-Based Patterns**: Uses manifest destinations + pretty_name for precise file path matching
- **Expiry Filtering**: Only processes artifacts with expiry settings (filters out temporary files)

### Pattern Optimization
- **Automatic Combining**: Merges 20+ regex patterns into single OR expressions for performance
- **Validation**: Comprehensive regex pattern validation with user-friendly error messages
- **Template Variables**: Handles complex template variable substitution in manifest processing

### API Design
- **Blueprint Architecture**: Modular organization with logical separation
- **Dependency Injection**: Clean parameter passing for shared resources (fetch_manager)
- **Error Handling**: Consistent error responses with detailed messages
- **Performance**: Optimized for large-scale regex filtering and database operations

## Implementation Notes

- Manifest patterns are generated from destinations + pretty_name, not mapping keys
- Template variables use precise regex patterns for version numbers, build numbers, platforms
- Pattern optimization prevents database performance issues with many concurrent filters
- All API responses use orjson for consistent JSON serialization