# Milestone 8 — Agentic Intelligence and Owner Operations

## Implementation status

Milestone 8 is implemented as a local, permissioned production foundation. It does not claim that ZENDOC owns or trained a medical small language model, and it does not grant a model arbitrary database, SQL, shell, filesystem, network, or Admin access.

Current local SLM statement:

> Local SLM integration ready — model not configured.

The deterministic safety engine and deterministic local fallback remain available when no model provider is configured.

## Runtime architecture

```text
Environment-configured ZENDOC Owner
  -> ZENDOC Core Agent
  -> deterministic Safety / Policy Gate
  -> bounded deterministic Planner
  -> Model Router
       -> deterministic safety
       -> configured local/open SLM adapter
       -> configured cloud OpenAI-compatible adapter
       -> deterministic safe fallback
  -> Specialized Agent Registry
  -> Permissioned Tool Registry
  -> bounded Executor (20 steps / request timeout)
  -> Persistent Agent Tasks + Attempts
  -> Persistent Events + Authenticated Polling
  -> Human Approval Engine
  -> Human Operations
  -> Alerts + Audit + Model Routing Logs
```

Planning and tool authorization are deterministic. Model responses never decide permissions. Tools are explicit server-side callables; no arbitrary command execution tool exists.

## Owner-only Admin invariant

- `admin` cannot be registered by web or API clients.
- The only valid Admin identity is the active account whose normalized email matches `ZENDOC_ADMIN_EMAIL`.
- Fresh owner bootstrap requires `ZENDOC_ADMIN_EMAIL` and `ZENDOC_ADMIN_PASSWORD`. Existing owner accounts are matched by the configured email without resetting or exposing their password.
- Bootstrap refuses to promote an existing public account with the same email, preventing pre-registration takeover.
- Legacy M1-M7 databases with multiple Admin rows are reconciled only during database bootstrap and only when exactly one normalized account matches `ZENDOC_ADMIN_EMAIL` and that account is already one of the legacy Admin rows. That account remains Admin and every other Admin is demoted without deleting, merging, or resetting any account.
- A demoted account is restored to `doctor`, `hospital`, or `pharmacy` only when its provider profile reliably records that role. With no reliable role history, it receives the conservative `patient` fallback. Each correction is recorded in `audit_logs` as `security.legacy_admin_demoted.admin_to_<role>.<source>` with user IDs only; passwords, hashes, and emails are excluded.
- Reconciliation is atomic and idempotent and is marked as `m8_legacy_admin_reconciliation_v1`. Startup fails closed when owner configuration is missing or mismatched, or when duplicate normalized accounts make owner identity ambiguous.
- The partial unique SQLite Admin index is created only after reconciliation verifies that the configured owner is the sole Admin, then prevents a second Admin row at normal runtime.
- Web `owner_required`, API token validation, service assertions, tool checks, approval resolution, alert controls, and privileged task execution all re-check the owner server-side.
- Client-supplied `role=admin`, a forged Admin row, or a non-owner Admin bearer token does not grant privileged access.

## Planner, executor, agents, and tools

The Core Agent now creates an explicit plan containing an intent, specialized agent, risk level, bounded steps, and confirmation state. Every command creates a persistent task. Emergency text routes directly through `SafetyAgent` before any model or ordinary tool.

Registered agents include Safety, Care, Doctor/Telehealth, Communication, Fitness, Video, Family Care, Pharmacy, Home Health, Transport, IoT, Operations, and Search. Their metadata defines allowed roles, tools, risk, approval requirements, and truthful connection status.

The executor calls only registered handlers. Implemented handlers cover aggregate platform health, failed operations, permissioned contact discovery, unread counts, educational video guidance, authenticated IoT device records, and bounded proactive alert checks. Consent- or human-dependent actions stop in `waiting_human`/`waiting_approval` instead of being simulated.

Explicitly absent tools include arbitrary shell, arbitrary SQL, Python evaluation, unrestricted filesystem access, unrestricted database access, autonomous prescribing, and autonomous emergency dispatch.

## Model router and provider status

Routing order is:

