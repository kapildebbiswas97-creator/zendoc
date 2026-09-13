# ZENDOC — Release Verification Record

**Verification model updated:** 13 September 2026  
**Current completion branch:** `release/system-completion-v1`  
**Authoritative code truth:** runtime capability registry + current GitHub Production Gate  
**Deployment truth:** must be verified separately after merge/deploy

This file replaces the obsolete August pre-selection snapshot. It is a release-verification record, not a permanent production certificate. ZENDOC changes frequently; old commit hashes, route counts, test counts, provider configuration and deployment-health claims must not be presented as current facts after the code changes.

## Current release objectives

The completion branch consolidates the current mobile-first frontend with the latest healthcare safety baseline and closes remaining truth/integration gaps without fabricating external services.

Current verified design requirements are:

- emergency-first deterministic safety remains ahead of model output;
- language-model output cannot directly execute registered tools;
- role, tenant, consent, human approval, idempotency and audit rules remain server-side;
- patient/provider/owner data access is authorization-scoped;
- external actions are recorded as requests/handoffs until an authoritative provider confirms execution;
- public/official datasets retain source/provenance and are not treated as complete simply because a connector exists;
- provider verification requires evidence/review rather than self-assertion;
- AI runtime status distinguishes configured providers from actually verified reachability;
- patient-facing AI clearly separates the governed ZENDOC AI path from deterministic navigation/wellness helpers;
- stale claims about medicine delivery, ambulance dispatch or unsupported model behavior are rejected by tests.

## Completion work represented by this release

### Frontend and patient experience

- Warm, mobile-first public homepage with clearer care-navigation shortcuts.
- Third-party autoplay hero media removed from the landing page.
- Homepage and AI copy use explicit truth boundaries rather than implying live integrations.
- AI page exposes response layer, route, approved-context count (when present) and safety notice.
- Legacy guided tools are labeled as deterministic helpers instead of appearing to be separate AI models.

### AI, agent and tool governance

- Deterministic safety is the non-optional first boundary for emergency/high-risk guidance.
- Model routing supports governed deterministic/local/configured-cloud paths with privacy/risk policy.
- Owner intelligence now exposes metadata-only AI runtime status without causing an external provider health call.
- Owner intelligence exposes registered-tool risk classes, approval-gated tools and critically blocked actions.
- Autonomous prescribing and emergency dispatch remain blocked tool classes.
- Configured model/provider settings are not reported as externally reachable without a separate health verification.
- The model/tool execution boundary is explicit: model output proposes; server policy decides.

### Healthcare workflows

- Health memory, records, timeline and vitals are protected by application authorization boundaries.
- Provider onboarding supports evidence review and does not auto-verify self-entered provider data.
- Appointment/provider scheduling uses ZENDOC-owned durable workflow state; external confirmation is not invented.
- Pharmacy, diagnostics, medical transport, home health and fulfilment workflows preserve request/status truth.
- Diagnostic report linking includes completion notification/provenance and concurrency-safe linking on the current main baseline.
- Real pharmacy stock/price/dispensing/delivery, ambulance dispatch and home-health staffing remain external integration concerns unless a connected provider confirms them.

### Data, geography and partner systems

- Public/official ingestion supports controlled dry-run/apply, provenance, checksums, validation/rejection and idempotent update behavior.
- India geography/health-graph infrastructure is separated from actual verified record coverage.
- Business/partner API v1 includes API-key/rate-limit/audit/handoff boundaries; partner-side execution remains external.
- Pilot/startup analytics are derived from stored ZENDOC records and must not be converted into fabricated traction/savings claims.

## Security and integrity verification

The repository Production Gate is the release authority. A branch intended for merge must pass the current jobs configured in `.github/workflows/ci.yml`, including the security/safety gate, SQLite suite, PostgreSQL readiness/migration checks and release gate.

Specific regression areas maintained in the current suite include:

- owner-only intelligence/runtime access;
- role and IDOR isolation;
- emergency/safety precedence;
- model-to-tool separation and critical tool blocking;
- diagnostic completion/report-link integrity;
- provider/data provenance truth;
- stale integration-claim prevention in the legacy AI helper;
- patient UI labeling of deterministic helper tools.

Do **not** copy a historical test count into presentations as a permanent number. Use the latest successful workflow run for the release commit.

## Infrastructure truth

- SQLite is supported for local/test application persistence.
- PostgreSQL status is environment-dependent and is only `WORKING` when configuration and the documented persistence verification are both satisfied; otherwise it remains `BETA` or `INTEGRATION_REQUIRED` according to the runtime registry.
- Local record storage can be working for a single deployment boundary without implying production-grade shared object storage.
- Multi-region HA/DR, real external messaging delivery, live provider logistics, payment/insurance authorization and other third-party infrastructure are not created by the application alone.
- A green pull-request gate does not prove the public Render deployment is healthy. Deployment health must be checked separately after merge/deployment.

## Release verdict rule

A commit may be called **repository release-ready** only when its current Production Gate is green and there are no known unreviewed P0/P1 safety/security regressions in the completion scope.

A deployment may be called **production healthy** only after the deployed revision is identified and the public health/application checks succeed. Until that verification exists, the truthful statement is **repository validated; deployment health not yet verified**.
