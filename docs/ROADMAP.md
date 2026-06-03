# ZENDOC Production Roadmap

## Phase 1: MVP Foundation

- Add persistent database storage.
- Replace plain-text passwords with strong password hashes.
- Add secure sessions, route guards, role guards, and CSRF protection.
- Add functional dashboards for core roles.
- Add appointment, medical record, notification, and health metric tables.
- Add basic mobile-ready JSON APIs.
- Add upload validation and controlled download routes.

## Phase 2: Core Healthcare Workflows

- Patient profile and medical history.
- Doctor appointment queue and status updates.
- Hospital/provider directory.
- Medical record categorization and timeline.
- Notification preferences and delivery channels.
- Admin dashboard for user, appointment, record, and AI usage statistics.

## Phase 3: AI Doctor And Assistant Architecture

- Create a prediction service interface with pluggable providers.
- Start with deterministic triage and symptom mapping.
- Add dataset ingestion and model training pipeline.
- Store model metadata, version, confidence, and evaluation metrics.
- Add clinical safety rules, disclaimers, and emergency escalation.
- Add human review workflows for high-risk outputs.

## Phase 4: Mental Health AI

- Age-aware support flows for students, working professionals, and elderly users.
- Stress scoring architecture.
- Mood and risk tracking.
- Escalation paths for crisis keywords.
- Clinical review and localization support.

## Phase 5: Flutter/FlutterFlow Integration

- Stabilize `/api/v1` endpoints.
- Add token-based mobile auth.
- Add OpenAPI documentation.
- Add pagination, filtering, and structured error responses.
- Add media upload endpoints compatible with mobile clients.

## Phase 6: Production Engineering

- Move secrets to environment variables.
- Add migrations, test suite, CI/CD, logging, monitoring, backups, and rate limits.
- Add deployment profiles for staging and production.
- Add object storage for medical files.
- Add queue workers for notifications, report processing, and AI jobs.

## Phase 7: Healthcare Compliance And Scale

- Add consent management, audit trails, access logs, and retention controls.
- Perform security review and threat modeling.
- Prepare HIPAA/GDPR-aligned operational processes based on launch geography.
- Add data residency strategy.
- Add clinical governance for AI model release and monitoring.

