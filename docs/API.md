# ZENDOC Mobile API

Base URL: `/api/v1`

## Auth

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `POST /auth/forgot-password`
- `POST /auth/reset-password`

Use the returned token as:

```http
Authorization: Bearer <token>
```

Registration normalizes email case, compatible Unicode forms, and outer whitespace. A duplicate returns HTTP 409 with `An account with this email already exists. Please log in.` Login uses the same safe response for a wrong password and an unknown account: `Email or password is incorrect.`

Access and password-reset tokens are purpose-separated. A reset token expires after 30 minutes and is never accepted as a bearer token. The reset-token response is a clearly labeled local-development beta; production returns HTTP 503 `integration_required` until a real delivery provider is configured.

## Endpoints

- `GET /health`
- `GET /dashboard`
- `GET /appointments`
- `POST /appointments`
- `GET /healthcare/search`
- `GET /providers`
- `GET /providers/<provider_profile_id>/slots`
- `POST /provider/profile`
- `POST /provider/schedules`
- `POST /ai/doctor`
- `POST /ai/assistant`
- `POST /ai/mental-health`
- `POST /ai/message`

### ZENDOC Milestone 6 Ecosystem

- `GET /family`
- `POST /family`
- `GET /family/<member_id>`
- `PUT /family/<member_id>`
- `DELETE /family/<member_id>`
- `GET /family/care-tasks`
- `POST /family/care-tasks`
- `PUT /family/care-tasks/<task_id>`
- `GET /family/access-grants`
- `POST /family/access-grants`
- `DELETE /family/access-grants/<grant_id>`
- `GET /home-health/requests`
- `POST /home-health/requests`
- `GET /ambulance/requests`
- `POST /ambulance/requests`

> **Verified (Selection Beta Hardening Audit):** The ambulance transport endpoint is `/api/v1/ambulance/requests` (not `/api/v1/transport/requests`). The response key for a created request is `ambulance_request` (not `request`). Doctor availability `status` accepts `"available"`, `"busy"`, `"offline"`, or `"consultation_only"` — not `"online"`. These were confirmed correct by end-to-end functional tests during the final hardening phase.
- `GET /pharmacy/medicines?q=<query>`
- `GET /pharmacy/stores?city=<city>`
- `POST /pharmacy/orders`
- `GET /pharmacy/reminders`
- `POST /pharmacy/reminders`
- `DELETE /pharmacy/reminders/<reminder_id>`
- `GET /iot/devices`
- `POST /iot/devices`
- `POST /iot/devices/<device_id>/sync`
- `GET /locations`
- `POST /locations`
- `DELETE /locations/<location_id>`
- `GET /search?q=<query>`
- `GET /marketplace`

### ZENDOC Milestone 7 Agent, Telehealth, Camera, Video, Operations

- `POST /agent/message`
- `GET /admin/agent-command-center`
- `PUT /doctor/availability`
- `GET /doctor/<doctor_id>/availability`
- `GET /consultations`
- `POST /consultations`
- `POST /consultations/<consultation_id>/status`
- `GET /consultations/<consultation_id>/messages`
- `POST /consultations/<consultation_id>/messages`
- `POST /fitness/pose-sessions`
- `GET /video-intelligence/search?q=<query>&category=<category>`
- `GET /videos/guidance?q=<query>&category=<category>`
- `POST /staff-profiles`
- `GET /staff-tasks`
- `POST /staff-tasks`
- `POST /staff-tasks/<task_id>/status`

### ZENDOC Connect & Permissioned Messaging (Milestone 7.1)

- `GET /contacts?q=<query>`
- `GET /conversations`
- `POST /conversations`
- `GET /conversations/<conversation_id>`
- `GET /conversations/<conversation_id>/messages`
- `POST /conversations/<conversation_id>/messages`
- `POST /conversations/<conversation_id>/read`
- `POST /conversations/<conversation_id>/share-video`
- `POST /conversations/<conversation_id>/share-report`
- `POST /communication-permissions`
- `GET /messages/unread-count`


### ZENDOC Health Memory

- `GET /health-profile`
- `PUT /health-profile`
- `GET /health-timeline`
- `GET /health-timeline/search?q=<query>`
- `GET /reports`
- `POST /reports` (multipart form upload)
- `GET /reports/<record_id>`
- `GET /reports/<record_id>/download`
- `GET /reports/<record_id>/results`
- `POST /reports/<record_id>/results`
- `GET /reports/<record_id>/explanation`
- `GET /report-trends?test_name=<test>`
- `GET /health-measurements`
- `POST /health-measurements`
- `GET /health-trends?metric_type=<metric>&period=30d`
- `GET /health-summary`
- `GET /health-access`
- `POST /health-access`
- `DELETE /health-access/<grant_id>`
- `GET /health-export`

