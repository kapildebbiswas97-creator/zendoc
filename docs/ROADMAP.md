# ZENDOC Production Roadmap

## Phase 1: MVP Hardening

- Move the database from SQLite to Postgres with migrations.
- Add automated tests for auth, appointments, uploads, AI outputs, API auth, and role authorization.
- Add rate limiting, password reset, email verification, MFA for admin, and API token expiry/revocation.
- Add OpenAPI documentation for mobile and partner integrations.
- Add structured logs, error tracking, uptime checks, and deployment health probes.

## Phase 2: Healthcare Data Protection

- Add consent records, privacy settings, and patient data export/delete workflows.
- Add a full audit dashboard for record access, downloads, login events, and AI interactions.
- Move uploads to encrypted object storage with malware scanning and signed downloads.
- Add data retention policies by record type and user role.
- Complete HIPAA/GDPR-aligned review based on launch geography.

## Phase 3: Clinical AI Governance

- Create a pluggable AI provider interface for future LLM and medical model integrations.
- Store AI prompt versions, response versions, confidence, risk class, and clinician-review status.
- Add safety review queues for high-risk AI events.
- Add medical disclaimer, emergency escalation localization, and clinician-approved response templates.
- Evaluate AI outputs with expert-reviewed test cases before each release.

## Phase 4: Product Depth

- Add patient profiles, allergies, medications, conditions, family history, and care goals.
- Add provider directory, appointment availability, reminders, and follow-up workflows.
- Add report explanation from uploaded files with clinician-friendly summaries.
- Add medication reminder schedules and adherence tracking.
- Add nutrition plans, daily coaching, habit streaks, and personalized wellness programs.

## Phase 5: Mobile And API Scale

- Add pagination, filtering, and stable resource schemas for all `/api/v1` endpoints.
- Add mobile upload endpoints, push-notification hooks, and device/session management.
- Add OAuth-compatible auth or short-lived JWT access tokens with refresh tokens.
- Add API monitoring, request IDs, and versioned client compatibility testing.

## Phase 6: Investor-Ready Operations

- Expand analytics into funnels: registration, activation, AI usage, record upload, appointment request, completion, and retention.
- Add cohort metrics, daily/weekly active users, engagement frequency, and care-outcome proxies.
- Add admin segmentation by role, geography, risk level, feature usage, and care pathway.
- Add exportable investor metrics and board-report snapshots.

## Phase 7: Cloud Production

- Deploy with a production WSGI server, managed database, object storage, backups, and secrets manager.
- Add CI/CD with staging and production environments.
- Add horizontal scaling behind a load balancer.
- Add background workers for notifications, file processing, AI review, and analytics aggregation.
- Add disaster recovery, backup restore drills, and incident response runbooks.
