# CWhitelist Backend — Modern Whitelist API & Admin Console

<div align="center">
  <br>
  <em>📡 API-first backend and admin interface for CWhitelist — a modern whitelist management system for Minecraft.</em>
</div>

<p align="center">
  <a href="https://github.com/SkyDreamLG/cwhitelist-backend/releases"><img alt="release" src="https://img.shields.io/github/v/release/SkyDreamLG/cwhitelist-backend?style=for-the-badge&color=4A90E2"></a>
  <a href="https://github.com/SkyDreamLG/cwhitelist-backend/issues"><img alt="issues" src="https://img.shields.io/github/issues/SkyDreamLG/cwhitelist-backend?style=for-the-badge&color=FF6B6B"></a>
  <a href="https://github.com/SkyDreamLG/cwhitelist-backend"><img alt="repo" src="https://img.shields.io/badge/repo-SkyDreamLG/cwhitelist--backend-6f42c1?style=for-the-badge"></a>
</p>

---

English | [中文](./README_CN.md)

A lightweight Flask backend for CWhitelist that exposes a REST API for whitelist synchronization and management, stores entries and logs, and ships with a web admin UI (templates included). It is designed to be used as the central authority for whitelist data when integrated with the CWhitelist Minecraft mod (or other clients).

## Key Features

- RESTful API with token-based authentication
- Health check endpoint for easy monitoring
- Whitelist sync endpoint (filtering for active / server-specific entries)
- Add / delete whitelist entries via API (supports name, uuid, ip)
- Login event logging endpoint for client-side login attempts
- Admin web UI (Flask templates) with API documentation pages
- SQLite by default, configurable via environment variables
- Session and upload folder handling, ready for small-to-medium deployments
- CLI-friendly startup script with optional GUI configuration prompts

## Quick Start

Prerequisites:
- Python 3.8+ (3.10+ recommended)
- pip

1. Clone
```bash
git clone https://github.com/SkyDreamLG/cwhitelist-backend.git
cd cwhitelist-backend
```

2. Create and activate a virtual environment
```bash
python -m venv venv
source venv/bin/activate   # on Windows: venv\Scripts\activate
```

3. Install dependencies
```bash
pip install -r requirements.txt
```
(If the repository does not include requirements.txt, install Flask and SQLAlchemy: `pip install Flask Flask-Login Flask-Session SQLAlchemy` plus any other optional packages used.)

4. Run the app
```bash
# Simple run (default host 0.0.0.0, port 5000)
python app.py

# With explicit options
python app.py --host 0.0.0.0 --port 5000 --no-gui
```

