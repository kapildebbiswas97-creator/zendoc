# ZENDOC

ZENDOC is an AI-powered healthcare MVP foundation with role-based access, emergency-first AI orchestration, provider discovery, connected appointments, private health profiles, a longitudinal health timeline, structured reports, health monitoring, patient-controlled provider access, notifications, admin operations, and mobile-ready APIs.

## Run Locally

```powershell
python -m pip install -r requirements.txt
python run.py
```

Open `http://127.0.0.1:5000`.

## Admin User

Set these environment variables before first startup if you want the app to seed an admin user:

```powershell
$env:ZENDOC_ADMIN_EMAIL="admin@example.com"
$env:ZENDOC_ADMIN_PASSWORD="replace-with-a-strong-password"
```

## Test

```powershell
pytest
```

## Production Notes

Set `ZENDOC_ENV=production`, `ZENDOC_SECRET_KEY`, `ZENDOC_ADMIN_EMAIL`, and `ZENDOC_ADMIN_PASSWORD` in the environment. Use PostgreSQL and external object storage before production healthcare data.

Optional AI provider selection is controlled with `ZENDOC_AI_PROVIDER`. If no external provider is configured, ZENDOC uses the deterministic local fallback.

Healthcare finder external integrations are controlled by `ZENDOC_PLACES_PROVIDER` and provider-specific keys such as `ZENDOC_GOOGLE_PLACES_API_KEY`. With no key, the app still runs and returns a truthful unavailable message.

Milestone 4 architecture and limitations are documented in `docs/HEALTH_MEMORY.md`. ZENDOC does not claim clinical validation or regulatory compliance.
