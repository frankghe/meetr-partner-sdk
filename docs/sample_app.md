# Sample App — Partner Integration Showcase

## Overview

The Sample App is a minimal standalone application that demonstrates how a partner company would integrate with the Meetr scheduling service. It showcases the typical workflow of a real partner: a company owner registers their organization, adds team members, and schedules meetings among them.

**Key principle**: The sample app communicates with Meetr exclusively via the Partner API — no admin API access, no direct database imports. It represents what a real third-party integration would look like.

---

## 1. Objective

The current sample app gives overly broad access to Meetr internals — any user can see all partners' customers and participants, which does not reflect how a real partner's application would work.

The revised sample app will showcase a **scoped, realistic partner integration**:

1. **Register as a company owner** — create an account in the sample app
2. **Add team members** — define participants (people) who belong to the company; these are private to the company's customer scope in Meetr
3. **Schedule meetings** — create meetings among the defined team members
4. **Monitor meeting progress** — track outreach, availability collection, slot selection, and confirmations

Declared participants are **private to the customer** who created them — they are not visible to other customers or partners.

---

## 2. User Workflow

### Pre-requisite

The Meetr API key and customer ID are pre-configured server-side (via environment variables or `--auto-setup`). The sample app never exposes these to the user — it just works.

### User Flow

1. **Register** an account (email, password, display name) — the user is now the company owner
2. **Log in** with email/password
2. **Manage team members** (participants):
   - Add a new team member: first name, last name, phone number, timezone, language, communication preferences
   - View and edit existing team members
   - Team members are stored in the sample app's local DB, scoped to the logged-in user
3. **Schedule a meeting**:
   - Enter meeting purpose and context
   - Select participants from the team member list (not free-form entry)
   - Set scheduling window, duration, and timezone
   - Submit -> Meetr begins the scheduling process
4. **Monitor meetings**:
   - Dashboard shows meeting stats and recent activity
   - Meeting detail shows participant outreach status, availability, and actions
   - Trigger actions: start outreach, select slot, send notifications
   - Live SSE event stream for real-time updates

---

## 3. What Changes from the Current App

| Aspect | Current | New |
|--------|---------|-----|
| **Customers** | Users can list/create/manage Meetr customers | Removed — the app operates within a single, pre-configured customer scope |
| **Participants** | Users can see all participants across the partner | Users manage only their own team members (participants scoped to their customer) |
| **Meeting creation** | Free-form participant entry (name + phone inline) | Select from pre-defined team members |
| **Scope** | Broad access to all Meetr partner features | Focused on the scheduling workflow a real partner would use |
| **Navigation** | Dashboard, Meetings, Customers, Participants, Settings | Dashboard, Team Members, Meetings, Settings |

### Pages Removed
- **Customers list/create/detail** (`/customers/*`) — the app operates within a single customer; no need to manage multiple customers

### Pages Renamed
- **Participants** -> **Team Members** (`/participants/*` -> `/team/*`) — better reflects the business concept for a partner app

### Pages Updated
- **Meeting creation** — participant entry changes from inline form rows to a picker that selects from existing team members
- **Dashboard** — simplified to show only the company's meetings
- **Settings** — shows company name and Meetr connection status; removes customer management

---

## 4. Architecture

### System Diagram

```
Browser (HTMX + Jinja2)
    |
Sample App (FastAPI, port 8002)
    |--- Own SQLite DB (users, org config)
    |--- Meetr Partner API (HTTP, X-API-Key + X-Customer-Id)
    |
Meetr Service (port 8001)
```

- **Separate process** — runs independently from the Meetr server
- **No Meetr imports** — communicates only via Partner API
- **Own database** — SQLite for users and organization config
- **Server-side API key** — from env vars, never sent to the browser
- **Customer-scoped** — all API calls include `X-Customer-Id` header, ensuring participant/data isolation

### Directory Structure

