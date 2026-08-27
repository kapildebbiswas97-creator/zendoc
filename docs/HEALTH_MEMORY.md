# ZENDOC Health Memory

## Purpose

Milestone 4 connects existing appointments, medical records, reports, health measurements, and relevant AI activity into one private longitudinal health identity. Existing data remains in its original tables; the timeline derives authorized views rather than copying or deleting historical records.

## Service Boundaries

- `health_profile.py`: optional patient health profile validation and persistence.
- `health_timeline.py`: bounded, paginated timeline queries across authorized sources.
- `report_intelligence.py`: secure report storage, metadata, structured values, explanations, and lab trends.
- `health_analytics.py`: source-aware measurements, validation, BMI calculation, and trends.
- `health_access.py`: provider scope, expiration, revocation, and authorization decisions.
- `health_summary.py`: minimum-scope patient and provider summaries plus patient export.
- `health_routes.py`: Milestone 4 web and API presentation layer.

## Data Model

Additive tables:

- `patient_health_profiles`
- `report_metadata`
- `report_results`
- `health_timeline_events`
- `health_access_grants`

Additive `health_metrics` fields:

- `numeric_value`
- `secondary_value`
- `source`
- `notes`

Existing `medical_records`, `appointments`, `health_metrics`, and `ai_interactions` remain the source of truth for their existing behavior.

## Timeline Sources

The timeline uses an indexed SQL union over the authenticated patient's appointments, medical records/report metadata, measurements, selected health-related AI interactions, and future explicit health events. Queries support type filtering, text/date search, sorting, date bounds, and pagination with a maximum page size of 100.

## Privacy Model

Patients always access only their own health data. Verified doctor/hospital accounts require an active patient grant for each requested scope. Expired and revoked grants fail authorization. Admin access is explicit and audited. Knowing a patient ID is never sufficient for provider access.

This is a technical privacy foundation. It is not a claim of HIPAA, GDPR, DPDP, or other regulatory compliance.

## Report Intelligence Limits

Uploaded files are preserved and validated by extension, MIME type, basic signature, secure generated filename, upload limit, and authorized download. Automatic extraction is currently unavailable; ZENDOC reports that status truthfully. Structured values are stored only when explicitly entered by an authorized user and are labeled by source.

Report explanations summarize stored values and supplied abnormal flags. They do not diagnose disease. Trend queries keep incompatible units in separate series and do not silently convert them.

## AI Context Rules

Health-memory intents use authorized service methods. Deterministic requests such as showing a timeline or latest report do not send data to an LLM. Report explanation uses only the selected authorized report and its structured values. Emergency safety runs before all health-memory routing.

## Production Work Remaining

- PostgreSQL and a migration framework.
- Encrypted object storage with malware scanning.
- Background document processing/OCR with confidence and provenance.
- Distributed rate limiting, monitoring, backups, key management, and incident response.
- Formal privacy/legal review, clinical governance, accessibility testing, and penetration testing.
