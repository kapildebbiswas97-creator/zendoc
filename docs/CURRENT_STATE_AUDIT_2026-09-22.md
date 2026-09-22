# ZENDOC current state audit — 22 September 2026

This is an evidence snapshot for the stabilization work that started from `main`. It records the repository shape and the release evidence available at audit time. Runtime capability truth remains owned by [`zendoc/capability_registry.py`](../zendoc/capability_registry.py) and [`FEATURE_TRUTH_MATRIX.md`](FEATURE_TRUTH_MATRIX.md).

## Baseline and release evidence

| Item | Evidence |
| --- | --- |
| Audited branch | `main` |
| Audited commit | `af0c1838dfd2b5760ef1e938b8221375175f418a` |
| Main production gate | Green on the latest recorded run; 1,158 tests passed, PostgreSQL readiness and static security jobs passed, and the deployed Render revision was verified. |
| Open search work | PR [#88](https://github.com/kapildebbiswas97-creator/zendoc/pull/88), healthcare-search resilience; its recorded suite passed 1,169 tests. Review before duplicating those changes. |
| Unmerged product work | `product/launch-ai-ux-20260922` at `14ba16ea7cbac3ce4327fabf4f25a3116a0aa702`, 17 commits ahead of `main`; it contains Copilot and launch UI work plus the PR #88 search changes. |
| Governance observation | `main` is not protected and no repository ruleset was reported by the audit. This requires repository-owner policy work before treating branch protection as a release control. |

The GitHub Actions workflow has a release-status correctness issue addressed in this stabilization change: pull-request runs execute against a synthetic merge ref, so the aggregate `ZENDOC Production Gate` status must be written to `github.event.pull_request.head.sha`. Push and manual runs continue to use their triggering SHA. The focused regression is in [`tests/test_release_gate_v1.py`](../tests/test_release_gate_v1.py).

## Measured repository map

The following counts were generated from the audited checkout rather than inferred from documentation:

| Area | Count / location | What it represents |
| --- | --- | --- |
| Python modules | 233 files in `zendoc/` | Domain services, route handlers, persistence, integrations, safety, AI and operations. |
| Route modules | 43 files ending in `routes.py` | HTTP/API boundary modules. |
| Registered blueprints | 47 calls in [`zendoc/__init__.py`](../zendoc/__init__.py) | Product surfaces installed into the Flask application. |
| Route declarations | 497 decorator matches across `zendoc/` | Web and API endpoints; authorization still needs workflow-level coverage. |
| Database tables | 147 `CREATE TABLE IF NOT EXISTS` declarations | Core schema plus additive domain schemas. Startup applies these through [`zendoc/__init__.py`](../zendoc/__init__.py). |
| Templates | 103 files under `templates/` | Web UI surfaces and shared components. |
| Static assets | 22 files under `static/` | CSS, JavaScript, icons and service-worker assets. |
| Test files | 204 Python files under `tests/` | Regression and feature coverage; the production gate selects critical subsets and the full suite. |

The app factory registers the main route, health/memory, care continuity, business, knowledge, fitness, family, ecosystem, identity, integration, shop, social, mental wellness, payment, pharmacy, fulfilment, milestone, connected-care, geography, ingestion, provider, launch, search, CareFin, Care Journey, nutrition, organization, language, specialist-agent and system-intelligence blueprints. Initialization creates the base database and invokes additive schema installers before checking the readiness report.

## Feature and test matrix

| Capability | Source boundary | Evidence in tests/docs | Current state |
| --- | --- | --- | --- |
| Authentication and sessions | `zendoc/auth.py`, `zendoc/routes.py`, `zendoc/account_lifecycle.py` | `test_auth_diagnosis_p0.py`, `test_auth_rate_limit_v1.py`, `test_email_verification_v1.py`, `test_login_dashboard_roles_v1.py` | Working boundary; keep regression coverage on role and session transitions. |
| Authorization, consent and tenancy | `zendoc/health_access.py`, `zendoc/family_care.py`, `zendoc/communication_policy.py`, provider organization services | `test_security_hardening_v3.py`, `test_provider_permission_matrix_v1.py`, `test_provider_tenancy_v1.py`, `test_provider_resource_tenancy_v1.py`, `test_careloop_consent_scope_boundary.py` | Working boundary; every new cross-user workflow must add an access test. |
| Health Memory and longitudinal graph | `zendoc/health_routes.py`, `health_timeline.py`, `health_memory_continuity.py`, `care_graph.py` | `test_health_hub_v1.py`, `test_health_memory_rag_v1.py`, `test_care_continuity_v1.py`, `test_health_knowledge_api_v1.py` | Working for stored/provenance-aware records; external verification remains explicit. |
| AI and Agent OS | `zendoc/orchestrator.py`, `agent_*`, `tool_registry.py`, `model_router.py`, `capability_registry.py` | `test_agent_autonomy_v1.py`, `test_agent_fleet.py`, `test_agent_specialists_v1.py`, `test_legacy_ai_truth_v1.py`, `test_model_portfolio.py` | Working advisory orchestration; deterministic safety and server-side tools govern sensitive actions. |
| Universal search and finder | `zendoc/universal_search.py`, `universal_health_search.py`, `healthcare_finder.py`, `places_provider.py` | `test_universal_health_search_v1.py`, `test_finder_*`, `test_places_fallback_v1.py` | Working with recorded/local data; live provider results remain configuration and reachability dependent. |
| CareLoop and appointments | `zendoc/careloop_integration.py`, `care_chain.py`, `appointment_continuity.py`, `connected_care_routes.py` | `test_careloop_*`, `test_care_chain*`, `test_submission_care_flow_v1.py`, `test_workflow_state_integrity_v1.py` | Working ZENDOC-owned workflow; external booking requires connected confirmation. |
| Communication and calling | `zendoc/connect.py`, `call_routes.py`, `call_signaling.py`, `telehealth.py` | `test_patient_messaging_and_feature_visibility_v1.py`, `test_telehealth_truth_v1.py`, `test_discovery_video_v2.py` | Messaging working; WebRTC and telehealth remain beta until real network/provider verification. |
| Mental wellness | `zendoc/mental_wellness.py`, `mental_wellness_routes.py` | `test_product_restoration_v1.py`, `test_competition_identity_wellness_visibility_v1.py` | Private self-entered wellness workflow; safety escalation must stay explicit and non-diagnostic. |
| Pharmacy and diagnostics | `pharmacy_service.py`, `pharmacy_order_routes.py`, `diagnostic_service.py` | `test_pharmacy_truth_v1.py`, `test_pharmacy_pilot_workflow_v1.py`, `test_diagnostics_v2.py`, `test_careloop_pharmacy_integration.py` | Request/catalog workflows work; stock, dispensing, delivery and booking require authoritative partners. |
| Marketplace and payments | `health_shop.py`, `marketplace.py`, `payments.py`, `payment_routes.py` | `test_health_social_commerce_payments_v1.py`, `test_production_integrations.py`, `test_public_catalog_truth_v1.py` | Discovery and evidence-first payment state work; no frontend callback is payment proof. |
| Provider, B2B and operations | `provider_network.py`, `organization_service.py`, `business_api.py`, `human_operations.py` | `test_b2b_operations_v1.py`, `test_business_api_v1.py`, `test_provider_operations_v1.py`, `test_operational_fulfilment_release.py` | ZENDOC-owned operations and APIs work; partner-side execution remains external. |
| Admin, observability and release | `observability.py`, `database_reliability.py`, `release_health_routes.py`, `.github/workflows/ci.yml` | `test_release_gate_v1.py`, `test_database_reliability_v1.py`, `test_observability_incident_v1.py`, `test_render_readiness_v1.py` | Release gate is defined; deployment and branch governance remain environment controls. |

## External dependency register

These features are prepared in software but cannot be truthfully marked connected without the corresponding operator evidence:

| Dependency | Runtime boundary | Required evidence |
| --- | --- | --- |
| Managed PostgreSQL | `DATABASE_URL`, persistence attestation | Configured database plus operator redeploy/persistence verification. |
| Map/Places search | `ZENDOC_PLACES_PROVIDER` and provider key | Reachable provider response and provenance. |
| Cloud/local AI | model router and provider adapters | Configured model plus runtime health verification; no key alone proves reachability. |
| Email/SMS/WhatsApp/push | notification providers | Configured provider, delivery response and safe retry state. |
| WebRTC public calling | ICE/STUN/TURN configuration | Two-device network verification; browser signaling alone is insufficient. |
| Pharmacy, diagnostics, logistics, home health and transport | request/handoff services | Authoritative partner confirmation for inventory, availability, fulfilment or dispatch. |
| Payments | payment intent, webhook and receipt state | Signed gateway verification and idempotent server-side state transition. |
| Object storage | community/media storage | Configured S3-compatible provider plus operator durability verification. |
| Government, insurer, eKYC and ABDM services | source/partner connectors | Authorized credentials, source response and provenance/consent record. |

## Next safe milestones

1. Land and verify the pull-request status fix in CI.
2. Review `product/launch-ai-ux-20260922` and PR #88 by diff, then integrate only tested, non-duplicative changes through a small PR.
3. Run the full release gate and record the exact commit and deployment verification after each merge.
4. Add regression tests for any P0 authorization or truth-boundary defect found in workflow review.
5. Enable repository branch protection and required checks as an owner-controlled governance change.

