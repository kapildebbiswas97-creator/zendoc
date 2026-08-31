# ZENDOC

ZENDOC is an AI-powered healthcare platform foundation with secure auth, role-based access, emergency-first AI orchestration, provider discovery, connected appointments, private health profiles, longitudinal health memory, fitness, family care, home healthcare requests, medical transport, pharmacy workflows, connected device provenance, saved locations, and mobile-ready APIs.

## Run Locally

```powershell
python -m pip install -r requirements.txt
python run.py
```

Open `http://127.0.0.1:5000`.

## Admin User

Set these environment variables before startup to seed or maintain the configured admin user. Admin email and password must come from the environment and must not be committed.

```powershell
$env:ZENDOC_ADMIN_EMAIL="admin@example.com"
$env:ZENDOC_ADMIN_PASSWORD="replace-with-a-strong-password"
```

## Test

```powershell
python -m pytest tests
```

## Milestones 6-8

Milestone 6 adds the consumer-grade healthcare ecosystem layer:

- Health Command Center dashboard and upgraded design system.
- One-time registration, persistent sessions, remember me, logout, password reset architecture, and secure admin bootstrap.
- Family Care with scoped caregiver consent, care tasks, and remote parent care workflows.
- Home healthcare, ambulance/medical transport, pharmacy, marketplace, universal search, saved locations, and IoT device hub APIs.
- Truthful service statuses for connected, beta, integration required, and coming soon capabilities.
- No fabricated providers, prices, stock availability, ETAs, or device integrations.

Milestone 7 & 7.1 adds the agentic core, telehealth beta workflows, ZENDOC Connect permissioned messaging, camera intelligence foundations, video intelligence, and human operations. Details, limitations, files changed, and validation notes are in `docs/MILESTONE6.md`, `docs/MILESTONE7.md`, and `docs/ZENDOC_CONNECT.md`.

Milestone 8 adds the environment-bound single owner invariant, bounded Core Agent planner/executor, specialized agent and permissioned tool registries, persistent tasks/events/approvals/alerts, provider boundaries, and Owner Command Center 2.0. Milestone 8.1 adds real optional Ollama/OpenAI-compatible local inference, strict structured output, privacy-aware routing, truthful provider/model health, metadata-only observability, and a safe owner runtime test. Milestone 8.2 adds an owner-only, synthetic, safety-first base-model evaluation framework with dry/mock defaults and a default-off, explicitly confirmed real-local path. Milestone 8.3 separates account persistence from session lifetime, adds managed-PostgreSQL configuration and safe additive migration readiness, hardens recovery/session behavior, and makes unsafe production persistence visible to the owner. Local AI remains optional and deterministic fallback is always available. See `docs/MILESTONE8.md` through `docs/MILESTONE8_3.md`.

## Production Notes

Set `ZENDOC_ENV=production`, `ZENDOC_SECRET_KEY`, `ZENDOC_ADMIN_EMAIL`, and `ZENDOC_ADMIN_PASSWORD` in the environment. Configure a secret managed-PostgreSQL `DATABASE_URL` (recommended) or an explicitly verified persistent SQLite mount before external testing. Service-local SQLite on Render free is ephemeral and is reported as **INTEGRATION REQUIRED**. Follow `docs/PRODUCTION_PERSISTENCE.md`; do not switch an existing account database without a reviewed backup/import.

## Selection Beta — Truthful Status Disclosure

ZENDOC is currently in **Selection Beta** (Milestone 8.3 hardened). All 192 automated tests pass. The following persistence tiers are available:

| Tier | Status |
|---|---|
| Local / test SQLite | WORKING |
| Same-database restart persistence | WORKING |
| PostgreSQL adapter (code complete) | BETA — requires DATABASE_URL |
| Permanent production cloud persistence | INTEGRATION REQUIRED |
| Render free-tier ephemeral SQLite | Known selection-beta limitation |

Permanent production persistence is intentionally not configured before the selection round. This limitation is disclosed to testers and does not block the Selection Beta from proceeding.

Relevant documentation:
- `docs/FEATURE_TRUTH_MATRIX.md` — Complete 43-capability truthful classification
- `docs/EXTERNAL_BETA_CHECKLIST.md` — 9-journey tester checklist with seed accounts
- `docs/SELECTION_DEMO_RUNBOOK.md` — 5-minute live demo script
- `docs/FINAL_RELEASE_AUDIT.md` — Full audit report (issues found, fixed, verified)

Optional local model providers are controlled with `ZENDOC_LOCAL_AI_*` (`ZENDOC_SLM_*` is retained as a legacy compatibility alias); cloud providers use `ZENDOC_AI_*`. If a provider is not ready or privacy policy disallows it, ZENDOC uses deterministic local fallback and never claims model inference occurred.

Real-local model evaluation is separately disabled by default. It requires `ZENDOC_MODEL_EVALUATION_REAL_ENABLED=true`, an already-installed configured local runtime/model, and a two-step owner confirmation. Tests and startup never download or run models.

Healthcare finder external integrations are controlled by `ZENDOC_PLACES_PROVIDER` and provider-specific keys such as `ZENDOC_GOOGLE_PLACES_API_KEY`. With no key, the app still runs and returns a truthful unavailable message.

Health Memory architecture is documented in `docs/HEALTH_MEMORY.md`. Milestone 6 ecosystem architecture is documented in `docs/MILESTONE6.md`; Milestone 7/7.1 agent, telehealth, Connect, and operations architecture is documented in `docs/MILESTONE7.md` and `docs/ZENDOC_CONNECT.md`; M8-M8.3 are documented in `docs/MILESTONE8.md`, `docs/MILESTONE8_1.md`, `docs/MILESTONE8_2.md`, and `docs/MILESTONE8_3.md`. The future model path is in `docs/ZENDOC_SLM_ROADMAP.md`. ZENDOC does not claim clinical validation, emergency dispatch capability, production telemedicine capability, a proprietary trained SLM, real provider inventory, or regulatory compliance.
