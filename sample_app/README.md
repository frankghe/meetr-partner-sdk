# Meetr Sample App

A standalone example application demonstrating how a third-party partner integrates with the Meetr scheduling service.

## Overview

This app shows how a real partner application would:
- Authenticate users with its own email/password accounts
- Store the Meetr API key server-side (never exposed to the browser)
- Communicate with Meetr exclusively via the Partner API
- Manage meetings, customers, and participants through a web UI

## Quick Start (Developer Mode)

```bash
cd sample_app
python run.py --auto-setup
```

This automatically:
1. Creates a "Sample App" partner in Meetr (requires Meetr server running on port 8001)
2. Seeds an admin user (`admin@example.com` / `admin`)
3. Starts the app at http://localhost:8002

**Prerequisite:** Set `ADMIN_API_KEY` in your environment (from `.env.meetr`).

## Partner Setup (Production-like)

1. Copy and configure environment:
   ```bash
   cp .env.example .env
   # Edit .env with your MEETR_API_URL and MEETR_API_KEY
   ```

2. Start the app:
   ```bash
   python run.py
   ```

3. Visit http://localhost:8002/setup to create your admin account.

4. Log in and start managing meetings.

## Architecture

```
Browser (HTMX + Jinja2)
    |
Sample App (FastAPI, port 8002)
    |--- Own SQLite DB (users, org config)
    |--- Meetr Partner API (HTTP, X-API-Key)
    |
Meetr Service (port 8001)
```

- **Separate process** — runs independently from the Meetr server
- **No Meetr imports** — communicates only via Partner API
- **Own database** — SQLite for users and organization config
- **Server-side API key** — stored in DB, never sent to the browser

## Directory Structure

```
sample_app/
├── run.py                  # Entry point
├── app/
│   ├── main.py             # FastAPI app factory
│   ├── config.py           # Environment-based config
│   ├── db.py               # SQLite database (users, org)
│   ├── auth.py             # Password hashing, session guards
│   ├── meetr_client.py     # HTTP client for Meetr Partner API
│   ├── routes/             # Route modules
│   ├── templates/          # Jinja2 templates
│   └── static/             # CSS, JS, Pico CSS, HTMX
├── tests/                  # pytest test suite
├── data/                   # SQLite DB (git-ignored)
├── requirements.txt
└── .env.example
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MEETR_API_URL` | `http://localhost:8001` | Meetr service URL |
| `MEETR_API_KEY` | — | Partner API key (from Meetr admin) |
| `APP_PORT` | `8002` | Port for the sample app |
| `APP_SECRET_KEY` | `sample-app-dev-key` | Session signing key |
| `DATABASE_PATH` | `data/sample_app.db` | SQLite database path |
| `MEETR_CUSTOMER_ID` | — | Optional default customer ID |

## Running Tests

```bash
# From the project root
python -m pytest sample_app/tests/ -v
```
