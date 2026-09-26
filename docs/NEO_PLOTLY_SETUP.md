# Neo.mjs + Plotly integration for ZENDOC

## Why this is an isolated first slice

ZENDOC's current Flask/PostgreSQL application is already covered by a large
production gate. Neo.mjs is therefore introduced as a separate engineering and
analytics surface first, not as a replacement for the working patient/provider
frontend.

The first contract is:

- ZENDOC remains the source of truth.
- Neo consumes ZENDOC APIs.
- Plotly visualizes aggregate operational/product metrics.
- Patient-level clinical text is not sent to the analytics surface.
- Existing consent, authorization, safety, truthfulness, and audit boundaries
  stay authoritative in Flask.
- Schemy may be used to design/version future database schemas. It is not a
  substitute for external healthcare/provider APIs.

## Current backend contract

Owner-only endpoint:

`GET /api/v1/admin/neo/analytics?days=30&provider_days=90`

It returns aggregate startup, activation, coverage, retention, care-journey,
provider-onboarding and pilot metrics.

## Windows setup for Neo.mjs

Prerequisites:

1. Node.js and npm installed.
2. Git installed.
3. A clean ZENDOC working tree.
4. Never put API keys or GitHub tokens into committed files.

For the base Neo app, the official create-app flow supports Windows 10+. For
Neo's fuller AI/knowledge-base tooling, its current AI quick-start recommends
Node.js 24+ and WSL on Windows because the ChromaDB-dependent tooling expects a
Linux environment. The bootstrap helper therefore warns when Node is older than
24; it does not pretend the full AI stack is ready on native Windows.

From the ZENDOC repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap_neo_workspace.ps1
```

The script creates a local `neo-workspace` directory with the official
`neo-app` bootstrap command but keeps it out of Git until the integration is
reviewed.

Neo's official create-app documentation uses:

```text
npx neo-app@latest
```

The generated workspace can be started with:

```powershell
cd neo-workspace
npm run server-start
```

The default development URL is normally under:

`http://localhost:8096/apps/zendocops/`

If the generated app name/path differs, use the URL printed by Neo.

## Secrets

Neo's create-app documentation describes a local `.env` for AI tooling such
as `GEMINI_API_KEY` and `GH_TOKEN`. Keep that file local and git-ignored.
Do not copy production ZENDOC database credentials into the Neo frontend.

Codex should be connected as an engineering agent, not given unrestricted
production-health-data access. Neo's current repository includes Codex-oriented
agent configuration and OpenAI/Codex maintainers, so we can use that workflow
after the local workspace and its security boundary are verified.

## Plotly phase

After the Neo workspace runs locally:

1. Build an owner analytics page.
2. Fetch only the aggregate analytics contract.
3. Render:
   - useful vs no-result Find Care searches,
   - activation funnel,
   - repeat-activity/retention evidence,
   - provider onboarding funnel,
   - pilot reliability/freshness signals,
   - geographic coverage counts.
4. Every chart must preserve `null`/unknown values instead of converting them
   to zero.
5. Do not create clinical risk scores, diagnosis rankings, or fake KPI targets.

Plotly's open-source libraries are suitable for interactive charts. The first
UI should remain an owner-only operations surface.

## Schemy phase

Use Schemy only when a new schema is actually necessary. Before adding a table:

1. Describe the minimum data required.
2. Exclude raw clinical content unless the feature genuinely requires it.
3. Create the schema in Schemy.
4. Review keys, constraints, tenancy, `environment_id`, `data_mode`,
   provenance, retention, and audit requirements.
5. Translate the reviewed schema into the repository's normal migration path.
6. Run SQLite, PostgreSQL readiness, safety/security, and release gates.

Do not treat Schemy as an API marketplace. External APIs still require a real
provider, documented authentication, contracts/terms where applicable, rate
limits, and truthful integration status.

## Next engineering slice

Once the backend contract is green and the local Neo workspace starts
successfully, build the first Plotly dashboard against this endpoint. Do not
migrate patient-facing UI yet.
