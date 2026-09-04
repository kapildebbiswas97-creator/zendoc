# ZENDOC Milestone 10: Connected Care & Truthfulness Architecture

## 1. Executive Summary

Milestone 10 introduces the Connected Care ecosystem to ZENDOC, uniting the Patient Context Engine, Hyperlocal Pharmacy Fulfilment Optimizer, Prescription Safety Guard, Diagnostic Marketplace, and Care Continuity Graph.

Crucially, Milestone 10 hardens ZENDOC against data fabrication and operational hallucination in healthcare workflows:
**NO DATA != POSITIVE DATA.**

---

## 2. Core Architectural Invariants

### 2.1 Truthful Data Boundaries (Live vs. Demo Mode)
- **LIVE MODE (`CONNECTED_CARE_DATA_MODE=LIVE`)**:
  - Operates strictly on verified provider profiles, real inventory observations, and actual quotes.
  - Never fabricates a fallback pharmacy partner, estimated stock, or fictional prices.
  - Missing inventory returns `NO_CONFIRMED_INVENTORY` or `NO_CONFIRMED_OPTION`.
  - Missing coordinates or fees yield `"Distance unavailable"` and `"Price unavailable"`.
  - Stale inventory (`> 24 hours` without fresh observation) is never promoted to confirmed stock.
- **DEMO MODE (`CONNECTED_CARE_DATA_MODE=DEMO`)**:
  - Synthetic demo scenarios are permitted for evaluation and testing.
  - Every UI screen and API payload in Demo Mode prominently displays the banner:
    `SYNTHETIC DEMO ENVIRONMENT — NOT FOR REAL MEDICAL FULFILMENT`.

### 2.2 Clinical Safety & Human Verification Gate
- **Extraction Is Not Prescribing**:
  - AI tools can extract structured medication details from uploaded prescriptions.
  - Any extraction with confidence `< 0.90` or without an exact, unambiguous catalogue match is placed into `ITEM_REVIEW_REQUIRED`.
  - The fulfilment optimizer refuses to stage orders for any prescription with unresolved items.
  - Autonomous prescription creation by AI agents or non-medical actors is blocked.

### 2.3 Consequential Action Gates & Plan Hash Integrity
- **Staging vs. Confirmation**:
  - The fulfilment optimizer only stages quotes into `fulfilment_plans`. It never places orders autonomously.
  - Submitting an order requires explicit user intent (`user_confirmed=True`) and a concrete `delivery_address`.
  - The staged plan is cryptographically signed with a SHA-256 snapshot hash (`plan_hash`) covering item quantities, prices, and participating pharmacy IDs.
  - If catalog prices or provider fees change between staging and confirmation, the order is rejected and requires user review of the updated quote.

### 2.4 Provider Acknowledgement & Real Tracking
- **Provider Autonomy**:
  - When an order is submitted, its status is set to `pending` / `SUBMITTED`.
  - Fulfilment cannot proceed until the assigned provider explicitly acknowledges the order (`acknowledge_order(action="accept")`).
  - Tracking status progresses truthfully through discrete state changes (`SUBMITTED` -> `PREPARING` / `PACKED` -> `OUT_FOR_DELIVERY` / `DISPATCHED` -> `DELIVERED`).

### 2.5 Verified Trust Signals
- **Proof of Interaction Required**:
  - Reviews cannot be submitted without an actual completed interaction (`DELIVERED` pharmacy order or completed diagnostic test).
  - Trust signals accurately reflect verified review rates and real average ratings.

---

## 3. Test Verification & Invariants Suite

All 219 tests across the repository pass with 0 failures:
- `tests/test_milestone10_connected_care.py`: 17 passed
  - Context engine privacy minimization & delegated consent lifecycle.
  - Accurate Haversine distance calculations.
  - Inventory freshness rules & unknown status preservation.
  - Zero-inventory truthfulness: no fake partner pharmacies or phantom stock.
  - Unknown inventory never promoted to confirmed.
  - Missing prices and distances never generate synthetic defaults.
  - Prescription safety guard: autonomous prescription creation blocked.
  - Prescription extraction: low-confidence items gated into `item_review_required`.
  - Fulfilment optimizer staging, plan hash verification, and anti-tamper validation.
  - Order submission requires explicit `user_confirmed=True` flag and concrete delivery address.
  - Order tracking status progression and provider acknowledgement.
  - Diagnostic catalog search & home collection booking.
  - Verified reviews require completed interactions.
  - Connected care web routes & JSON API endpoints.

---

## 4. Integration Disclosure & External Prerequisites

- **Standalone Mode**: In local or standard testing deployments, ZENDOC operates against internal verified SQLite/PostgreSQL provider records.
- **External Integration Required**: Connecting to national healthcare backbones (e.g. ABDM / ABDC), open commerce networks (ONDC), or hospital/pharmacy ERPs requires live credentials and external API gateways. In the absence of live integration credentials, the system truthfully reports `EXTERNAL_UNAVAILABLE` or empty verified results, rather than simulating network responses.
