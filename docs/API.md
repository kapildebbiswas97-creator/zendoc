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

## Connected Care & Partner APIs (Milestone 10 / Pilot Readiness)

All JSON endpoints below use the existing `/api/v1` bearer-token boundary unless explicitly marked owner-only. Session-backed browser mutations additionally require the existing CSRF token boundary.

### Partner contract invariants

- A client-supplied patient ID is never sufficient authorization. Cross-patient access requires an active matching consent/care grant.
- `UNKNOWN` and `STALE` inventory/diagnostic states are never promoted to confirmed availability.
- Provider reconfirmation is explicit. A stale offer is refreshed only after the owning provider rechecks the values and sends `confirmed_unchanged=true`, or submits new values through the normal update endpoint.
- Provider resources are organization/branch scoped when tenancy metadata exists. Moving to another branch does not grant access to old-branch resources.
- Prescription ambiguity, medicine substitution, dose/frequency/form changes, prescribing, and autonomous order submission are blocked.
- Diagnostic booking requires an exact test, a verified fresh provider offer, explicit user confirmation, a future date, and a concrete collection address.
- Consequential actions remain human/provider gated. Partner integrations must not interpret a staged or requested object as externally accepted, dispatched, paid, dispensed, or completed.
- `LIVE` and `DEMO` data are isolated and must not be mixed implicitly.

### Connected Care

- `GET /api/v1/connected-care/context`
- `GET /api/v1/connected-care/pharmacy-offers`
- `POST /api/v1/connected-care/fulfilment`
- `POST /api/v1/connected-care/orders/confirm`
- `POST /api/v1/connected-care/prescriptions`
- `GET /api/v1/connected-care/prescriptions`
- `POST /api/v1/connected-care/prescriptions/<prescription_id>/status`
- `GET /api/v1/connected-care/next-safe-actions`
- `POST /api/v1/connected-care/consent`
- `DELETE /api/v1/connected-care/consent/<grant_id>`
- `POST /api/v1/connected-care/diagnostics/book`
- `GET /api/v1/connected-care/orders/<order_id>`
- `GET /api/v1/connected-care/care-graph`
- `GET /api/v1/connected-care/trust/<provider_id>`
- `GET /api/v1/connected-care/trust-center`
- `POST /api/v1/connected-care/trust-center/revoke`
- `POST /api/v1/connected-care/orchestrate`
- `POST /api/v1/connected-care/orchestrate/confirm`

### Provider inventory freshness

Authenticated pharmacy only:

- `POST /api/v1/connected-care/inventory` — submit new stock/price observation.
- `GET /api/v1/connected-care/provider/inventory-refresh` — list only the authenticated pharmacy's observations with effective freshness and `needs_refresh`.
- `POST /api/v1/connected-care/provider/inventory/<observation_id>/reconfirm` — renew freshness only after explicit provider recheck.

Reconfirmation body:

```json
{
  "confirmed_unchanged": true
}
```

A false/missing confirmation is rejected. Cross-pharmacy and cross-branch reconfirmation is rejected.

### Diagnostic offer freshness

Verified diagnostic provider only:

- `POST /api/v1/connected-care/diagnostic-offers` — create/update an offer and record a fresh observation.
- `GET /api/v1/connected-care/provider/diagnostic-refresh` — list the authenticated provider's diagnostic offers and freshness state.
- `POST /api/v1/connected-care/provider/diagnostic-offers/<offer_id>/reconfirm` — renew freshness only after explicit provider recheck.

Reconfirmation body:

```json
{
  "confirmed_unchanged": true
}
```

Stale or unknown offers remain non-bookable until a valid provider refresh occurs.

### Provider onboarding and evidence

Provider account:

- `GET /api/v1/provider/onboarding`
- `POST /api/v1/provider/evidence`

Owner only:

- `GET /api/v1/admin/provider-evidence`
- `POST /api/v1/admin/provider-evidence/<evidence_id>/review`

Evidence review and provider verification are separate states. Reviewing one evidence item must not be interpreted by a partner as automatic provider approval.

### CareFin and Care Journey

- `POST /api/v1/carefin/discover`
- `POST /api/v1/care-journeys`
- `GET /api/v1/care-journeys`
- `GET /api/v1/care-journeys/<journey_id>`
- `POST /api/v1/care-journeys/<journey_id>/transition`

CareFin discovery returns possible pathways and verification requirements. It does not confirm eligibility, approval, payment, insurer coverage, or government benefit entitlement without an authoritative partner workflow.

### Geography and official/public ingestion

Authenticated:

- `GET /api/v1/geography/search`
- `GET /api/v1/geography/<node_id>/entities`

Owner only:

- `POST /api/v1/admin/geography/nodes`
- `POST /api/v1/admin/geography/links`
- `GET /api/v1/admin/ingestion/sources`
- `GET /api/v1/admin/ingestion/batches`
- `POST /api/v1/admin/ingestion/adapt`
- `POST /api/v1/admin/ingestion/preview`
- `POST /api/v1/admin/ingestion/apply`
- `GET /api/v1/admin/ingestion/data-gaps`

Public/official directory records retain source, freshness, and verification state. Imported records do not automatically become ZENDOC-verified or bookable.

### Integration state vocabulary

Partners should preserve these distinctions:

- `WORKING` — implemented software path in ZENDOC.
- `BETA` — implemented but not yet production-validated for the external dependency/use case.
- `INTEGRATION_REQUIRED` — software boundary exists but an external provider, credential, partner, approval, or infrastructure dependency is missing.
- `CONFIRMED` — a fresh provider observation exists for that specific inventory/diagnostic fact.
- `STALE` — a prior observation exists but is too old to be represented as currently confirmed.
- `UNKNOWN` — ZENDOC has no reliable current observation.
- `UNAVAILABLE` — the provider explicitly reported zero/unavailable state.

### Idempotency and retries

Partner clients should retry only idempotent reads or endpoints whose documented request fingerprint/idempotency semantics apply. Do not blindly retry order confirmation, evidence submission, care-journey transitions, or other state-changing calls unless the endpoint explicitly supports safe replay.

The API intentionally prefers a truthful pending/requested state over inventing an external acknowledgement. Partner-side acceptance, fulfilment, dispatch, payment, clinical completion, or regulatory confirmation must be recorded only from the responsible authority/provider.

See also [Partner API Specification](PARTNER_API_SPEC.md) for integration requirements and pilot onboarding guidance.