1. Deterministic emergency safety.
2. Configured local SLM (`ollama` or OpenAI-compatible local endpoint).
3. Configured cloud OpenAI-compatible provider when cloud use is allowed and content is not privacy-sensitive.
4. Deterministic local fallback.

The local adapter performs real HTTP inference only when enabled with a model. The cloud adapter performs real OpenAI-compatible chat-completion requests only when provider, key, base URL/model configuration are complete. Failed providers fall back safely and record routing metadata. Prompts and hidden reasoning are not stored in model logs.

Environment variables:

- `ZENDOC_SLM_ENABLED`, `ZENDOC_SLM_PROVIDER`, `ZENDOC_SLM_BASE_URL`, `ZENDOC_SLM_MODEL`, `ZENDOC_SLM_TIMEOUT`
- `ZENDOC_AI_PROVIDER`, `ZENDOC_AI_API_KEY`, `ZENDOC_AI_BASE_URL`, `ZENDOC_AI_MODEL`, `ZENDOC_AI_TIMEOUT`

Configuration alone is reported as configured but connectivity not verified. ZENDOC has not trained a proprietary SLM.

## Persistent tasks, events, approvals, alerts, and recovery

- Task lifecycle: `queued -> running -> waiting_approval/waiting_human -> completed/failed/cancelled`.
- Attempts, duration, failure category, last error, timestamps, and bounded retry count are persisted.
- Idempotency keys return the original task/event rather than duplicating work.
- Only temporary, provider-unavailable, or timeout failures are retriable.
- Missing handlers fail; tasks never report a fake no-op completion.
- Events redact secret-like payload fields and support correlation/idempotency metadata.
- Authenticated polling returns all operational events to the owner and only actor-owned events to other users.
- Owner approvals and specifically assigned doctor approvals are supported. Critical-blocked actions cannot be approved.
- Approval decisions transition linked tasks and persist resolver/time/note metadata.
- Deterministic alert scans detect old approvals, exhausted agent tasks, and elevated recent platform errors; active alerts are deduplicated.

## Provider foundations

- **Database:** SQLite remains the working local backend. `DATABASE_URL` is detected for PostgreSQL readiness, but PostgreSQL remains Integration Required until its driver and production migrations are installed and tested.
- **Medical records:** A provider boundary now owns save/delete/download operations. Local filesystem storage works; external object storage remains Integration Required.
- **Notifications:** In-app delivery is real and persisted in both the user feed and delivery ledger. Email, SMS, WhatsApp, and push requests are stored as `integration_required`; delivery is never fabricated.
- **Real time:** Incremental authenticated event polling is working. WebSocket/SSE infrastructure remains Integration Required.
- **Telehealth:** Local consultation state, rooms, and chat remain a beta workflow through a provider abstraction. Production WebRTC/TURN/STUN remains Integration Required.

## Owner Command Center 2.0

`/admin/agent-command-center` now exposes real backend state and actions:

- plan-and-execute Core Agent commands;
- model router and fallback statistics;
- persistent tasks and safe retry queuing;
- pending approvals with approve/reject actions;
- active alerts with scan/acknowledge/resolve actions;
- specialized agent/tool metadata;
- infrastructure provider status;
- complete capability matrix;
- agent audit history and operational counts.

Every rendered action posts to a real owner-gated server workflow with CSRF protection.

## Database migration

The additive migration is recorded as `m8_agent_platform_v1` in `schema_migrations`.

New tables:

- `agent_tasks`
- `agent_task_attempts`
- `agent_alerts`
- `model_execution_logs`
- `notification_deliveries`
- `schema_migrations`

Extended tables:

- `agent_approvals`: agent/user/task linkage, risk, designated approver, expiry, resolution metadata, and backward-compatible M7 fields.
- `platform_events`: namespaced type, redacted JSON payload, correlation ID, and idempotency key.

Security/recovery indexes include one-Admin enforcement, task status/requester lookup, approval status, active-alert deduplication, event idempotency, model provider/actor lookup, and notification delivery lookup.

## M8 API surface

