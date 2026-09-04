# ZENDOC Milestone 11: Trust-First Intelligence & Healthcare Orchestration

## 1. Executive Summary

Building on the verified foundation of Milestone 10 (which established the Connected Care ecosystem, minimum privacy context bundles, hyperlocal inventory truth states, and order confirmation guards), Milestone 11 delivers **Trust-First Intelligence & Healthcare Orchestration**.

Milestone 11 introduces a central, deterministic orchestrator (`zendoc/orchestrator.py`) that coordinates all underlying domain capabilities into structured, multi-step healthcare workflows while strictly preserving patient safety, authorization boundaries, and clinical truthfulness:
- **Emergency Safety Always First**: Acute clinical red flags immediately halt standard workflows and route to 108 ambulance guidance.
- **Subject Resolution & Granular Family Authorization**: Automatically distinguishes self vs family care requests (`mother`, `father`, etc.) and enforces active, task-scoped consent grants before accessing records.
- **Friction Minimization**: Auto-resolves saved addresses (e.g., `parent_home`) and active verified prescriptions to eliminate tedious re-entry.
- **Consequential Action Gating**: AI stages and prepares quotes, but autonomous execution is impossible; orders halt at `AWAITING_CONFIRMATION` and require explicit user confirmation (`user_confirmed=True`) bound to an immutable cryptographic snapshot (`plan_hash`).
- **Care Graph Continuity**: Confirmed actions automatically record provenance-bearing continuity events to the patient's Care Graph.
- **Trust Center**: A dedicated UI and API (`/connected-care/trust-center`) providing transparent data provenance inspection, active consent management, and instant revocation.
- **Inbox 2.0**: Enhanced dashboard prioritizing action-required items and surfacing contextual Next Safe Actions.

---

## 2. Architecture & Components

### 2.1 Central Healthcare Orchestrator (`zendoc/orchestrator.py`)

The `HealthcareOrchestrator` implements a phased pipeline:
1. **Safety Triage**: Scans input against `SafetyEngine`. If acute distress or red flags are detected, execution bypasses all commercial and administrative steps, producing an immediate emergency plan with 108 ambulance dispatch instructions.
2. **Subject Resolution**: Delegates to `zendoc/subject_resolver.py` to identify whether the request is for the authenticated actor or a family member. For family care, it checks `family_access_grants` and verifies that the requested scope (e.g., `pharmacy`, `diagnostics`) is actively permitted.
3. **Location & Data Resolution**: Resolves saved parent locations (`parent_home`) or user addresses without repetitive prompts. Fetches the patient's active prescription.
4. **Clinical Safeguards**: If prescribed medications have low extraction confidence or missing catalogue matches (`ITEM_REVIEW_REQUIRED`), the orchestrator blocks autonomous ordering and directs the user to clinical confirmation.
5. **Hyperlocal Search & Staging**: Queries participating verified pharmacies or NABL labs. If no confirmed stock is found, it truthfully reports zero inventory without fabricating providers. When verified stock is available, it stages the plan with an immutable SHA-256 `plan_hash`.
6. **Confirmation Gate**: Consequential steps enter status `AWAITING_CONFIRMATION`. The action preview specifies exact costs, items, delivery location, and participating providers.
7. **Execution & Continuity**: When explicitly confirmed (`user_confirmed=True`), `confirm_and_execute()` validates the plan hash, submits the order, and commits an `ORDER_SUBMITTED` event into `health_timeline_events` in the Care Graph.

### 2.2 Subject Resolver (`zendoc/subject_resolver.py`)

Provides natural language entity resolution for family relationships:
- Resolves terms like "my mother", "my father", "mom", "dad", "parent" to registered family members.
- Validates active caregiver delegation in `family_access_grants`.
- If unauthorized or missing required scopes, returns a structured `BLOCKED_PERMISSION` status with explicit consent request guidance.

### 2.3 Trust Center (`templates/trust_center.html`, `/connected-care/trust-center`)

Surfaces all transparency controls required for healthcare trust:
- **Data Provenance Breakdown**: Inspectable metrics for `USER_REPORTED`, `DOCUMENT_EXTRACTED`, `PROVIDER_RECORDED`, and `DEVICE_RECORDED` records.
- **Active Consents**: Lists every active grant, its authorized scopes, and timestamp.
- **Instant Revocation**: Direct POST API (`/api/v1/connected-care/trust-center/revoke`) and UI action allowing patients to revoke caregiver or provider access with immediate enforcement.
- **Family Delegations**: Manage authorized caregivers and relationship permissions.

### 2.4 Inbox 2.0 (`templates/inbox.html`, `/connected-care/inbox`)

Upgraded care coordination inbox:
- Highlights **Action Required** alerts for pending prescription reviews and unconfirmed staged orders.
- Dynamic **Next Safe Actions** suggestions based on current patient care state (e.g., track order, upload prescription, consult doctor).
- Quick link to the Trust Center for consent inspection.

---

## 3. Test Verification & Invariants Suite

The Milestone 11 test suite (`tests/test_milestone11_orchestration.py`) exercises 10 comprehensive end-to-end scenarios:
1. `test_emergency_red_flag_bypasses_orchestration_to_immediate_safety`: Acute chest pain red flag immediately yields emergency triage and halts commercial orchestration.
2. `test_subject_resolution_self_vs_family_unauthorized`: Family request without grant is blocked with clear consent request instructions.
3. `test_subject_resolution_family_authorized_permitted`: Active caregiver grant permits family care orchestration.
4. `test_frictionless_saved_location_auto_resolution`: Auto-resolves saved parent home location (`parent_home`).
5. `test_signature_scenario_family_medicine_fulfilment_with_confirmation`: Full signature journey: son orchestrates mother's prescription fulfilment, auto-resolves location and active Rx, stages verified stock, halts at `AWAITING_CONFIRMATION`, enforces user confirmation, submits order, and verifies Care Graph event recording.
6. `test_truthful_zero_inventory_orchestration_response`: Truthfully reports zero inventory without fabricating providers or estimates.
7. `test_clinical_uncertainty_guard_blocks_unreviewed_extraction`: Low-confidence extracted prescription items block staging until human review.
8. `test_trust_center_api_and_consent_revocation`: Verifies Trust Center API and instant consent revocation.
9. `test_inbox_2_action_required_and_next_safe_actions`: Inbox 2.0 accurately surfaces priority action-required items.
10. `test_intelligence_respond_routes_orchestration`: Integration with `ZendocIntelligence.respond()`.

### Test Results
- **Milestone 11 Suite**: 10 passed, 0 failed
- **Full Repository Suite**: 229 passed, 0 failed
- **Baseline Regression**: 100% clean (all 219 baseline M1–M10 tests remain green)
