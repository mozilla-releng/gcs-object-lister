# Static Assets Directory

This directory contains all frontend assets for the GCS Object Lister web application.

## Structure

- **`css/app.css`** - Custom styles and utility classes that extend Pico.css (multiple regex filter UI)
- **`js/`** - JavaScript modules for frontend functionality
  - `api.js` - API client and utility functions with error handling
  - `index.js` - Landing page logic (fetch management, live progress display, database size display)
  - `fetch.js` - Object viewer page logic (pagination, multiple regex filters, date/custom_time filters)
- **`index.html`** - Main landing page template with database size column
- **`fetch.html`** - Fetch detail/object viewer page template with enhanced filtering UI

## Frontend Architecture

Uses plain HTML/CSS/JS with ES6 modules. No bundlers or frameworks - keeps it simple and maintainable.

External dependencies loaded via CDN:
- Pico.css for base styling
- Font Awesome for icons

## Key Frontend Features

- **Live Progress**: Real-time object count updates during fetch (every 2 seconds polling)
- **Multiple Regex Filters**: Dynamic UI for adding/removing regex patterns with OR logic
- **Manifest Filtering**: URL-based manifest loading with automatic pattern generation and status feedback
- **Enhanced Filters**: Date range filtering and custom_time presence filtering
- **Database Size Display**: Shows calculated database size on landing page
- **Sort Options**: Name and time_created sorting (ascending/descending)
- **Responsive Design**: Clean, accessible interface with fieldset organization

## Manifest Integration

- **URL Input**: Users can enter Firefox manifest URLs for automatic pattern generation
- **Status Display**: Real-time feedback during manifest loading with success/error states
- **Database-Level Filtering**: "Matches Manifest" dropdown for fast filtering using pre-computed links
- **Object ID Display**: Shows manifest entry IDs for each matched object in the table
- **Recalculation**: Real-time manifest match recalculation without re-fetching objects
- **Clear Functionality**: Easy manifest clearing and filter management

## Manifest Filtering UI Components

### Custom Filtering Section
- **Matches Manifest Dropdown**: Three-state filter (All Files/Matches Manifest/Does Not Match Manifest)
- **Performance Optimization**: Uses database JOINs instead of runtime regex pattern matching
- **State Management**: Tracks filtering state independently from manifest pattern loading

### Enhanced Object Table
- **Manifest ID Column**: Displays manifest_entry_id for matched objects with visual styling
- **Conditional Display**: Shows numeric IDs for matches, dash (-) for non-matches
- **CSS Styling**: `.manifest-id` class for positive matches, `.no-manifest` for empty states

### Manifest Management Controls
- **Load Button**: Fetches and parses manifest from URL with template variable processing
- **Recalculate Button**: Re-runs object linking algorithm without re-fetching objects
- **Clear Button**: Removes manifest data and resets filtering state
- **Status Feedback**: Real-time loading states and error handling

## Frontend Architecture Evolution

### Phase 1: Runtime Pattern Matching
- Frontend received manifest patterns from API
- Client-side filtering using JavaScript regex
- Performance bottleneck with large object lists

### Phase 2: Database-Level Filtering (Current)
- Backend pre-computes object-to-manifest-entry links
- Frontend sends filter parameters to API
- Fast server-side JOIN operations for filtering
- Manifest IDs displayed for debugging and transparency

All JavaScript uses modern ES6+ features and module imports for clean separation of concerns.