```
sample_app/
├── run.py                  # Entry point
├── app/
│   ├── main.py             # FastAPI app factory
│   ├── config.py           # Environment-based config
│   ├── db.py               # SQLite database (users, org)
│   ├── auth.py             # Password hashing, session guards
│   ├── meetr_client.py     # HTTP client for Meetr Partner API
│   ├── routes/
│   │   ├── auth_routes.py  # Login, register, logout
│   │   ├── dashboard.py    # Dashboard with stats
│   │   ├── team.py         # Team member CRUD (was participants.py)
│   │   ├── meetings.py     # Meeting CRUD + actions + SSE
│   │   └── settings.py     # Organization settings
│   ├── templates/
│   │   ├── layout.html
│   │   ├── login.html
│   │   ├── register.html
│   │   ├── dashboard.html
│   │   ├── settings.html
│   │   ├── team/
│   │   │   ├── list.html
│   │   │   ├── create.html
│   │   │   └── detail.html
│   │   ├── meetings/
│   │   │   ├── list.html
│   │   │   ├── create.html
│   │   │   └── detail.html
│   │   └── partials/
│   │       ├── team_rows.html
│   │       ├── meeting_rows.html
│   │       ├── participant_cards.html
│   │       ├── dashboard_stats.html
│   │       └── event_log.html
│   └── static/
│       ├── app.css
│       ├── app.js
│       ├── htmx.min.js
│       └── pico.min.css
├── tests/
├── data/
├── requirements.txt
└── .env.example
```

### Routing

#### Authentication Routes

| Route | Handler | Description |
|-------|---------|-------------|
| `GET /login` | `login_page()` | Login form |
| `POST /login` | `login_action()` | Authenticate user |
| `GET /register` | `register_page()` | Registration form |
| `POST /register` | `register_action()` | Create user account |
| `POST /logout` | `logout_action()` | Clear session |

#### Page Routes (require login)

| Route | Handler | Template | Description |
|-------|---------|----------|-------------|
| `GET /` | `dashboard()` | `dashboard.html` | Stats + recent meetings |
| `GET /team` | `team_list()` | `team/list.html` | Team member list |
| `GET /team/new` | `create_team_member_form()` | `team/create.html` | Add team member form |
| `GET /team/{id}` | `team_member_detail()` | `team/detail.html` | View/edit team member |
| `GET /meetings` | `meeting_list()` | `meetings/list.html` | Meeting list with filters |
| `GET /meetings/new` | `create_meeting_form()` | `meetings/create.html` | Create meeting with team member picker |
| `GET /meetings/{id}` | `meeting_detail()` | `meetings/detail.html` | Meeting detail + actions + SSE |
| `GET /settings` | `settings_page()` | `settings.html` | Org info + connection status |

#### Action Routes (POST)

| Route | Handler | Description |
|-------|---------|-------------|
| `POST /team` | `create_team_member_action()` | Create team member in local DB |
| `POST /team/{id}/update` | `update_team_member_action()` | Update team member in local DB |
| `POST /meetings` | `create_meeting_action()` | Create meeting in Meetr |
| `POST /meetings/{id}/cancel` | `cancel_meeting_action()` | Cancel meeting |
| `POST /meetings/{id}/select-slot` | `select_slot_action()` | Trigger slot selection |
| `POST /meetings/{id}/notify` | `notify_action()` | Send confirmations |
| `POST /meetings/{id}/intervene` | `intervene_action()` | Send intervention instruction |
| `POST /meetings/{id}/outreach/{pid}/start` | `start_outreach_action()` | Start outreach for participant |
| `POST /meetings/{id}/outreach/{pid}/force-fail` | `force_fail_action()` | Force-fail outreach |

#### Partial Routes (HTMX fragments)

| Route | Handler | Description |
|-------|---------|-------------|
| `GET /partials/team-rows` | `team_rows_partial()` | Team member table body (from local DB) |
| `GET /partials/meeting-rows` | `meeting_rows_partial()` | Meeting table body |
| `GET /partials/participant-cards/{id}` | `participant_cards_partial()` | Participant cards for meeting |
| `GET /partials/dashboard-stats` | `dashboard_stats_partial()` | Dashboard summary |

#### SSE Route

| Route | Handler | Description |
|-------|---------|-------------|
| `GET /sse/meetings/{id}` | `sse_proxy()` | Proxied SSE events from Meetr |

