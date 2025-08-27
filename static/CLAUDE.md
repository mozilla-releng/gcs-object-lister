# Static Assets Directory

This directory contains all frontend assets for the GCS Storage Manager web application.

## Structure

- **`css/app.css`** - Custom styles and utility classes that extend Pico.css
- **`js/`** - JavaScript modules for frontend functionality
  - `api.js` - API client and utility functions
  - `index.js` - Landing page logic (fetch management, status polling)
  - `fetch.js` - Object viewer page logic (pagination, filtering, download)
- **`index.html`** - Main landing page template
- **`fetch.html`** - Fetch detail/object viewer page template

## Frontend Architecture

Uses plain HTML/CSS/JS with ES6 modules. No bundlers or frameworks - keeps it simple and maintainable.

External dependencies loaded via CDN:
- Pico.css for base styling
- Font Awesome for icons

All JavaScript uses modern ES6+ features and module imports for clean separation of concerns.