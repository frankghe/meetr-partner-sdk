# Meetr Integration Guide

Guide for partners integrating Meetr's automated meeting scheduling into their applications.

---

## 1. Overview

Meetr automates meeting scheduling by contacting participants, collecting their availability through natural conversations (SMS, WhatsApp, voice), and selecting optimal meeting times. As a partner, you interact with Meetr through a REST API to create meeting requests and receive results via callbacks, webhooks, or polling.

### What Meetr does for you

1. Contacts each participant via their preferred channel(s)
2. Conducts a natural-language conversation to collect availability
3. Retries unreachable participants with configurable backoff
4. Selects the optimal meeting slot based on participant priorities and coverage
5. Notifies participants of the selected time and collects confirmations

---

## 2. Getting Started

### Self-registration

Register as a partner to receive an API key:

```bash
curl -X POST https://meetr.aigent.biz/api/partners/register \
  -H "Content-Type: application/json" \
  -d '{"name": "My Company", "contact_email": "dev@mycompany.com"}'
```

**Response:**

```json
{
  "partner_id": "uuid",
  "name": "My Company",
  "api_key": "mk_abc123..."
}
```

Store the `api_key` securely — it is shown only once.

### Authentication

All API requests (except registration) require an API key in the `X-API-Key` header:

```bash
curl -H "X-API-Key: mk_abc123..." \
     https://meetr.aigent.biz/api/meetings
```

API keys are scoped to your partner account. You can only access meetings and data belonging to your partner.

The `X-API-Key` header authentication requirement is also formally documented in the OpenAPI spec (`docs/openapi.yaml`) under `components.securitySchemes.ApiKeyAuth`. All endpoints except `/health`, `/health/detailed`, and `/api/partners/register` carry a global security requirement in the spec.

### Rate Limits

All authenticated endpoints are rate-limited per partner (or per customer when `X-Customer-Id` is provided).

| Scope | Default Limit | Description |
|-------|--------------|-------------|
| General | 100 requests/min | Applies to all authenticated endpoints |
| Meeting creation | 20 requests/min | `POST /api/meetings` only |
| Key rotation | 5 requests/hour | `POST /api/keys/rotate` only |

When a limit is exceeded, the API returns `429 Too Many Requests` with a `Retry-After` header indicating how many seconds to wait.

Customer-specific rate limits can be configured via the `/api/customers` endpoints and override partner defaults when set.

### Customer Scoping (Multi-Tenant)

If you manage multiple customers, include the `X-Customer-Id` header to scope operations:

```bash
curl -H "X-API-Key: mk_abc123..." \
     -H "X-Customer-Id: cust-001" \
     https://meetr.aigent.biz/api/meetings
```

**Behavior:**
- If the customer does not exist, it is auto-created under your partner account
- Meetings, participants, and rate limits are scoped to the customer
- Customer-specific rate limits override partner defaults when set
- Omitting the header scopes operations to your partner account directly

Manage customers explicitly via the `/api/customers` endpoints to set names and rate limits.

### API Explorer

Meetr provides an interactive API explorer powered by Swagger UI:

- **Swagger UI**: `https://meetr.aigent.biz/docs`
- **OpenAPI JSON**: `https://meetr.aigent.biz/openapi.json`

Use the Swagger UI to browse all public endpoints, view request/response schemas, and try requests interactively. Internal and admin endpoints are not shown.

---

## 3. Core Workflow

### Step 1: Create a meeting

```bash
curl -X POST https://meetr.aigent.biz/api/meetings \
  -H "X-API-Key: mk_abc123..." \
  -H "Content-Type: application/json" \
  -d '{
    "purpose": "Q1 Planning",
    "context": "Quarterly planning and goal setting for the engineering team",
    "scheduling_window_start": "2026-03-20T00:00:00Z",
    "scheduling_window_end": "2026-03-27T23:59:59Z",
    "timezone": "America/New_York",
    "meeting_duration_minutes": 60,
    "daily_start_time": "09:00",
    "daily_end_time": "17:00",
    "participants": [
      {
        "first_name": "Alice",
        "last_name": "Martin",
        "phone_number": "+1234567890",
        "priority": 5,
        "communication_modes": ["whatsapp", "sms"]
      },
      {
        "first_name": "Bob",
        "last_name": "Chen",
        "phone_number": "+0987654321",
        "priority": 3,
        "communication_modes": ["sms"]
      }
    ],
    "min_participants_required": 2,
    "client_callback_url": "https://your-app.com/meetr/callback"
  }'
```