These endpoints use structured JSON responses suitable for Flutter and FlutterFlow. Requests for another patient's data require an active provider grant with the matching scope. Admin access is controlled and audited.

## Pagination And Filters

Timeline parameters:

- `page` and `per_page` (maximum 100)
- `type`
- `q`
- `order=asc|desc`
- `start_date` and `end_date`

Report list parameters:

- `page` and `per_page` (maximum 100)

Health trend periods:

- `7d`
- `30d`
- `90d`
- `custom` with `start_date` and `end_date`

Measurements with different units are returned in separate series. The API does not infer unit conversions.

## Report Upload

`POST /reports` accepts multipart form data with `file`, `title`, `category`, `report_type`, and optional document metadata. Supported file extensions are PDF, PNG, JPEG, TXT, DOC, and DOCX. ZENDOC validates filename, MIME type, and basic file signatures.

Report extraction currently returns `unavailable` unless structured values are explicitly entered. No laboratory values are fabricated.

## Consent

Patients create a grant with a verified provider profile, one or more scopes, and an optional expiration:

```json
{
  "provider_profile_id": 12,
  "scopes": ["profile", "reports", "timeline"],
  "expires_at": "2026-12-31"
}
```

Supported scopes are `profile`, `reports`, `appointments`, `measurements`, and `timeline`. Revoked and expired grants are denied.

Family care uses a separate user-to-user grant for caregiver actions:

```json
{
  "grantee_email": "child@example.com",
  "family_member_id": 3,
  "scopes": ["home_health", "pharmacy", "transport"]
}
```

Supported family scopes are `appointments`, `reports`, `metrics`, `timeline`, `emergency`, `home_health`, `pharmacy`, `transport`, and `care_tasks`. Home healthcare, pharmacy, and transport requests for another patient account are denied unless the requester owns that account, is an admin, or has the matching active family grant.

## Healthcare Search

`GET /healthcare/search?category=doctor&specialty=Cardiology&location=Kolkata`

Returns registered verified ZENDOC providers and external places results when a provider is configured. Missing external credentials return a graceful unavailable message with no fabricated results.
# Milestone 8 APIs

All M8 endpoints require a bearer token. `/api/v1/admin/*` endpoints additionally require the environment-configured ZENDOC owner identity.

- `GET /api/v1/capabilities`
- `GET /api/v1/agent/registry`
- `GET /api/v1/agent/tools`
- `GET /api/v1/agent/tasks`
- `GET /api/v1/agent/tasks/{id}`
- `POST /api/v1/agent/tasks/{id}/execute`
- `POST /api/v1/agent/tasks/{id}/retry`
- `GET /api/v1/agent/approvals`
- `POST /api/v1/agent/approvals/{id}/decision`
- `GET /api/v1/events?after_id={id}&limit={n}`
- `POST /api/v1/admin/agent/tasks`
- `GET /api/v1/admin/model-router`
- `POST /api/v1/admin/model-router/test` (owner-only, fixed harmless local prompt; caller prompts are ignored)
- `GET /api/v1/admin/infrastructure`
- `GET /api/v1/admin/approvals`
- `POST /api/v1/admin/approvals/{id}/decision`
- `GET /api/v1/admin/alerts`
- `POST /api/v1/admin/alerts/check`
- `POST /api/v1/admin/alerts/{id}/acknowledge`
- `POST /api/v1/admin/alerts/{id}/resolve`

See [Milestone 8](MILESTONE8.md) for schemas, status, and safety boundaries.

## Milestone 8.2 Model Evaluation APIs

These endpoints require a bearer token belonging to the single environment-configured owner:

- `GET /api/v1/admin/model-evaluation`
- `POST /api/v1/admin/model-evaluation/runs` with fixed candidate ID and `dry_run` or `mock` mode
- `GET /api/v1/admin/model-evaluation/runs/{run_id}`

The API rejects `real_local` mode. A real-local evaluation is available only through the owner web UI's default-off, short-lived, two-step confirmation workflow. Requests cannot supply a provider endpoint, arbitrary model name, raw dataset path, prompt, or executable tool/action. Result payloads contain scores and metadata, not raw prompts, responses, credentials, patient information, or hidden reasoning. See [Milestone 8.2](MILESTONE8_2.md).
