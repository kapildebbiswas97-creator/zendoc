# ZENDOC

ZENDOC is an AI-powered healthcare platform foundation with secure auth, role-based access, emergency-first AI orchestration, provider discovery, connected appointments, private health profiles, longitudinal health memory, fitness, family care, home healthcare requests, medical transport, pharmacy and diagnostic workflows, connected device provenance, official/public data ingestion, partner handoffs, and mobile-ready APIs.

ZENDOC follows one product rule across the stack: **recorded or configured is not the same as externally confirmed**. Providers, inventory, prices, availability, verification, dispatch, delivery, approvals, model health, and other external facts are never fabricated.

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

The authoritative release result is the GitHub **ZENDOC Production Gate** for the exact release commit. Do not treat a historical test count as a permanent product metric.

## Product architecture

The current codebase includes:

- Health Command Center, private Health Memory, records, timeline, vitals, reports, family care and fitness/wellness workflows.
- Provider onboarding/evidence review, schedules, appointments, healthcare finder and public/official data ingestion with provenance.
- Pharmacy, diagnostics, home-health, medical-transport and operational-fulfilment workflow foundations with explicit external-integration boundaries.
- ZENDOC Connect messaging, telehealth beta workflow, in-app notifications and human operations.
- Core Agent, specialized agents, persistent tasks/events/approvals, permissioned tool registry and owner command center.
- Deterministic emergency-first safety, approved knowledge/RAG foundation, optional local/cloud model routing, structured output validation, model evaluation and metadata-only runtime observability.
- Care Journey coordination, CareFin benefit discovery, partner/business API v1, institution pilots, startup analytics and release/readiness instrumentation.
- India geography/health-graph and official-source ingestion architecture where actual coverage is measured from ingested verified records rather than inferred from schemas.

Detailed milestone history remains in `docs/MILESTONE6.md` through the later milestone documents. The current truth boundary is maintained in `docs/FEATURE_TRUTH_MATRIX.md` and the runtime `zendoc/capability_registry.py`.

## AI and agent safety boundary

- Deterministic emergency/high-risk safety rules run before model routing.
- Model output is advisory and cannot directly execute registered tools.
- Server-side role, tenant, consent, owner/doctor approval, idempotency and audit policy decide whether a tool may execute.
- Autonomous prescribing and emergency dispatch remain blocked actions.
- Local AI and cloud AI are optional. A configured provider is not reported as reachable without a separate runtime health verification.
- Health-sensitive/high-risk content is restricted from unsafe cloud routing by policy.
- If a model/provider is unavailable or disallowed, deterministic fallback remains available.
- ZENDOC does not claim clinical validation, autonomous diagnosis/prescribing, a proprietary trained SLM, or regulatory approval.

Owner-only programmatic inspection is available through `/owner/intelligence-manifest` and `/owner/ai-runtime`; these status views do not make an external health-check call merely to render metadata.

## Production notes

Set `ZENDOC_ENV=production`, `ZENDOC_SECRET_KEY`, `ZENDOC_ADMIN_EMAIL`, and `ZENDOC_ADMIN_PASSWORD` in the environment. Configure `DATABASE_URL` for managed PostgreSQL and follow `docs/PRODUCTION_PERSISTENCE.md` for migration and persistence verification.

Production database truth is environment-dependent:

| Tier | Truth boundary |
|---|---|
| Local / test SQLite | Supported and tested for the local/test boundary |
| Same-database restart persistence | Supported when the deployment retains the configured database/storage |
| Managed PostgreSQL path | `WORKING` only when configured and operator persistence verification is recorded; otherwise runtime status remains `BETA`/`INTEGRATION_REQUIRED` |
| India-wide geography/facility ingestion architecture | Implemented; actual coverage remains source/import/provenance dependent |
| Enterprise multi-region HA / DR | `INTEGRATION_REQUIRED` |
| Public deployment health | Must be checked against the deployed revision after merge/deploy; PR CI alone does not prove it |

The live host must not be described as persistence-verified, deployment-healthy, or connected to a specific external provider unless that environment has actually been checked.

## Connected-service truth

ZENDOC-owned request and handoff workflows can be `WORKING` while real-world execution still requires integration. In particular:

- pharmacy stock, price, dispensing and doorstep delivery require authoritative pharmacy/logistics confirmation;
- ambulance/medical transport dispatch requires a real connected provider;
- home-health staffing/visit fulfilment requires connected verified care providers;
- external email/SMS/WhatsApp/push requires configured delivery providers;
- insurer/government/CSR/trust eligibility or payment confirmation requires authoritative responses;
- live Places/video/device/translation capabilities depend on their configured providers and current runtime health.

A ZENDOC request record never by itself means an external action happened.

## Startup product status

ZENDOC is developed as a startup product, not as a time-boxed hackathon prototype. Public demonstrations, competitions, pilots, accelerators, and investor meetings may use the same production branch, but product decisions optimize for long-term safety, data quality, interoperability, scalability, and user trust.

Operating principles:

- no fabricated providers, availability, prices, stock, beds, ratings, ETAs, verification, dispatch, delivery or integrations;
- no unauthorized private clinical-data ingestion;
- nationwide India coverage is a product target whose real coverage is measured from verified ingested data;
- external investment or accelerator participation is optional, not a dependency for product continuation;
- clinical, regulatory, security, privacy, traction and savings claims remain evidence-bound.

## Configuration pointers

Optional local model providers use `ZENDOC_LOCAL_AI_*` (`ZENDOC_SLM_*` remains a legacy compatibility alias); cloud providers use `ZENDOC_AI_*`. Real-local model evaluation is disabled by default and requires `ZENDOC_MODEL_EVALUATION_REAL_ENABLED=true`, an already-installed configured local runtime/model, and explicit owner confirmation. Tests and startup do not download or run models.

Healthcare finder external integrations are controlled by `ZENDOC_PLACES_PROVIDER` and provider-specific keys such as `ZENDOC_GOOGLE_PLACES_API_KEY`. With no configured provider, local/ingested finder behavior remains available according to the runtime capability status and the UI must not invent live Places results.

Relevant documentation:

- `docs/STARTUP_STRATEGY.md` — startup operating model, growth strategy, rollout, monetization, and investor path
- `docs/INVESTOR_READINESS.md` — evidence, traction, diligence, data room, metrics, and funding-readiness checklist
- `docs/ROADMAP.md` — product and infrastructure roadmap
- `docs/FEATURE_TRUTH_MATRIX.md` — current capability truth classification and external boundaries
- `docs/PRODUCTION_PERSISTENCE.md` — production persistence and migration guidance
- `docs/FINAL_RELEASE_AUDIT.md` — current release-verification rules and completion record
- `docs/openapi-partner-v1.yaml` / `docs/PARTNER_API_SPEC.md` — partner API contract
- `docs/HEALTH_MEMORY.md` and `ZENDOC_ARCHITECTURE.md` — health-memory and platform architecture