5. Open the admin UI
- By default the app prints a URL (e.g. http://127.0.0.1:5000). Browse to it to see the web UI and API docs.

## Configuration

Configuration is provided via the `config.py` classes and environment variables. Important options:

- SECRET_KEY — Flask secret key (env: SECRET_KEY)
- TIMEZONE — default timezone (env: TIMEZONE)
- DATABASE_URL — SQLAlchemy connection string (env: DATABASE_URL). Defaults to:
  sqlite:///instance/cwhitelist.db
- SESSION_TYPE — default: filesystem
- PERMANENT_SESSION_LIFETIME — default: 60 minutes
- API_PREFIX — default: `/api`
- API_VERSION — default: `v1`
- UPLOAD_FOLDER — directory for file uploads

You can set the `FLASK_CONFIG` environment variable to select a config class (e.g. `config.DevelopmentConfig` or `config.ProductionConfig`) as implemented in config.py.

Example (Linux / macOS):
```bash
export FLASK_CONFIG=config.DevelopmentConfig
export SECRET_KEY="change-me-in-production"
export DATABASE_URL="sqlite:///instance/cwhitelist.db"
python app.py --no-gui
```

## API Overview

Base path: {host}{API_PREFIX} (default: /api)

- GET /api/health
  - Health check (no authentication required)
  - Example response:
  ```json
  {
    "success": true,
    "status": "ok",
    "timestamp": "2024-01-01T00:00:00Z",
    "service": "CWhitelist API",
    "version": "1.0.0"
  }
  ```

- GET /api/whitelist/sync
  - Returns whitelist entries.
  - Authentication: token required (header or query param)
  - Query params:
    - server_id (optional)
    - only_active (default true)
    - include_expired (optional)
  - Example:
    ```
    curl -H "Authorization: Bearer YOUR_TOKEN" "http://host:5000/api/whitelist/sync?only_active=true"
    ```

- POST /api/whitelist/entries
  - Add a whitelist entry
  - Body (JSON): { "type": "name|uuid|ip", "value": "<value>", "description": "", "expires_at": "ISO8601", "is_active": true }
  - Requires token with write permission

- DELETE /api/whitelist/entries/<type>/<value>
  - Delete an entry by type and value
  - Requires token with delete permission

- POST /api/login/log
  - Log a player login attempt (player_name, player_uuid, player_ip, allowed, check_type)
  - Requires token with write permission

- GET /api/tokens/verify
  - Verify token status & permissions

Authentication:
- Header: Authorization: Bearer <token> (recommended)
- Or: ?token=<token> as fallback (both options supported by the API)

Permissions (token scopes in the system):
- Read: sync whitelist
- Write: add entries / log events
- Delete: delete entries
- Manage: admin operations (user/token management)

See the built-in API docs page (templates/api_docs.html) for request/response examples.

## File Layout (selected)

```
.
├── app.py                 # Application entrypoint and startup CLI
├── config.py              # Configuration classes and defaults
├── routes/
│   └── api.py             # API endpoints (health, sync, add/delete entries, login logs)
├── models/                # DB models (WhitelistEntry, Token, Log, etc.)
├── templates/             # Admin UI & API documentation templates
├── instance/              # default database file location (sqlite)
└── requirements.txt       # Python dependencies (if present)
```

## Database

Default: SQLite at instance/cwhitelist.db (configurable via DATABASE_URL).

If running in production, use a production-grade DB (Postgres or MySQL) and configure DATABASE_URL accordingly.

Example:
```
export DATABASE_URL="postgresql://user:password@db_host:5432/cwhitelist"
```

## Running in Production

Recommended options:

- Gunicorn (WSGI):
  ```
  pip install gunicorn
  gunicorn -w 4 -b 0.0.0.0:5000 "app:app"
  ```

- Docker:
  - (If you add a Dockerfile) build and run with docker, map ports and mount persistent storage for database and uploads.

- Systemd service:
  - Create a systemd unit that activates your virtualenv and runs Gunicorn (or supervisord).

Security recommendations:
- Set a strong SECRET_KEY
- Serve via HTTPS (reverse proxy like Nginx + TLS)
- Use production DB and enable proper DB backups
- Protect admin UI behind authentication and restrict access

## Development & Tests

- Create virtualenv and install dev dependencies from requirements.txt
- Run locally with:
  ```
  python app.py --debug
  ```
- The app includes templates that document the API; use them to verify endpoint behavior.

If you add tests, we recommend using pytest and including a CI workflow.

## Troubleshooting

- "Database locked" with SQLite:
  - Use a DB better suited for concurrent writes (Postgres) in production.
- Token authentication errors:
  - Verify token exists in the DB and has required permissions; use /api/tokens/verify.
- API returns 403 on delete/write:
  - Token lacks required permission scopes.

Check logs (the backend stores logs via the Log model and may write to console depending on configuration).

## Contributing

Contributions welcome — please follow these steps:
1. Fork the repo
2. Create a feature branch: git checkout -b feature/your-feature
3. Commit and push: git commit -m "Add feature" && git push
4. Open a Pull Request

Please include tests and documentation for new features.

## License & Acknowledgements

- See repository LICENSE file for license details (if present).
- Thanks to contributors and the community for feedback and testing.

## Support

- Issues: https://github.com/SkyDreamLG/cwhitelist-backend/issues
- Email: 1607002411@qq.com

---

Built and maintained by the SkyDream team. If this project helps you, a ⭐ on GitHub is greatly appreciated!
```