### Meetr Client

The `MeetrClient` always sends both `X-API-Key` and `X-Customer-Id` headers on every request. This ensures all data (participants, meetings) is scoped to the company's customer in Meetr.

```python
class MeetrClient:
    def __init__(self, base_url: str, api_key: str, customer_id: str):
        # customer_id is required, not optional

    def _headers(self) -> dict:
        return {
            "X-API-Key": self._api_key,
            "X-Customer-Id": self._customer_id,  # always sent
        }
```

**Methods**:
- Meetings: `create_meeting`, `list_meetings`, `get_meeting`, `cancel_meeting`, `select_slot`, `notify_participants`, `intervene`
- Outreach: `start_outreach`, `get_outreach_detail`, `force_fail_outreach`

**Removed methods**:
- `list_customers`, `create_customer`, `get_customer`, `update_customer` — no longer needed since the app operates within a single customer scope
- `list_participants`, `create_participant`, `get_participant`, `update_participant` — participants (team members) are now managed in the local DB, not via Meetr API. Participant details are passed inline when creating a meeting.

### Database Schema

```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    company_name TEXT NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS participants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    phone_number TEXT NOT NULL,
    timezone TEXT DEFAULT 'UTC',
    language TEXT DEFAULT 'en',
    communication_modes TEXT DEFAULT '["whatsapp"]',
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

- **users** — company owners who register in the app. Each user represents a company.
- **participants** — team members defined by a user. `user_id` links each participant to the user who created them, ensuring they are private to that user/company. Participant details are passed inline to Meetr when creating a meeting — no Meetr-side participant ID is stored.
- The Meetr API key and customer ID are server-side config (env vars), not stored in the DB.

### Meeting Creation Flow

The key UX change: instead of typing participant details inline, the user selects from their own team members.

1. User navigates to **Create Meeting**
2. Form shows:
   - Meeting details: purpose, context, scheduling window, timezone, duration
   - **Team member picker**: checkboxes or multi-select of the user's team members (fetched from the local DB, filtered by `user_id`)
   - Optional: priority override per selected member
3. On submit, the app constructs the meeting payload using the selected participants' details from the local DB
4. Meetr creates the meeting and the user is redirected to the meeting detail page

---

## 5. Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MEETR_API_URL` | `https://meetr.aigent.biz/api` | Meetr API URL |
| `MEETR_API_KEY` | — | Partner API key (from Meetr admin) |
| `MEETR_CUSTOMER_ID` | — | Customer ID for scoping all API calls |
| `APP_PORT` | `80` | Port for the sample app (80 or 443) |
| `APP_SECRET_KEY` | `sample-app-dev-key` | Session signing key |
| `DATABASE_PATH` | `data/sample_app.db` | SQLite database path |

### Auto-Setup Mode (Developer Convenience)

```bash
cd sample_app
python run.py --auto-setup
```

This automatically provisions the Meetr-side resources:
1. Creates a "Sample App" partner in Meetr (requires Meetr server running)
2. Creates a customer under that partner
3. Configures the API key and customer ID as environment variables for the running process
4. Seeds a default user (`admin@example.com` / `admin`)
5. Starts the app at http://localhost

Without `--auto-setup`, the API key and customer ID must be set via environment variables (`MEETR_API_KEY`, `MEETR_CUSTOMER_ID`).

---

## 6. Out of Scope

- No multi-customer management (the app works within one customer)
- No admin API access (only partner-facing endpoints)
- No callr-level endpoints (internal service-to-service)
- No direct Meetr database access
- No automated test execution (this is a showcase/demo tool)

---

## 7. UI/UX

- **Tech stack**: Jinja2 templates, HTMX, Pico CSS (same as admin UI)
- **Navigation sidebar**: Dashboard, Team Members, Meetings, Settings
- **Responsive**: standard desktop browsers
- **Error display**: inline dismissible alerts
- **SSE integration**: live event stream on meeting detail page
- **Workflow guidance**: visual progress indicator on meeting detail (Create -> Outreach -> Collect -> Select -> Notify)
