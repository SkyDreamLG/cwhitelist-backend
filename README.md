# CWhitelist Backend — Modern Whitelist API & Admin Console

<div align="center">
  <br>
  <em>API-first backend and admin interface for CWhitelist — a modern whitelist management system for Minecraft servers.</em>
</div>

<p align="center">
  <a href="https://github.com/SkyDreamLG/cwhitelist-backend/releases"><img alt="release" src="https://img.shields.io/github/v/release/SkyDreamLG/cwhitelist-backend?style=for-the-badge&color=4A90E2"></a>
  <a href="https://github.com/SkyDreamLG/cwhitelist-backend/issues"><img alt="issues" src="https://img.shields.io/github/issues/SkyDreamLG/cwhitelist-backend?style=for-the-badge&color=FF6B6B"></a>
  <a href="https://github.com/SkyDreamLG/cwhitelist-backend"><img alt="repo" src="https://img.shields.io/badge/repo-SkyDreamLG/cwhitelist--backend-6f42c1?style=for-the-badge"></a>
</p>

---

English | [中文](./README_CN.md)

A lightweight Flask backend for CWhitelist that exposes a REST API for whitelist synchronization and management, stores entries and logs, and ships with a web admin UI. It is designed as the central authority for whitelist data when integrated with the CWhitelist Minecraft mod or other clients.

**Current version: 2.1.0**

## Key Features

- RESTful API with token-based authentication — tokens are hashed (irreversible storage)
- Fine-grained permission system (`whitelist:read/write/delete`, `login:log`) with presets and `*:*` wildcard
- Brute-force protection on login (IP-based rate limiting)
- Server health check with heartbeat tracking and auto-offline detection
- Whitelist sync endpoint (server-scoped, supports name/uuid/ip)
- Add / edit / delete whitelist entries via API with `server_id` scoping
- Batch whitelist operations (enable/disable/delete)
- Login / logout event logging with session duration tracking
- Player analytics dashboard — online time charts, IP geolocation, server vitality rankings
- Admin web UI with i18n support (简体中文 / English)
- Server status monitoring with automatic session cleanup
- Timezone-aware time display across all pages
- One-line dev/production mode toggle (`DEV_MODE` in config.py)
- Auto-generated SECRET_KEY persisted to file — no manual config needed
- CLI-friendly startup with optional GUI configuration

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

4. Run the app
```bash
python app.py

# With explicit options
python app.py --host 0.0.0.0 --port 5000 --no-gui
```

