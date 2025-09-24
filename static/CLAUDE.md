# Static Assets Directory

This directory contains all frontend assets for the GCS Storage Manager web application.

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
- **Enhanced Filters**: Date range filtering and custom_time presence filtering
- **Database Size Display**: Shows calculated database size on landing page
- **Sort Options**: Name and time_created sorting (ascending/descending)
- **Responsive Design**: Clean, accessible interface that works on all devices

All JavaScript uses modern ES6+ features and module imports for clean separation of concerns.