# ZENDOC Roadmap To Full Healthcare Ecosystem

## Milestones 1-4: Platform And Health Memory

Complete in this codebase: security and authentication hardening, central AI safety and intent routing, verified provider discovery, connected appointments, private health profiles, longitudinal timeline, structured reports, measurements, trends, scoped consent, and mobile APIs.

## Milestone 5: Fitness And Nutrition

- Fitness plan service with safe personalization boundaries.
- Exercise education and legitimate video-provider integrations.
- General wellness nutrition logging and goals.
- Progress tracking connected to Health Memory with explicit consent.

## Milestone 6: Production UX And Connected Care

- Premium Health Command Center dashboard and consistent healthcare SaaS UI.
- One-time account registration, persistent session controls, password reset architecture, and environment-driven admin bootstrap.
- Family Care and Remote Parent Care with scoped consent grants and audit trails.
- Saved locations, home healthcare requests, medical transport, pharmacy services, marketplace, universal search, and IoT health device hub.
- Truthful integration boundaries for beta, verified provider, integration required, and coming soon services.

## Milestone 7 & 7.1: Agentic Core, Telehealth, ZENDOC Connect, Camera, Video, Operations

- ZENDOC Core Agent with permissioned communication and domain tools, safety-first routing, and audit trails.
- Admin Agent Command Center for platform health, failed operations, integrations, and agent audit trails (with strict private chat privacy boundaries).
- Doctor availability, customizable patient message policies, consultation requests, and local-demo voice/video controls.
- **ZENDOC Connect (Milestone 7.1)**: Unified permissioned messaging (`/messages`), contact discovery by name/role/specialty without exposing private identifiers, delivery/read receipts, unread badges, structured message cards, and consent-driven record sharing.
- **Video Guidance & Intelligence**: Truthful video search and step-by-step guidance (`/videos`) with explicit non-fabricated fallback disclaimers.
- Universal Search integration across providers, family, permitted contacts, conversations, and educational videos.
- Reusable camera infrastructure and Fitness Pose Coach beta.
- Human operations staff profiles and task lifecycle.

## Milestone 8: Agentic Intelligence And Owner Operations

- Single environment-configured ZENDOC owner and server-side Admin enforcement.
- Bounded Core Agent planner/executor with deterministic safety first.
- Local SLM and cloud model-provider adapters with truthful fallback status.
- Specialized Agent Registry and Permissioned Tool Registry.
- Persistent tasks, attempts, events, approvals, alerts, retries, and idempotency.
- Authenticated incremental event polling and provider abstractions.
- Owner Command Center 2.0 with real workflow controls and capability matrix.
- PostgreSQL/external storage/notification/WebRTC readiness boundaries without fabricated integration.

## Milestone 8.1: Local AI Runtime And Intelligent Routing

- Real optional Ollama and OpenAI-compatible local inference adapters.
- Configurable small-model selection with no automatic install or download.
- Deterministic emergency and restricted-task handling before model routing.
- Privacy-aware local/cloud/fallback selection and explicit cloud consent policy.
- Strict structured-output validation with no direct model-to-tool execution.
- Truthful provider/server/model health and owner-only AI Runtime observability.
- Metadata-only inference logs, safe fallback reasons, and legacy M8 database compatibility.

## Milestone 8.2: Base Model Evaluation Lab And ZENDOC-SLM Foundation

- Fixed, claim-conscious registry for development baseline and future candidate metadata; no automatic model download.
- Versioned synthetic-only ZENDOC evaluation cases with provenance, allowed-use, PHI/PII, quality, and safety governance fields.
- Dry-run and mock defaults plus an owner-only, default-off, explicitly confirmed real-local runner.
- Deterministic structured-output, policy-boundary, timeout, and safety scoring with explicit human-review dimensions.
- Critical safety disqualification before capability or efficiency comparison.
- Additive metadata-only result persistence and laptop-safe execution bounds.
- Future ZENDOC-SLM architecture documented without training, fine-tuning, or proprietary-model claims.

## Milestone 8.3: Demo Stabilization And Persistent Accounts

- Correct production database selection so `DATABASE_URL` is no longer ignored.
- Preserve local/test SQLite while adding a managed-PostgreSQL adapter and additive migration tracking.
- Distinguish durable account identity from expiring browser sessions.
- Harden identifier normalization, duplicate handling, reset-token purpose/expiry, session rotation, and production logout CSRF.
- Surface persistence engine, durability, and redeploy-verification status in the owner Command Center without exposing credentials.
- Add restart/data/role persistence, legacy migration, configuration, security, and demo-route verification.
- Keep external tester readiness blocked until production persistence is configured and manually redeploy-verified.

## Milestone 9: Mental Wellness

- Context-aware check-ins, journaling, breathing, sleep, and stress tracking.
- Strong crisis escalation and age/context-appropriate support.

## Milestone 10: Medicine And Pharmacy Integrations

- Real pharmacy partner integrations for inventory and delivery status.
- Prescription-aware order validation and refill workflows.
- No AI prescribing.

## Milestone 11: Admin, Analytics, And Notifications

- Unified notification delivery architecture.
- AI safety/usage analytics, moderation, error operations, and expanded audit reporting.

## Milestone 12: Mobile And Production Hardening

- Operational PostgreSQL migration/import rehearsal, backup/restore drills, and production cutover verification.
- S3-compatible file storage.
- Redis/worker queue for notifications, extraction, and AI jobs.
- OpenAPI schema and generated Flutter client models.
- Structured logs, monitoring, backups, CI/CD, penetration testing, and distributed rate limiting.
- Data deletion, retention, recovery, and incident response workflows.

## Compliance And Clinical Governance

- Legal review of consent, privacy notices, and regional obligations.
- Clinical safety review, model evaluation, and human escalation processes.
- Data retention and deletion policy.
- Security review and threat modeling.
- Region-specific HIPAA/GDPR/DPDP alignment.
