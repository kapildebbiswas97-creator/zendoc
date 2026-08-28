# ZENDOC Milestone 6

## Summary

Milestone 6 upgrades ZENDOC toward a production UX and connected healthcare ecosystem without pretending unfinished integrations are live. The application remains additive to Milestones 1-5 and keeps existing routes, APIs, and database structures compatible.

## Implemented

- Health Command Center dashboard with quick actions for AI, doctors, appointments, reports, medicine, home health, family care, fitness, IoT devices, and services.
- One-time registration and login hardening with email normalization, duplicate-account handling, remember me sessions, logout, password visibility-ready templates, and password reset token architecture.
- Admin bootstrap from `ZENDOC_ADMIN_EMAIL` and `ZENDOC_ADMIN_PASSWORD`; configured admin accounts are created or promoted without duplicating users.
- Family Care and Remote Parent Care with family profiles, care tasks, user-to-user scoped family access grants, revocation, and audit logging.
- Home Healthcare request architecture with transparent service statuses.
- Ambulance and Medical Transport request architecture with emergency-first safety messaging and no fabricated ETA.
- Pharmacy service architecture for medicine search, prescription awareness, delivery requests, reminders, and verified pharmacy lookup without fake stock status.
- IoT Health Device Hub with connected devices, sync status, device identifiers, and measurement provenance recorded as `device`.
- Saved location APIs for home, current, recent, parent home, and other locations. Browser location remains user initiated.
- Universal search routing across family care, providers, emergency transport, pharmacy, fitness, records, and AI.
- Marketplace catalog for ZENDOC ecosystem categories with visible status boundaries.

## Database Changes

Additive SQLite tables:

- `family_members`
- `family_access_grants`
- `family_care_tasks`
- `saved_locations`
- `health_devices`
- `home_health_requests`
- `ambulance_requests`
- `medicine_orders`
- `medicine_reminders`

Existing tables are preserved. `health_metrics.source` continues to record provenance and now supports trusted device sync.

## New APIs

Milestone 6 adds API groups for:

- `/api/v1/family`
- `/api/v1/family/care-tasks`
- `/api/v1/family/access-grants`
- `/api/v1/home-health/requests`
- `/api/v1/ambulance/requests`
- `/api/v1/pharmacy/*`
- `/api/v1/iot/devices`
- `/api/v1/locations`
- `/api/v1/search`
- `/api/v1/marketplace`

Full endpoint details are listed in `docs/API.md`.

## Environment Variables

- `ZENDOC_ENV`
- `ZENDOC_SECRET_KEY`
- `ZENDOC_ADMIN_EMAIL`
- `ZENDOC_ADMIN_PASSWORD`
- `ZENDOC_MAX_UPLOAD_BYTES`
- `ZENDOC_RATE_LIMIT_PER_MINUTE`
- `ZENDOC_AI_PROVIDER`
- `ZENDOC_PLACES_PROVIDER`
- `ZENDOC_GOOGLE_PLACES_API_KEY`
- `ZENDOC_VIDEO_PROVIDER`
- `ZENDOC_YOUTUBE_API_KEY`

No admin password, API key, token, or provider secret is committed.

## Truthful Limits

- Home healthcare and ambulance requests are stored in ZENDOC but not dispatched to real providers.
- Pharmacy search is a reference catalog and verified-provider lookup; stock availability is not claimed.
- IoT sync is an internal trusted architecture path, not a live Apple, Google, Fitbit, or medical device integration.
- AI guidance is educational, routes users into services, and emergency safety runs before normal AI handling.
- ZENDOC has not completed clinical validation, legal compliance review, medical device certification, penetration testing, or production infrastructure hardening.

## Validation

Checks run in this workspace:

- `python -m compileall zendoc tests`
- `python -m pytest` (68 passed)

The dependency folders checked into this workspace had unreadable Windows ACLs, so pytest was installed into ignored folder `backups/pytest-deps` for verification.

## Checkpoint

A recoverable pre-edit checkpoint was written to `backups/milestone6-checkpoint-20260828-1148` before additional changes in this session.