**Response** (wrapped in the standard envelope):

```json
{
  "data": {
    "session_id": "uuid",
    "meeting_request_id": "uuid",
    "participants_count": 2,
    "outreaches_initiated": 2,
    "status": "created",
    "external_id": null
  }
}
```

### Step 2: Monitor progress

Poll the meeting status or use SSE for real-time updates:

```bash
# Poll
curl -H "X-API-Key: mk_abc123..." \
     https://meetr.aigent.biz/api/meetings/{session_id}

# SSE (real-time)
curl -N -H "X-API-Key: mk_abc123..." \
     https://meetr.aigent.biz/api/meetings/{session_id}/events
```

### Step 3: Receive results

When scheduling completes, the meeting detail includes a `selected_slot`. If you provided a `client_callback_url`, you also receive a POST notification. You can also subscribe to webhooks for event-driven updates.

### Callback Payload

When a meeting reaches a terminal state and a `client_callback_url` was provided, Meetr sends a POST request:

```json
{
  "session_id": "uuid",
  "status": "completed",
  "selected_slot": {
    "start": "2026-03-21T09:00:00Z",
    "end": "2026-03-21T10:00:00Z",
    "timezone": "UTC"
  },
  "participants": [
    { "name": "Alice Martin", "confirmation_status": "confirmed" },
    { "name": "Bob Chen", "confirmation_status": "pending" }
  ]
}
```

The `status` field is `"completed"`, `"failed"`, or `"cancelled"`. For cancelled meetings, a `cancellation_reason` field is included when one was provided. The `selected_slot` is `null` when no slot was selected (e.g. on failure).

---

## 4. Meeting Lifecycle

### States

| State | Description |
|-------|-------------|
| `PENDING` | Initial state, meeting request created |
| `COLLECTING` | Outreach in progress, collecting availability |
| `AWAITING_RESPONSES` | Waiting for participant responses |
| `SELECTING_SLOT` | Sufficient availability collected, selecting optimal slot |
| `NEEDS_INTERVENTION` | Scheduling stuck, manager intervention needed |
| `CONFIRMING` | Sending confirmations to participants |
| `AWAITING_CONFIRMATIONS` | Waiting for participant confirmations |
| `COMPLETED` | Meeting fully confirmed |
| `FAILED` | Scheduling could not be completed |
| `CANCELLED` | Meeting was cancelled by the partner |

### Outreach Statuses

Each participant has an outreach status visible in the meeting detail response:

| Status | Description |
|--------|-------------|
| `NOT_CONTACTED` | Outreach not yet started |
| `CONTACTING` | Outreach in progress |
| `AWAITING_RETRY` | Previous attempt failed, waiting for retry |
| `AVAILABILITY_RECEIVED` | Participant provided availability |
| `NOTIFIED` | Participant notified of selected slot |
| `CONFIRMED` | Participant confirmed attendance |
| `DECLINED` | Participant declined |
| `OPTED_OUT` | Participant opted out of scheduling |
| `NO_RESPONSE` | No response received before deadline |
| `FAILED` | Outreach failed after all retry attempts |

### Cancel a meeting

**POST** `/api/meetings/{session_id}/cancel`

```json
{
  "reason": "Meeting no longer needed"
}
```

The `reason` field is optional. Active outreaches are stopped and participants are notified.

**Response:**

```json
{
  "data": {
    "success": true,
    "message": "Meeting cancelled (was AWAITING_RESPONSES)",
    "session_id": "uuid",
    "state": "CANCELLED"
  }
}
```

### Intervene on a meeting

**POST** `/api/meetings/{session_id}/intervene`

Send a natural-language instruction to adjust a stuck meeting:

```json
{
  "message": "Extend the scheduling window by 3 days"
}
```

**Response:**

```json
{
  "data": {
    "success": true,
    "session_id": "uuid",
    "actions_applied": ["extended_scheduling_window"],
    "validation_errors": [],
    "new_state": "AWAITING_RESPONSES",
    "error_message": null
  }
}
```

### Check slot selection status

**POST** `/api/meetings/{session_id}/select-slot`

Returns the current slot selection status. Slot selection is performed automatically by the scheduling worker when sufficient availability is collected.

### Notify participants

**POST** `/api/meetings/{session_id}/notify`

Send confirmation notifications to all participants with availability. Returns per-participant notification results.

---

## 5. Outreach Management

### Get outreach detail

**GET** `/api/meetings/{session_id}/outreach/{participant_id}`

Returns detailed outreach status including availability slots, attempt count, and active channel.

> **Complete schemas**: For full request/response schemas and field details, see the [API Explorer](/docs).

### Start outreach manually

**POST** `/api/meetings/{session_id}/outreach/{participant_id}/start`

Manually trigger outreach for a specific participant. Accepts an optional JSON body:

| Field | Type | Description |
|-------|------|-------------|
| `callback_url` | string | Override callback URL |
| `force` | boolean | Force restart even if already contacted |

### Submit availability

**POST** `/api/meetings/{session_id}/participants/{participant_id}/availability`

Submit or replace availability slots for a participant. This is typically used when your app's calendar sync provides availability externally.

```json
{
  "slots": [
    {
      "start": "2026-03-21T09:00:00Z",
      "end": "2026-03-21T10:00:00Z",
      "timezone": "UTC",
      "confidence": 0.9
    },
    {
      "start": "2026-03-22T14:00:00Z",
      "end": "2026-03-22T15:00:00Z",
      "timezone": "UTC"
    }
  ],
  "source": "calendar"
}
```

**Response:**

```json
{
  "data": {
    "participant_id": "uuid",
    "status": "AVAILABILITY_RECEIVED",
    "slots_count": 2,
    "ready_for_slot_selection": false
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `slots` | array | yes | Non-empty list of availability slots |
| `source` | string | no | Source: `calendar`, `manual`, or `web_form` (default: `calendar`) |

**Behavior:**
- Idempotent: re-submitting replaces previous availability (last write wins)
- The participant's outreach status is set to `AVAILABILITY_RECEIVED`
- Slot selection is triggered automatically when sufficient availability is collected
- Returns `409 Conflict` if the meeting is in a terminal state or outreach cannot accept availability
- Returns `404 Not Found` if the session or participant does not exist

---

## 6. Resource Management

### Customers

Customers represent sub-accounts under your partner. They allow you to segment meetings and participants by customer.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/customers` | GET | List all customers |
| `/api/customers` | POST | Create a customer |
| `/api/customers/{customer_id}` | GET | Get customer detail |
| `/api/customers/{customer_id}` | PATCH | Update a customer |

### Participants