- `GET /api/v1/capabilities`
- `GET /api/v1/agent/registry`
- `GET /api/v1/agent/tools`
- `GET /api/v1/agent/tasks`
- `GET /api/v1/agent/tasks/<id>`
- `POST /api/v1/agent/tasks/<id>/execute`
- `POST /api/v1/agent/tasks/<id>/retry`
- `GET /api/v1/agent/approvals`
- `POST /api/v1/agent/approvals/<id>/decision`
- `GET /api/v1/events`
- `POST /api/v1/admin/agent/tasks`
- `GET /api/v1/admin/model-router`
- `GET /api/v1/admin/infrastructure`
- `GET /api/v1/admin/approvals`
- `POST /api/v1/admin/approvals/<id>/decision`
- `GET /api/v1/admin/alerts`
- `POST /api/v1/admin/alerts/check`
- `POST /api/v1/admin/alerts/<id>/acknowledge`
- `POST /api/v1/admin/alerts/<id>/resolve`

All endpoints require authentication. Admin-prefixed endpoints additionally require the configured owner identity.

## Capability matrix

| Capability | Status | Notes |
|---|---|---|
| Owner-only Admin and bootstrap | WORKING | Environment-bound, single owner, escalation tests |
| Deterministic safety | WORKING | Runs before model/tool routing |
| Core Agent planner/executor | WORKING | Bounded, permissioned, persistent |
| Specialized Agent Registry | WORKING | Role/tool/risk metadata |
| Permissioned Tool Registry | WORKING | No arbitrary execution |
| Agent tasks, attempts, retries, idempotency | WORKING | Retriable categories only |
| Persistent event bus and authenticated polling | WORKING | User-scoped; secret redaction |
| Approval engine | WORKING | Owner and designated-doctor paths |
| Proactive operational alerts | WORKING | Deterministic scans and dedupe |
| Model Router | WORKING | Routing and safe fallback |
| Deterministic local fallback | WORKING | No model inference claim |
| Local SLM inference | INTEGRATION REQUIRED | Adapter ready; model not configured/tested |
| Cloud LLM inference | INTEGRATION REQUIRED | Adapter ready; provider not configured/tested |
| ZENDOC proprietary trained SLM | FUTURE | No proprietary model has been trained |
| SQLite local database | WORKING | Local development backend |
| PostgreSQL production database | INTEGRATION REQUIRED | Driver and migrations not installed/tested |
| Local medical-record storage | WORKING | Development filesystem provider |
| External object storage | INTEGRATION REQUIRED | Provider adapter not installed/tested |
| In-app notifications | WORKING | Feed plus delivery ledger |
| Email/SMS/WhatsApp/push | INTEGRATION REQUIRED | Requests recorded, not falsely delivered |
| Authenticated real-time polling | WORKING | Incremental event endpoint |
| WebSocket/SSE messaging | INTEGRATION REQUIRED | External realtime adapter required |
| Telehealth local workflow | BETA | State, room, chat |
| Production WebRTC telehealth | INTEGRATION REQUIRED | Signaling/TURN/STUN provider required |
| Health memory, records, finder, family, fitness, Connect | WORKING/BETA | Existing M1-M7.1 behavior preserved |
| Home health/transport/pharmacy intake | WORKING | External fulfillment remains Integration Required |
| Autonomous prescribing/dispatch | FUTURE / CRITICAL BLOCKED | Never agent-executable |

## Security and privacy boundaries

- Owner access is server-controlled and revalidated on each privileged workflow.
- Record sharing remains consent-gated.
- Clinical conversation content is not exposed in owner operational summaries.
- Event payloads redact password/token/secret/API-key fields.
- Model logs store routing metadata, never prompts or hidden chain-of-thought.
- Upload signature checks, path containment, hashed API tokens, CSRF, rate limiting, ownership checks, and audit logs remain in force.
- This is a technical security/privacy foundation, not legal or clinical certification.

## Remaining blockers

- Configure and test a real local model endpoint if local inference is desired.
- Configure and test a cloud provider if cloud inference is desired.
- Add PostgreSQL driver/migrations and validate at production scale.
- Add external object storage, notification, realtime, and WebRTC providers.
- Complete security review, threat modeling, penetration testing, backup/restore validation, observability export, and HIPAA/GDPR/DPDP/legal review before production health-data use.
