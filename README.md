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

## Milestones 6-7

Milestone 6 adds the consumer-grade healthcare ecosystem layer:

- Health Command Center dashboard and upgraded design system.
- One-time registration, persistent sessions, remember me, logout, password reset architecture, and secure admin bootstrap.
- Family Care with scoped caregiver consent, care tasks, and remote parent care workflows.
- Home healthcare, ambulance/medical transport, pharmacy, marketplace, universal search, saved locations, and IoT device hub APIs.
- Truthful service statuses for connected, beta, integration required, and coming soon capabilities.
- No fabricated providers, prices, stock availability, ETAs, or device integrations.

Milestone 7 & 7.1 adds the agentic core, telehealth beta workflows, ZENDOC Connect permissioned messaging, camera intelligence foundations, video intelligence, and human operations. Details, limitations, files changed, and validation notes are in `docs/MILESTONE6.md`, `docs/MILESTONE7.md`, and `docs/ZENDOC_CONNECT.md`.

## Production Notes

Set `ZENDOC_ENV=production`, `ZENDOC_SECRET_KEY`, `ZENDOC_ADMIN_EMAIL`, and `ZENDOC_ADMIN_PASSWORD` in the environment. Use PostgreSQL and external object storage before production healthcare data.

Optional AI provider selection is controlled with `ZENDOC_AI_PROVIDER`. If no external provider is configured, ZENDOC uses the deterministic local fallback.

Healthcare finder external integrations are controlled by `ZENDOC_PLACES_PROVIDER` and provider-specific keys such as `ZENDOC_GOOGLE_PLACES_API_KEY`. With no key, the app still runs and returns a truthful unavailable message.

Health Memory architecture is documented in `docs/HEALTH_MEMORY.md`. Milestone 6 ecosystem architecture is documented in `docs/MILESTONE6.md`; Milestone 7/7.1 agent, telehealth, Connect, and operations architecture is documented in `docs/MILESTONE7.md` and `docs/ZENDOC_CONNECT.md`. ZENDOC does not claim clinical validation, emergency dispatch capability, production telemedicine capability, real provider inventory, or regulatory compliance.

