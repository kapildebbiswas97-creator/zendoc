# ZENDOC — Feature Truth Matrix

**Truth model updated:** 20 September 2026  
**Authoritative runtime source:** `zendoc/capability_registry.py`  
**Owner inspection:** `/owner/intelligence-manifest` and `/owner/ai-runtime`

This document describes the product boundary. It is intentionally conservative. Environment-dependent capabilities must be read from the runtime capability registry rather than inferred from screenshots, configuration files, demo data, or old release notes.

## Status taxonomy

ZENDOC uses exactly these runtime statuses:

- **`WORKING`** — the ZENDOC-owned software workflow is implemented and tested for its stated boundary.
- **`BETA`** — the workflow is usable, but a provider, model, browser feature, or operational dependency still limits production guarantees.
- **`INTEGRATION_REQUIRED`** — ZENDOC has a safe integration/workflow boundary, but a real external provider, credential, authorization, partner, infrastructure service, or verified dataset is required.
- **`DISABLED`** — deliberately unavailable by policy or configuration.
- **`FUTURE`** — intentionally outside the current implemented product boundary.

`Configured` does not mean `reachable`, and a recorded request does not mean an external action occurred.

## Current capability truth

| Domain | Capability | Truth status | Current boundary |
| --- | --- | --- | --- |
| Security | Role/session/owner authorization | `WORKING` | Server-side authorization protects owner, patient, provider and tenant-scoped resources. |
| Security | CSRF, IDOR and audit controls | `WORKING` | Mutating web flows use CSRF validation; protected records are subject to ownership/role checks and audited access. |
| AI safety | Deterministic emergency safety gate | `WORKING` | Runs before model routing for safety-sensitive guidance; models do not replace emergency services. |
| AI governance | Model router | `WORKING` | Routes by privacy/risk/configuration. Model output cannot directly execute tools. |
| AI governance | Tool registry and approval boundary | `WORKING` | Role, consent, owner/doctor approval, idempotency and audit policy are enforced server-side. Critical autonomous prescribing/dispatch actions remain blocked. |
| AI product | ZENDOC-SLM product layer | `WORKING` | Safety, approved context, structured validation and advisory response layer work without claiming a particular local model is installed. |
| AI runtime | Local model provider | `BETA` or `INTEGRATION_REQUIRED` | Depends on runtime model/provider configuration and explicit health verification. |
| AI runtime | Cloud LLM provider | `BETA` or `INTEGRATION_REQUIRED` | Depends on configured provider/key/model; health-sensitive and high-risk routing remains restricted. |
| AI knowledge | Approved knowledge/RAG foundation | `WORKING` | Curated/provenance-aware repository knowledge and ingestion workflow; discovered sources are not automatically trusted for patient answers. |
| Health memory | Records, timeline, vitals and access controls | `WORKING` | Persistent application records with provenance and authorization. Uploaded content is not automatically clinician-verified. |
| Reports | Report intelligence | `BETA` | Deterministic educational interpretation and report workflow; not diagnosis. |
| Appointments | Provider profiles, schedules and booking state | `WORKING` | ZENDOC-owned scheduling/booking records work; external provider truth is shown only when confirmed. |
| Finder | Local/ingested healthcare finder | `BETA` or `WORKING` | Local/verified records work. Live Places status depends on configured provider and server-side key. |
| Global search | Restored product-module discovery | `WORKING` | Global search can surface Mental Wellness, Community, Health Shop, Messages/calling, Payments, Health Memory and AI in addition to healthcare discovery. |
| Provider network | Onboarding and evidence review | `WORKING` | Providers submit evidence; owner review controls verification. ZENDOC does not auto-verify from self-asserted data. |
| Public data | Official/public dataset ingestion | `WORKING` | Owner-only dry-run/apply, checksums, schema mapping, provenance, rejection reasons and idempotent upsert are implemented. |
| Public data | Live official connectors | `INTEGRATION_REQUIRED` | LGD/OGD/ABDM or other sources require source-specific download/API/authorized access. |
| Geography | India hierarchy and health graph foundation | `WORKING` | Ingestion/search architecture is implemented; production coverage depends on actually ingested verified records. |
| Pharmacy | Catalog/search/request workflow | `WORKING` | ZENDOC can manage/search recorded data and create fulfilment workflow records. |
| Pharmacy | Real stock, price, dispensing and doorstep delivery | `INTEGRATION_REQUIRED` unless confirmed by connected source | Never inferred or fabricated. External execution requires a real pharmacy/logistics response. |
| Diagnostics | Diagnostic workflow and report linking | `WORKING` | Request/status/report-link lifecycle includes provenance, notifications and concurrency-safe completion handling. |
| Transport | Medical transport request intake | `WORKING` | ZENDOC can record and track a request. |
| Transport | Real ambulance dispatch | `INTEGRATION_REQUIRED` | ZENDOC never claims dispatch without a connected provider confirmation. |
| Home health | Service request intake | `WORKING` | ZENDOC can record and coordinate the request state. |
| Home health | Real staffing/visit fulfilment | `INTEGRATION_REQUIRED` | Requires connected, verified care providers. |
| Care journeys | Deterministic care journey coordinator | `WORKING` | Durable coordination state machine with human gates and next-safe-action logic; no diagnostic authority. |
| CareFin | Benefit discovery | `WORKING` | Provenance-aware discovery and missing-information analysis. |
| CareFin | Personal eligibility/approval/payment confirmation | `INTEGRATION_REQUIRED` | Requires authoritative government/insurer/CSR/trust/payment responses. |
| Family care | Family/dependent coordination | `WORKING` | Permissioned app workflow; real-world care remains subject to connected providers. |
| Messaging | ZENDOC Connect | `WORKING` | Policy-aware conversations, read state, native participant-protected image/video attachments, report/video-link sharing, blocking and in-app notifications. |
| Calling | Browser WebRTC voice/video | `BETA` | Authenticated signaling, offer/answer/ICE exchange, call lifecycle, browser media controls and stale-call cleanup are implemented. Network reachability still depends on real STUN/TURN configuration and end-to-end browser verification. |
| Telehealth | Consultation + ZENDOC Connect WebRTC | `BETA` | Consultation request/acceptance, scoped chat and authenticated browser voice/video call entry are connected. Reliable public-network calling still depends on verified STUN/TURN infrastructure and two-device testing. |
| IoT | Device registration/manual measurements | `BETA` | Device records and measurement provenance work; live hardware sync requires device SDK/integration. |
| Mental wellness | Private check-ins and journal | `WORKING` | User-owned mood/stress/energy/sleep self-ratings, private journal history and user deletion controls are implemented. ZENDOC does not turn these into a diagnosis or personality score. |
| Community | Health Community | `WORKING` | Health-focused posts, stories, comments, likes, follows, saved posts, blocking, reporting, author deletion and authenticated media access are implemented. User-generated content is not verified medical advice. |
| Community | Durable public image/video storage | `INTEGRATION_REQUIRED` unless configured and verified | Local development media works; hosted persistence requires verified S3-compatible storage or equivalent durable object storage. |
| Commerce | Health Shop discovery | `WORKING` | External merchant discovery and ZENDOC outbound-click evidence are implemented without claiming stock, price, conversion or commission. |
| Commerce | Affiliate/referral revenue | `INTEGRATION_REQUIRED` unless approved/configured | Requires a real merchant program/approved affiliate deep link and authoritative conversion/settlement evidence. A click is not revenue. |
| Payments | Connected payment gateway | `INTEGRATION_REQUIRED` unless configured and verified | Payment workflow exists; successful payment requires genuine gateway credentials and signed webhook/verification evidence. |
| Fitness | Plans, sessions, nutrition and hydration | `WORKING` | General wellness tooling; not medical diagnosis/treatment. |
| Fitness camera | Camera preview | `BETA` | Browser-local preview only; no fabricated pose/rep/form analysis. |
| Notifications | In-app notifications | `WORKING` | Delivered inside ZENDOC. |
| Notifications | External email/SMS/WhatsApp/push | `INTEGRATION_REQUIRED` | Requires configured real delivery providers. |
| Database | SQLite application persistence | `WORKING` | Supported for local/test operation. |
| Database | PostgreSQL | runtime-dependent | `WORKING` only when configured **and** operator persistence verification is recorded; otherwise `BETA`/`INTEGRATION_REQUIRED`. |
| Storage | Secure local record storage | `WORKING` for its deployment boundary | Production object storage is separately configuration/integration dependent. |
| Operations | Pilot analytics, observability and safe operations automation | `WORKING` | Metrics are derived from stored ZENDOC events; no invented traction, savings, uptime or provider performance. |
| Partner API | Business/partner API v1 | `WORKING` for ZENDOC-owned API boundary | API keys, rate limits, audit events and handoffs are implemented; partner-side execution remains external. |

## Non-negotiable truth boundaries

1. **No fake healthcare inventory:** providers, facilities, medicine stock, prices, slots, ratings, distance, ETA or verification must come from stored/verified/connected evidence.
2. **No fake external execution:** ambulance dispatch, medicine delivery, home-health staffing, insurer approval, payment, messaging delivery and similar actions are not complete until a real external system confirms them.
3. **No autonomous clinical authority:** ZENDOC AI can provide educational guidance and workflow suggestions. It cannot autonomously diagnose, prescribe, or bypass clinician/owner approval gates.
4. **No model-to-tool shortcut:** language-model output is advisory. Server-side policy decides whether any registered tool may execute.
5. **No configuration-as-health claim:** presence of an API key/model URL/provider setting is not proof the service is currently reachable.
6. **No static coverage claim:** geographic/data coverage is measured from ingested records and provenance, not from the existence of a schema or connector.

## Verification rule

Do not publish a fixed test count or production-health claim from this document. The current branch/release must pass the repository's **ZENDOC Production Gate**, including security/safety, SQLite, PostgreSQL readiness and release-gate jobs. Deployment health must be checked separately after merge/deployment; PR CI does not prove the public deployment is healthy.
