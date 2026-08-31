# ZENDOC Launch Status Report

## Current Phase

Milestones 1 through 8.3 are implemented as an advanced MVP foundation. ZENDOC is not a certified medical product, emergency dispatch system, pharmacy inventory network, production telemedicine system, or regulated medical device platform. M8 adds an owner-bound Admin invariant and bounded agent operations; M8.1 adds a real optional local inference path, strict structured output, privacy-aware routing, truthful runtime health, and owner-only AI observability; M8.2 adds a synthetic, safety-first base-model evaluation framework without downloading, training, or automatically running a model; M8.3 stabilizes persistent identity, sessions, recovery tokens, database selection, and demo release checks.

## Implemented

- Flask application package with app factory.
- SQLite schema for users, appointments, records, health metrics, notifications, AI logs, API tokens, and audit logs.
- Password hashing and session-based web login.
- CSRF checks for web forms.
- Token-based API login for mobile apps and FlutterFlow.
- AI Doctor rules engine with emergency-risk handling and ML-ready service boundary.
- Smart Assistant and Mental Health AI support architecture.
- Admin dashboard with live statistics, user verification, and audit log.
- Upload/download flow with file type validation.
- Separate account and patient health profiles with optional health fields.
- Paginated, searchable, filterable health timeline derived from existing records.
- Structured report metadata and manually verified laboratory result storage.
- Truthful report explanation fallback when extraction is unavailable.
- Source-aware measurements and unit-safe 7/30/90-day trends.
- Patient-controlled provider grants with scope, expiration, and revocation.
- Patient JSON export without storage paths.
- Authorized provider summary view and cross-user/IDOR tests.
- Central AI actions for timeline, report history, report explanation, trends, and medications.
- Smoke tests for critical web and API flows.
- Production configuration now requires real secrets instead of relying on source-code credentials.
- Health Command Center dashboard and upgraded whole-app navigation.
- Environment-driven admin bootstrap with no source-code admin password requirement in production.
- Family Care with explicit user-to-user scoped consent grants, caregiver audit events, remote parent profiles, and care tasks.
- Home healthcare, ambulance/transport, pharmacy, marketplace, universal search, saved locations, and IoT hub API foundations.
- IoT measurement provenance recorded as `device` only through the trusted device sync path.
- Milestone 6 regression tests for admin, auth, family isolation, consent, remote parent care authorization, service requests, pharmacy truthfulness, IoT provenance, saved locations, AI routing, and endpoint auth.
- Normalized email uniqueness with duplicate legacy account documentation.
- ZENDOC Core Agent with permissioned deterministic tools, platform events, agent audit logs, and communication tools.
- Admin Agent Command Center for operations visibility without leaking private patient-doctor clinical messages.
- Doctor availability with customizable patient message policies, consultation request workflow, secure consultation messaging, and local demo media controls.
- ZENDOC Connect permissioned care messaging (`/messages`) with responsive desktop 3-pane and mobile layouts.
- Privacy-preserving contact discovery (`/api/v1/contacts`) searching by name, role, doctor specialty, and organization while redacting emails and phone numbers.
- Message delivery receipts (`delivered`, `read`), unread counts, and notification triggers.
- Consent-driven medical report sharing and educational video attachments in chat.
- Universal Search extended across providers, family, permitted contacts, conversations, and educational videos.
- Video Intelligence Agent with provider fallback, step-by-step guidance (`/videos`), and explicit non-fabricated guidance disclosures.
- Fitness Pose Coach beta with user-initiated camera access and saved pose session summaries.
- Human operations staff profiles and task lifecycle.
- Single environment-configured owner enforcement across Admin web/API/tool workflows; Admin registration and self-promotion remain blocked.
- Bounded deterministic Core Agent plans executed only through registered server handlers.
- Real optional Ollama and OpenAI-compatible local inference adapters, privacy-approved cloud routing, strict structured output, deterministic fallback, and metadata-only routing logs.
- Persistent agent tasks, attempts, idempotency, categorized retries, events, approvals, and proactive alerts.
- Authenticated actor-scoped event polling as the real-time messaging foundation.
- Medical-record storage, notifications, telehealth, database-readiness, and infrastructure status provider boundaries.
- Owner Command Center 2.0 with working commands, retries, approvals, and alert controls.
- Truthful M8/M8.1 capability registry and reports in `docs/MILESTONE8.md` and `docs/MILESTONE8_1.md`.
- Owner-only M8.2 Model Evaluation Lab with fixed candidate metadata, versioned synthetic test cases, dry/mock execution, deterministic and human-review scoring, safety-first comparison, metadata-only persistence, and a default-off two-step real-local workflow.
- Truthful M8.2 capability and future ZENDOC-SLM boundaries in `docs/MILESTONE8_2.md` and `docs/ZENDOC_SLM_ROADMAP.md`.
- Register-once/login-again behavior with NFKC/case/whitespace-normalized email identity, clear duplicate/credential messages, rotating sessions, idle-expiry-to-login, and CSRF-protected production logout.
- Purpose-bound, expiring local-beta reset tokens that cannot authenticate as API bearer tokens; production recovery delivery remains Integration Required.
- Explicit SQLite/PostgreSQL database target resolution, a BETA psycopg compatibility adapter, additive M8.3 migration tracking, and isolated-test protection from production `DATABASE_URL`.
- Owner-visible persistence engine/durability/redeploy status with no credential disclosure, plus a strict optional production fail-closed mode.
- Restart persistence tests retaining stable patient/provider IDs, roles, profiles, health data, appointments, schedules, notifications, conversations, and messages.
- M8.3 release, production-persistence, rollback, and evidence-based demo checklist documentation.

## Not Yet Production-Certified

- No HIPAA/GDPR/DPDP legal review.
- No clinical validation or medical-device certification.
- No model is bundled or automatically downloaded. Local inference is available only when an operator installs a supported server and configures a model; no local model is claimed medically trained or certified. ZENDOC has no proprietary trained model.
- No real base-model benchmark, automatic model recommendation, training, or fine-tuning has been performed. M8.2 dry/mock results are framework verification only; real-local evaluation remains Integration Required and explicitly owner initiated.
- No OCR/document extraction provider or clinically validated report interpretation.
- Consent controls are a technical foundation, not a legal compliance certification.
- No payment, insurance, medicine delivery, or telemedicine video module.
- No live ambulance dispatch, ETA, or operational home healthcare fulfillment integration.
- No real pharmacy stock confirmation or delivery partner integration.
- No real IoT vendor sync adapter yet; device sync is an internal architecture and provenance path.
- No production WebRTC signaling/TURN/STUN telemedicine stack yet.
- No MediaPipe or clinical-grade pose estimation yet.
- No real staff dispatch/mobile workforce system yet.
- Live managed-PostgreSQL provisioning, existing-data import rehearsal, and production restart/redeploy verification remain Integration Required. The adapter is BETA until that evidence exists.
- Local uploaded medical files still require external object storage or a verified persistent mount.
- No object storage, queue worker, background extraction job, or cloud deployment automation.

## Launch Recommendation

**SELECTION BETA READY — PERSISTENCE LIMITATION DISCLOSED.** The platform is hardened and verified for the selection round. 100% of core flows function reliably in local SQLite and test suites. Permanent production persistence is classified as `INTEGRATION REQUIRED` and Render free-tier ephemeral storage is disclosed as a known temporary limitation to external testers. ZENDOC provides healthcare organization and decision support, not final diagnosis, clinical certification, or emergency care.