Manage a directory of participants that can be reused across meetings.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/participants` | GET | List all participants |
| `/api/participants` | POST | Create a participant |
| `/api/participants/{participant_id}` | GET | Get participant detail |
| `/api/participants/{participant_id}` | PATCH | Update a participant |

> **Complete schemas**: For full request/response schemas and field details, see the [API Explorer](/docs).

---

## 7. Webhooks

Register webhook endpoints to receive event notifications.

### Subscribe

**POST** `/api/webhooks`

```json
{
  "url": "https://your-app.com/meetr/events",
  "event_types": ["meeting.completed", "meeting.failed", "meeting.cancelled"],
  "secret": "your-hmac-secret"
}
```

**Response:**

```json
{
  "data": {
    "id": "subscription-uuid",
    "url": "https://your-app.com/meetr/events",
    "event_types": ["meeting.completed", "meeting.failed", "meeting.cancelled"],
    "is_active": true,
    "created_at": "2026-03-20T10:00:00Z"
  }
}
```

> **Complete schemas**: For full request/response schemas and field details, see the [API Explorer](/docs).

**Available event types:** `meeting.state_changed`, `meeting.completed`, `meeting.failed`, `meeting.cancelled`, `outreach.updated`, `slot.selected`, `confirmation.received`

### List subscriptions

**GET** `/api/webhooks`

### Delete a subscription

**DELETE** `/api/webhooks/{subscription_id}`

### Webhook payload format

When an event fires, Meetr sends a POST request to your registered URL:

```json
{
  "event": "meeting.completed",
  "session_id": "uuid",
  "partner_id": "your-partner-id",
  "state": "COMPLETED",
  "selected_slot": {
    "start": "2026-03-21T09:00:00Z",
    "end": "2026-03-21T10:00:00Z",
    "timezone": "UTC"
  },
  "reference_code": "M-7K3X"
}
```

If a `secret` was provided, the payload is signed with HMAC-SHA256. The signature is in the `X-Meetr-Signature` header as `sha256=<hex-digest>`. Verify by computing `HMAC-SHA256(secret, raw_body)` and comparing.

---

## 8. API Key Rotation

**POST** `/api/keys/rotate`

Create a new API key while keeping old key(s) active for a grace period:

```json
{
  "grace_period_hours": 24
}
```

> **Complete schemas**: For full request/response schemas and field details, see the [API Explorer](/docs).

The new key is shown only once. Store it securely. Old key(s) remain valid for the specified grace period.

---

## 9. Server-Sent Events (SSE)

**GET** `/api/meetings/{session_id}/events`

Connect to a live event stream for real-time meeting updates. Events include state changes, outreach updates, and slot selection.

The native browser `EventSource` API does not support custom headers. Use a library or `fetch` with a streaming reader:

```javascript
const response = await fetch(
  'https://meetr.aigent.biz/api/meetings/{session_id}/events',
  { headers: { 'X-API-Key': 'your-key' } }
);

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  const text = decoder.decode(value);
  // Parse SSE lines: "event: <type>\ndata: <json>\n\n"
  console.log(text);
}
```

Supports `Last-Event-ID` header for resuming after disconnection.

---

## 10. Partner Chat Channel

Use the partner chat channel to route participant conversations through your own messaging system instead of SMS/WhatsApp.

### Register your chat webhook

**PUT** `/api/partner/chat-webhook`

```json
{
  "url": "https://your-app.com/meetr/chat",
  "secret": "your-hmac-secret"
}
```

The `url` must use HTTPS. The `secret` is used bidirectionally for HMAC-SHA256 signing — Meetr signs outbound messages to you, and you sign inbound messages to Meetr.

### Create a meeting with partner chat participants

Include `"partner_chat"` in `communication_modes` and provide an `external_participant_id` instead of a phone number:

```json
{
  "purpose": "Q1 Planning",
  "context": "Quarterly planning session",
  "scheduling_window_start": "2026-03-20T00:00:00Z",
  "scheduling_window_end": "2026-03-27T23:59:59Z",
  "timezone": "America/New_York",
  "meeting_duration_minutes": 60,
  "participants": [
    {
      "first_name": "Alice",
      "last_name": "Martin",
      "communication_modes": ["partner_chat"],
      "external_participant_id": "your-user-id-123"
    }
  ]
}
```

When using `partner_chat` only, `phone_number` is not required. For mixed modes (e.g. `["partner_chat", "whatsapp"]`), `phone_number` is still required.

### Outbound messages (Meetr → your chat)

Meetr POSTs outbound messages to your registered webhook URL:

```json
{
  "external_participant_id": "your-user-id-123",
  "message": {
    "text": "Hi Alice! I'm helping schedule a Q1 Planning meeting...",
    "buttons": [
      {"id": "1", "label": "Monday 2pm"},
      {"id": "2", "label": "Tuesday 10am"}
    ]
  },
  "timestamp": "2026-03-20T10:00:00Z"
}
```

The payload is signed with HMAC-SHA256. Verify the `X-Meetr-Signature` header:

```python
import hmac, hashlib
expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
assert hmac.compare_digest(expected, request.headers["X-Meetr-Signature"])
```

### Inbound messages (your chat → Meetr)

Forward participant replies to Meetr's callr service:

**POST** `{callr_url}/webhooks/partner-chat/inbound`

```json
{
  "partner_id": "your-partner-id",
  "external_participant_id": "your-user-id-123",
  "message": "I'm available Monday at 2pm"
}
```

Sign the request with HMAC-SHA256 using the same shared secret. Include the signature in the `X-Partner-Signature` header.

### Removing the webhook

**DELETE** `/api/partner/chat-webhook`

Removes the partner chat configuration. Participants with `partner_chat` mode will not be contactable until a new webhook is registered.

---

## 11. Response Format & Error Handling

### Success envelope

All successful responses are wrapped in a standard envelope:

```json
{
  "data": { ... },
  "meta": {
    "total": 42,
    "limit": 20,
    "offset": 0
  }
}
```

The `meta` field is present only on paginated list endpoints.

### Error envelope

Errors return a structured envelope:

```json
{
  "error": {
    "code": "not_found",
    "message": "Session not found"
  }
}
```

| Status | Error Code | Description |
|--------|------------|-------------|
| 400 | `bad_request` | Invalid request payload |
| 400 | `validation_error` | Field-level validation failure |
| 401 | `unauthorized` | Missing or invalid API key |
| 403 | `forbidden` | Not authorized to access this resource |
| 404 | `not_found` | Resource not found |
| 409 | `conflict` | State conflict (e.g. submitting availability to a terminal meeting) |
| 429 | `rate_limited` | Rate limit exceeded (check `Retry-After` header) |
| 500 | `internal_error` | Internal server error |

---

## 12. Observability

### Health checks

| Endpoint | Purpose | Auth |
|----------|---------|------|
| `GET /health` | Fast liveness probe (no DB call) | No |
| `GET /health/detailed` | Deep readiness check (DB, workers, active sessions) | No |

**`/health/detailed` response:**

```json
{
  "status": "healthy",
  "checks": {
    "database": {"status": "ok", "latency_ms": 1.2},
    "workers": {
      "scheduling_worker": {"running": true},
      "completion_worker": {"running": true},
      "housekeeper_worker": {"running": true}
    },
    "active_sessions": 5
  }
}
```

Status values: `healthy` (all systems nominal), `degraded` (DB ok but some workers stopped), `unhealthy` (DB unreachable).

### Metrics

`GET /metrics` returns Prometheus-format metrics including HTTP request counters/histograms and business metrics (sessions created, completed, outreach outcomes).

### Correlation IDs

All API responses include an `X-Correlation-ID` header. Pass this header in your requests to trace operations across services in logs.

---

## 13. Meeting Reference Codes

Every meeting is assigned a short, user-friendly **reference code** at creation time (e.g., `M-7K3X`). This code:

- Is included in all participant-facing messages (outreach, confirmations, cancellations)
- Appears in meeting list and detail responses as the `reference_code` field
- Can be used by participants to identify meetings when they have multiple active meetings

**Format:** `M-` prefix followed by 4 uppercase alphanumeric characters (excluding ambiguous characters O, 0, I, 1, l).

---

## 14. Participant Question Sessions

Participants can send unsolicited messages (SMS/WhatsApp) to ask about their meeting status. Meetr handles this automatically:

1. **Participant sends a message** when no active conversation exists
2. **Meetr looks up their meetings** and responds with status information
3. **If multiple meetings**, Meetr asks which meeting they're asking about (using reference codes)
4. **Follow-up questions** are supported within the same session (configurable turn limit)
5. **Sessions auto-expire** after a configurable inactivity timeout

### Configuration

Question session behavior is configured per customer:

| Field | Default | Description |
|-------|---------|-------------|
| `max_question_turns` | 3 | Maximum conversation turns per question session |
| `question_session_ttl_seconds` | 120 | Inactivity timeout before session auto-closes |

### Authorization

Participants can only ask about meetings they are part of (as a participant or as the requestor).

---

## 15. OpenAPI Specification

The public partner-facing API specification is available in multiple formats. Internal and admin endpoints are excluded from the documentation.

| Format | Location |
|--------|----------|
| Interactive explorer | `/docs` (Swagger UI) |
| JSON spec | `/openapi.json` |
| Versioned YAML | `docs/openapi.yaml` (in repository) |

The YAML spec is regenerated with:

```bash
python scripts/export_openapi.py
```

---

## 16. Create Meeting Request — Field Reference

### Top-level fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `purpose` | string | yes | Meeting purpose shared with participants during outreach |
| `context` | string | yes | Additional context for the conversational agent |
| `scheduling_window_start` | string | yes | Earliest date/time (ISO 8601) |
| `scheduling_window_end` | string | yes | Latest date/time (ISO 8601) |
| `timezone` | string | yes | Default IANA timezone |
| `meeting_duration_minutes` | integer | yes | Meeting length in minutes |
| `daily_start_time` | string | no | Earliest daily time (HH:MM), e.g. `"09:00"` |
| `daily_end_time` | string | no | Latest daily time (HH:MM), e.g. `"17:00"` |
| `max_scheduling_deadline` | string | no | Hard deadline (ISO 8601) |
| `participants` | array | yes | At least one participant (see below) |
| `min_participants_required` | integer | no | Minimum participants needed (default: all mandatory) |
| `client_callback_url` | string | no | HTTPS endpoint for completion callbacks |
| `external_id` | string | no | Your external identifier for correlation |
| `manager` | object | no | Full participant info for the meeting manager/requestor. Enables question sessions, escalation handling, and intervention notifications. Same fields as participant entries (`first_name`, `last_name`, `phone_number`, etc.). Resolved against the address book by phone number. |
| `requester` | string | no | Name of the person requesting the meeting (simple alternative to `manager` when full participant info is not needed) |
| `intervention_notification` | string | no | `"callback"`, `"outreach"`, or `"both"` |

### Participant fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `first_name` | string | yes | Participant's first name |
| `last_name` | string | yes | Participant's last name |
| `phone_number` | string | conditional | E.164 format phone number. Required unless using `partner_chat` only |
| `priority` | integer | no | 1=optional, 2=low, 3=medium (default), 4=high, 5=mandatory |
| `timezone` | string | no | Participant's IANA timezone (overrides meeting timezone) |
| `language` | string | no | Conversation language: `en`, `fr`, `he` (default: `en`) |
| `communication_modes` | array | no | Ordered list of channels: `"sms"`, `"whatsapp"`, `"voice"`, `"partner_chat"` |
| `external_participant_id` | string | no | Partner's identifier for this participant (required with `partner_chat`) |
| `skip_outreach` | boolean | no | Skip conversational outreach (default: `false`). Requires `availability_slots` |
| `availability_slots` | array | conditional | Pre-known slots (required when `skip_outreach` is `true`) |

**Calendar-linked participants:** When your app already knows a participant's availability (e.g., from calendar sync), set `skip_outreach: true` and provide their `availability_slots`. Meetr will use the provided slots directly for scheduling.

---

## 17. Test App

Meetr includes a browser-based test harness at `/app/` on the server. Use it to:

- Create meetings through a UI instead of raw API calls
- Monitor outreach progress in real time
- View participant availability and slot selection
- Test your integration flow end-to-end

---

## 18. Best Practices

- **Use webhooks** for production integrations — polling is unnecessary for terminal events
- **If polling**, use 30-60 second intervals — the scheduling lifecycle is measured in hours, not seconds
- **Store the `session_id`** returned from the create call — it is your reference for all subsequent operations
- **Use HTTPS** for your callback and webhook URLs
- **Handle retries** — your endpoints may receive the same event more than once; use `session_id` + `event` for deduplication
- **Set reasonable scheduling windows** — wider windows give participants more flexibility
- **Use priority correctly** — 5 (mandatory) for must-attend, 1 (optional) for nice-to-have
- **Rotate API keys** regularly using the `/api/keys/rotate` endpoint
- **Monitor health** — use `/health/detailed` for readiness probes in orchestration systems
- **Use correlation IDs** — pass `X-Correlation-ID` in requests to trace operations across services
