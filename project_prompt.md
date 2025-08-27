You are an expert full‑stack engineer. Build a local‑only web application that manages and explores artifacts in Google Cloud Storage (GCS). Implement everything end‑to‑end (frontend + backend + Docker) exactly as specified below. Do not ask questions—make reasonable defaults and deliver a working project. Provide complete code for every file with accurate paths.

### High-level intent

* Manage objects in a pre‑configured GCS bucket.
* Runs locally via Docker; user visits [http://localhost:8080/](http://localhost:8080/).
* No authentication.
* Favor simplicity and maintainability over fanciness.

---

## Frontend requirements

* Tech: Plain HTML + CSS + JS (no bundlers). Use [Pico.css](https://picocss.com/) and [Font Awesome](https://fontawesome.com/) via CDN for minimal styling/icons.
* Landing page (/):

  * Button: “Fetch current files” → triggers a backend operation that starts an async fetch from the configured bucket.

    * UI must indicate when a fetch is running (spinner + disabled button + status text).
    * Only one fetch may run at a time—reflect 409/locked state clearly.
  * List of available fetches (historical runs). Each entry shows: db name (timestamp), start time, end time, object count.

    * For each fetch:

      * Open → navigates to `/{db-name}`.
      * Delete → removes this fetch (and its DB file) after confirmation.
* Fetch view (/{db-name}):

  * Simple table or list of objects with paging.
  * Regex search input to filter by object name (server-side filtering).

    * Show validation error if regex is invalid.
  * Button: “Download file list” → downloads a plain text file (one object name per line) for the current filter.
* Keep the code modular and readable (small JS modules, no frameworks).
* Accessibility basics: semantic HTML, labels for inputs, focus states.
* Performance: paginate results (default page size 200), show total matches.

---

## Backend requirements

* Language: Python 3.11.
* Framework: Flask (keep dependencies minimal).
* Direct dependencies only:

  * `Flask` (web framework)
  * `google-cloud-storage` (GCS access)
  * built-in `sqlite3` (standard library) — use SQLite, not MySQL
  * `orjson` (JSON serialization)
* No other third-party deps (avoid SQLAlchemy, Celery, etc.).
* Run as a single service; dev-grade WSGI is fine for local use.
* ADC / credentials: The app must use the local user’s gcloud login via Application Default Credentials (ADC). In Docker, mount the host’s `${HOME}/.config/gcloud` into the container and use default credentials automatically.

### Data persistence & layout

* Use a named Docker volume (e.g., `data:`) mounted at `/data`.
* For each fetch, create one SQLite database file under `/data/fetches/` named with the UTC start timestamp, e.g. `2025-08-18T14-32-10Z.db` (use `:` replaced with `-` for filesystem safety).
* Schema (per fetch DB):

  * Table `fetch` (single row):

    * `id` INTEGER PRIMARY KEY (always 1)
    * `bucket_name` TEXT
    * `prefix` TEXT NULL
    * `started_at` TEXT (UTC ISO-8601)
    * `ended_at` TEXT NULL (UTC ISO-8601)
    * `record_count` INTEGER DEFAULT 0
    * `status` TEXT CHECK(status IN ('running','success','error','canceled'))
    * `error` TEXT NULL
  * Table `objects`:

    * `name` TEXT PRIMARY KEY
    * `size` INTEGER
    * `updated` TEXT (UTC ISO-8601)
    * `raw` BLOB (store compact JSON bytes via `orjson.dumps`)
* Listing historical fetches (for landing page) is done by scanning `/data/fetches/*.db` and reading the single row from each DB’s `fetch` table.

### Async fetch behavior

* Only one fetch may run at a time across the whole app. Enforce with an in‑process lock and a simple persisted lock file (e.g., `/data/fetches/.lock`) to prevent accidental parallel runs if the server restarts mid-fetch.
* Start a background thread to stream GCS objects into the new DB:

  * Record `started_at` immediately, set `status='running'`.
  * Iterate `list_blobs(bucket, prefix=ENV_PREFIX)`; for each blob, persist a row in `objects`:

    * `name`, `size`, `updated` (blob.updated in UTC ISO), `raw` = full metadata dict.

      * Ensure full metadata by calling `blob.reload()` once per blob (OK for local tool; optimize with batch/retry).
  * Use SQLite pragmas for bulk insert speed (`journal_mode=WAL`, `synchronous=OFF` during ingestion, restore defaults after).
  * Commit in batches (e.g., 1,000 rows) to avoid memory growth.
  * On completion, set `record_count`, `ended_at`, `status='success'`.
  * On error, set `status='error'` and `error` message; release lock.

### REST API (JSON using `orjson`)

All responses must be JSON (except the “download list”, which is `text/plain`). Handle errors cleanly with proper HTTP status codes and messages.

* `GET /api/health` → `{status:"ok"}`
* `GET /api/status` → Current global fetch status: `{running: bool, started_at?, db_name?, processed?, message?}`
* `POST /api/fetches` → Starts a new fetch. Body: `{bucket?:string, prefix?:string}` (optional overrides; default from env).

  * 409 Conflict if a fetch is already running.
  * Response: `{db_name, started_at}`
* `GET /api/fetches` → List all fetches (read each DB’s `fetch` row). Support query `order=started_at_desc` by default.
* `DELETE /api/fetches/{db_name}` → Delete the DB file. 400/404/409 for invalid, missing, or locked/running.
* `GET /api/fetches/{db_name}/objects` → Paginated listing with optional regex filter.

  * Query: `regex`, `page` (default 1), `page_size` (default 200, max 1000), `sort` (`name_asc` default).
  * Regex is Python re (case-sensitive by default). Validate and return 400 on invalid patterns.
  * Implement server‑side filtering efficiently: if regex present, stream names and filter in Python; otherwise use SQL directly.
  * Response: `{items:[{name,size,updated}], total, page, page_size}`
* `GET /api/fetches/{db_name}/download` → Same filter params as above. Returns `text/plain` with one object name per line and `Content-Disposition: attachment; filename="{db_name}_files.txt"`.

### Environment configuration

* Read from environment (with sane defaults):

  * `APP_HOST=0.0.0.0`
  * `APP_PORT=8080`
  * `BUCKET_NAME` (required unless provided at POST time)
  * `GCS_PREFIX` (optional)
  * `DATA_DIR=/data/fetches`
* Validate `BUCKET_NAME` on startup; log a clear message if missing.

### Docker & Compose

* Provide a minimal Dockerfile based on `python:3.11-slim`:

  * Install system packages only if required by `google-cloud-storage` (keep minimal).
  * Copy app, install `requirements.txt`.
  * Set `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`.
  * Expose 8080; `CMD ["python","-m","app.main"]` (or equivalent).
* Provide docker-compose.yml:

  * Service `app`:

    * `build: .`
    * `ports: ["8080:8080"]`
    * `volumes`:

      * named volume `data:/data`
      * `${HOME}/.config/gcloud:/root/.config/gcloud:ro` (document Windows path alternative)
    * `env_file: .env`
    * `restart: unless-stopped`
  * `volumes: { data: {} }`
* Provide a `.env.example` that users can copy to `.env` and set `BUCKET_NAME`.

### Static frontend hosting

* Serve static files from `/static` via Flask (`send_from_directory`).
* Pages:

  * `/` → `static/index.html` (landing page)
  * `/{db_name}` → `static/fetch.html` (viewer)
* JS modules:

  * `static/js/api.js` (fetch wrappers)
  * `static/js/index.js` (landing page logic)
  * `static/js/fetch.js` (viewer logic)
* CSS: rely on Pico.css CDN + a tiny `static/css/app.css` for spacing/utility classes.

### UX details to implement

* Disable “Fetch current files” button and show spinner while `running=true`; poll `/api/status` every 2s.
* On landing page, show a table of fetches; each row has Open and Delete (trash icon) actions.
* Viewer page:

  * Regex input + “Apply” button.
  * Results table with Name, Size (humanized), Updated.
  * Pagination controls (Prev/Next).
  * “Download file list” button; when clicked, trigger a file download using current filter params.
* Display clear error toasts/messages for invalid regex, API errors, or conflicts.

### Implementation constraints & quality bar

* Type hints and docstrings in Python.
* Use context managers for SQLite connections; set row factory and pragmas appropriately.
* Avoid N+1 mistakes; batch commits during ingestion.
* Centralize JSON responses using `orjson` for dumps.
* Clean error handling with `@app.errorhandler`.
* Keep modules small and cohesive: e.g., `gcs.py`, `db.py`, `fetcher.py`, `api.py`, `main.py`.
* Logging to stdout with concise progress messages (processed count, rate).
* No external task queues; use `threading.Thread` with a global fetch manager + lock + persisted lock file.
* Unit of deletion is the DB file; ensure safe path handling (no directory traversal).
* Regex compile failures return HTTP 400 with message `{"error":"invalid_regex","details":...}`.
* Large buckets are acceptable; the tool is local and may run for a long time.

### Deliverables (as text in your response)

1. Project tree (paths only).
2. All source files in full, grouped by file path with fenced code blocks. Include at least:

   * `app/main.py` (Flask app factory or simple app bootstrap)
   * `app/api.py` (routes)
   * `app/db.py` (SQLite helpers, schema creation)
   * `app/fetcher.py` (background fetch thread & lock)
   * `app/gcs.py` (GCS client utilities)
   * `app/utils.py` (time/format helpers, humanize size)
   * `static/index.html`, `static/fetch.html`
   * `static/js/api.js`, `static/js/index.js`, `static/js/fetch.js`
   * `static/css/app.css`
   * `Dockerfile`, `docker-compose.yml`, `.env.example`, `requirements.txt`, `README.md`
3. README.md with:

   * Quick start (`cp .env.example .env`, set `BUCKET_NAME`, `docker compose up --build`).
   * Note on gcloud creds (ensure `gcloud auth application-default login`).
   * Troubleshooting (permission denied, missing bucket, Windows credentials path).
   * What data is stored, and how to delete it safely.
4. API reference section (method, path, params, example requests/responses).
5. Acceptance tests / manual test plan with steps:

   * Start app.
   * Trigger fetch; observe lock and status.
   * Open a fetch; search with regex; paginate.
   * Download list; verify text file contents.
   * Delete a fetch; verify it disappears.

Important: Output must be directly copy‑pastes of the full working code. Avoid placeholders like “implement here”. Keep dependencies to exactly:

```
Flask
google-cloud-storage
orjson
```

(Use Python’s built‑in `sqlite3` module; do not add ORM or other libs.)

---

### Optional but nice-to-have (implement if trivial without extra deps)

* Return counts quickly with `SELECT COUNT(*)` for regex = empty.
* Graceful shutdown: ensure lock released if process dies mid-run (e.g., on next startup, clear stale lock older than N hours).
* Simple ETag/Cache headers for static assets.

---

Now generate the COMPLETE project exactly as requested.

---