5. Open the admin UI
- By default the app prints a URL (e.g. http://127.0.0.1:5000). Browse to it for the web UI and API docs.
- On first run, complete the OOBE setup wizard to create an admin account.

## Configuration

Configuration via `config.py` and environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DEV_MODE` | Dev/production switch (line 8 in `config.py`) | `True` (dev) |
| `SECRET_KEY` | Flask secret key | Auto-generated, persisted to `instance/secret_key` |
| `TIMEZONE` | Default timezone | `Asia/Shanghai` |
| `DATABASE_URL` | SQLAlchemy connection string | `sqlite:///instance/cwhitelist.db` |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated) | Empty (same-origin only) |

```bash
export DATABASE_URL="sqlite:///instance/cwhitelist.db"
python app.py --no-gui
```

Switch to production: edit `config.py` line 8 to `DEV_MODE = False`.

## API Overview

Base path: `{host}/api`

### Health Check
```
GET /api/health?server_id=<id>
```
No authentication required. `server_id` is **required** and doubles as a server heartbeat. If a server misses heartbeats for 60+ seconds, all its open player sessions are auto-closed.

```json
{
  "success": true,
  "status": "ok",
  "server_id": "lobby",
  "timestamp": "2026-07-23T00:00:00Z",
  "service": "CWhitelist API",
  "version": "2.1.0"
}
```

### Sync Whitelist
```
GET /api/whitelist/sync?server_id=<id>&only_active=true
```
Token required (`whitelist:read`). `server_id` is **required**.

### Add Whitelist Entry
```
POST /api/whitelist/entries
```
Token required (`whitelist:write`). Body:
```json
{
  "type": "name",
  "value": "PlayerName",
  "server_id": "lobby",
  "description": "VIP Player",
  "expires_at": "2026-12-31T23:59:59Z"
}
```

### Update Whitelist Entry
```
PUT /api/whitelist/entries/<entry_id>
```
Token required (`whitelist:write`). All fields are optional — only provided fields will be updated. Body:
```json
{
  "value": "NewPlayerName",
  "description": "Updated description",
  "is_active": false
}
```

### Delete Whitelist Entry
```
DELETE /api/whitelist/entries/<type>/<value>?server_id=<id>
```
Token required (`whitelist:delete`). `server_id` is **required**.

### Log Login Event
```
POST /api/login/log
```
Token required (`login:log`). Body:
```json
{
  "player_name": "SkyDream",
  "player_uuid": "xxx-xxx-xxx",
  "player_ip": "192.168.1.100",
  "allowed": true,
  "server_id": "lobby",
  "check_type": "name"
}
```

### Log Logout Event
```
POST /api/login/logout
```
Token required (`login:log`). Body:
```json
{
  "player_name": "SkyDream",
  "player_uuid": "xxx-xxx-xxx",
  "player_ip": "192.168.1.100",
  "server_id": "lobby"
}
```
Automatically calculates online duration. If no open session exists (e.g. server just recovered), creates one using the server's recovery time as login time.

### Verify Token
```
GET /api/tokens/verify
```
Any valid token can call this. Returns token status, permissions, and validity.

### Authentication
- Header: `Authorization: Bearer <token>` (recommended)
- Or: `?token=<token>` query parameter

### Token Permissions

Fine-grained permission strings — each token can have multiple:

| Permission | Endpoint |
|------------|----------|
| `whitelist:read` | `GET /api/whitelist/sync` |
| `whitelist:write` | `POST/PUT /api/whitelist/entries` |
| `whitelist:delete` | `DELETE /api/whitelist/entries/<type>/<value>` |
| `login:log` | `POST /api/login/log`, `POST /api/login/logout` |
| `*:*` | All endpoints (super admin) |

**Preset combinations**:
| Preset | Includes |
|--------|----------|
| Server (Full) | `whitelist:read` + `whitelist:write` + `whitelist:delete` + `login:log` |
| Server (Basic) | `whitelist:read` + `login:log` |
| Read Only | `whitelist:read` |

## Whitelist JSON Import/Export

### Export format
```json
[
  {
    "type": "name",
    "value": "SkyDream_LG",
    "server_id": "lobby",
    "description": "Admin player",
    "created_by": "admin",
    "created_at": "2026-07-23T10:00:00",
    "expires_at": null,
    "is_active": true
  },
  {
    "type": "uuid",
    "value": "117a97e0-10ad-338d-aae2-54c4ec32959f",
    "server_id": "survival",
    "description": "",
    "created_by": "admin",
    "created_at": "2026-07-23T10:05:00",
    "expires_at": "2026-12-31T23:59:59",
    "is_active": true
  }
]
```

### Import format
Minimal required fields per entry:
```json
[
  {"type": "name", "value": "PlayerName", "server_id": "lobby"},
  {"type": "uuid", "value": "117a97e0-10ad-338d-aae2-54c4ec32959f", "server_id": "lobby"},
  {"type": "ip", "value": "192.168.1.100", "server_id": "survival"}
]
```
- `type`: `name`, `uuid`, or `ip` (required)
- `value`: the entry value (required)
- `server_id`: can be specified per-entry in JSON, or set globally via the import form (required)
- `description`: optional
- `is_active`: optional, defaults to `true`

## Web Admin UI

The built-in web interface provides:

- **Dashboard** — KPI cards, login trend charts (whitelist/guest breakdown), quick actions
- **Whitelist Management** — CRUD with server_id scoping, JSON import/export, **batch enable/disable/delete**
- **Login Logs** — filterable by server, event type (allow/deny/logout), player search
- **System Logs** — with health check filtering, log statistics
- **User Analytics** — per-player online timeline, session records, IP geolocation, server vitality overview with player rankings
- **Token Management** — create/manage API tokens with fine-grained permission checkboxes and presets
- **Settings** — timezone, language, server configuration
- **API Documentation** — built-in interactive docs

i18n: Switch between 简体中文 and English via the topbar language selector.

## File Layout

```
.
├── app.py                     # Application entrypoint
├── config.py                  # Configuration classes (DEV_MODE switch)
├── routes/
│   ├── api.py                 # All API endpoints
│   ├── web.py                 # Web UI routes (incl. batch operations)
│   └── auth.py                # Authentication routes (incl. rate limiting)
├── models/                    # DB models
│   ├── whitelist.py           # WhitelistEntry
│   ├── token.py               # API Token (hashed storage + JSON permissions)
│   ├── log.py                 # System/Login logs
│   ├── session.py             # LoginSession (login/logout tracking)
│   ├── server_status.py       # Server heartbeat tracking
│   ├── user.py                # User accounts
│   └── setting.py             # System settings
├── utils/
│   ├── auth.py                # Auth decorators (fine-grained permissions)
│   └── permissions.py         # Permission constants
├── templates/                 # Jinja2 templates
├── static/                    # CSS/JS assets
├── translations/              # i18n (.po/.mo files)
├── instance/                  # default SQLite database + secret_key
└── requirements.txt
```

## Running in Production

**Gunicorn (WSGI):**
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 "app:app"
```

**Security recommendations:**
- Set `DEV_MODE = False` in `config.py`
- Serve via HTTPS (reverse proxy like Nginx + TLS)
- Use PostgreSQL/MySQL for production
- Restrict admin UI access

## Development

```bash
python app.py --debug
```

Update translations after template changes:
```bash
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
pybabel compile -d translations
```

## Troubleshooting

- **SQLite "Database locked"**: Use PostgreSQL for concurrent writes in production
- **Token 401/403**: Verify token exists and has the required permission (e.g. `whitelist:read`)
- **Missing `server_id` column**: Run `ALTER TABLE whitelist_entries ADD COLUMN server_id VARCHAR(36) NOT NULL DEFAULT 'default'`
- **Missing `login_sessions` table**: Ensure Flask app starts with model imports to auto-create tables, or run manual migration

## License

GNU General Public License v3.0

## Support

- Issues: https://github.com/SkyDreamLG/cwhitelist-backend/issues
- Email: 1607002411@qq.com

---

Built and maintained by the SkyDream team. If this project helps you, a ⭐ on GitHub is greatly appreciated!
