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
