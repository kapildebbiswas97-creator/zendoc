# ZENDOC Partner API Specification

**Branch:** `post-submission-production`  
**Audience:** pharmacy, diagnostic/lab, hospital, insurer/benefits, government/public-data, device, logistics, and pilot integration partners.  
**Status:** pilot integration contract. This document defines software boundaries; it does not claim a partner, regulatory approval, production SLA, clinical certification, or live external connectivity.

## 1. Core integration rule

ZENDOC distinguishes software capability from external-world completion.

A ZENDOC object may be `requested`, `staged`, `pending`, `confirmed`, or `completed` only according to the authority that can truthfully establish that state. A partner integration must not convert local intent into external success without a real partner acknowledgement.

Examples:

- a medicine order created by ZENDOC is not proof of pharmacy acceptance;
- an ambulance request is not proof of dispatch;
- a CareFin pathway is not proof of eligibility or payment;
- a diagnostic catalog item is not proof of live availability;
- a public facility directory record is not proof that the provider is connected to ZENDOC;
- an AI recommendation is not clinical authorization.

## 2. Authentication

Pilot APIs use ZENDOC bearer-token authentication unless a future partner-specific credential flow is explicitly added.

```http
Authorization: Bearer <token>
```

Browser/session-backed state changes also require the existing CSRF boundary.

Partners must not place tokens, passwords, patient records, or provider credentials into query strings, analytics tags, log messages, or public issue trackers.

## 3. Authorization and consent

Knowing an identifier does not authorize access.

For patient-linked data:

- self-access is allowed within the endpoint's scope;
- delegated access requires an active matching consent/care grant;
- provider access is purpose/scoped;
- owner/admin access is explicit, owner-bound, and audited;
- cross-patient IDOR attempts are denied.

A partner connector must preserve the authenticated actor and target patient separately and must not trust a client-provided `patient_id` without server-side authorization.

## 4. Provider tenancy

When organization metadata is present, resources are bound to:

- `organization_id`
- `organization_location_id`

A provider who moves branches does not inherit authority over the prior branch's orders, appointments, consultations, inventory observations, or diagnostic offers.

Partner adapters should carry provider organization/location identifiers when available and fail closed when the mapping is ambiguous.

## 5. Truth-state vocabulary

### Inventory

- `CONFIRMED` — fresh provider observation and quantity/availability state is current.
- `STALE` — prior provider observation exists but is older than the freshness threshold.
- `UNKNOWN` — no reliable current observation exists.
- `UNAVAILABLE` — provider explicitly reports unavailable/zero stock.

### Diagnostics

- `CONFIRMED` — verified provider offer is still within the diagnostic freshness window.
- `STALE` — offer exists but must be refreshed before booking.
- `UNKNOWN` — ZENDOC lacks a reliable current offer.
- `OBSERVED` — data exists but is not yet eligible to be represented as confirmed.

### Capability

- `WORKING` — implemented software path.
- `BETA` — implemented but not fully production-validated for the dependency/use case.
- `INTEGRATION_REQUIRED` — partner, credential, infrastructure, approval, or external dependency is missing.
- `FUTURE` — intentionally not implemented/authorized as a current capability.

Partner systems should preserve these distinctions rather than flattening them into a generic `available=true`.

## 6. Pharmacy integration

Current ZENDOC software supports:

- inventory observations;
- pharmacy offer search;
- prescription-aware fulfilment planning;
- explicit user confirmation before order submission;
- provider acknowledgement lifecycle;
- inventory freshness queues;
- explicit provider reconfirmation.

### Inventory write

`POST /api/v1/connected-care/inventory`

The authenticated pharmacy reports a SKU observation. ZENDOC records the provider, tenant context, source, data mode, quantity, price, and observation timestamp.

### Freshness queue

`GET /api/v1/connected-care/provider/inventory-refresh`

Returns only the authenticated pharmacy's observations and flags `needs_refresh`.

### Reconfirm unchanged values

`POST /api/v1/connected-care/provider/inventory/<observation_id>/reconfirm`

```json
{
  "confirmed_unchanged": true
}
```

This call is valid only after the provider actually rechecks the values. It must not be used as a timer-based automatic refresh.

A partner with a real POS/API feed should submit the current values through the normal inventory update path rather than repeatedly using manual reconfirmation.

## 7. Diagnostic/lab integration

Current software supports:

- canonical diagnostic catalog;
- provider offers;
- freshness classification;
- stale-offer booking rejection;
- explicit patient confirmation;
- provider acknowledgement/completion boundaries;
- freshness queue and explicit reconfirmation.

### Offer update

`POST /api/v1/connected-care/diagnostic-offers`

The provider supplies the current test, price, home-collection status, collection fee, and data mode.

### Freshness queue

`GET /api/v1/connected-care/provider/diagnostic-refresh`

### Reconfirm unchanged offer

`POST /api/v1/connected-care/provider/diagnostic-offers/<offer_id>/reconfirm`

```json
{
  "confirmed_unchanged": true
}
```

A stale offer remains non-bookable until a legitimate provider refresh occurs.

## 8. Prescription and medicine safety boundary

ZENDOC does not grant an AI or partner adapter authority to:

- prescribe;
- substitute one medicine for another;
- change strength;
- change dose/frequency/form;
- invent missing prescription directions;
- bypass ambiguous extraction/review states.

Partner pharmacy systems should consume only exact, authorized prescription fields and should return provider-side exceptions explicitly.

## 9. Diagnostic booking boundary

A valid request requires:

- authenticated and authorized patient context;
- exact `test_id`;
- verified provider-backed offer;
- fresh/confirmed availability;
- explicit `user_confirmed=true`;
- future scheduled date;
- concrete collection address;
- valid collection mode.

ZENDOC intentionally does not invent a default provider slot.

## 10. Provider onboarding

Provider-facing:

- `GET /api/v1/provider/onboarding`
- `POST /api/v1/provider/evidence`

Owner review:

- `GET /api/v1/admin/provider-evidence`
- `POST /api/v1/admin/provider-evidence/<evidence_id>/review`

Verification evidence status and provider profile verification are separate. Integrators must not assume that one reviewed document means the provider is operationally approved or connected.

## 11. CareFin and benefits integrations

`POST /api/v1/carefin/discover`

CareFin may surface possible government, insurance, CSR, trust, NGO, or employer support pathways.

Without an authoritative connector, ZENDOC does not claim:

- beneficiary eligibility;
- policy coverage;
- pre-authorization;
- claim acceptance;
- benefit approval;
- payment.

A future insurer/government connector must include authoritative reference IDs and source timestamps before advancing to confirmed approval/payment states.

## 12. Care Journey integrations

- `POST /api/v1/care-journeys`
- `GET /api/v1/care-journeys`
- `GET /api/v1/care-journeys/<journey_id>`
- `POST /api/v1/care-journeys/<journey_id>/transition`

Care Journey is an orchestration state machine, not a clinical decision engine. Partner-triggered transitions must still satisfy actor, consent, and human-gate requirements.

## 13. Official/public data ingestion

Owner-only ingestion:

- source registry;
- adapt;
- preview;
- apply;
- batch history;
- data-gap registry.

Rules:

- dry-run/preview before apply;
- retain source and freshness;
- row-level rejection reasons;
- duplicate/checksum protection;
- no patient/beneficiary/claims ingestion through the public-directory pipeline;
- imported facilities do not automatically become ZENDOC-verified;
- imported facilities do not automatically become bookable.

## 14. LIVE vs DEMO

Partner connectors must specify or preserve the active data mode.

ZENDOC does not silently mix `LIVE` and `DEMO` inventory or diagnostic data.

Production integrations should reject ambiguous mode configuration instead of falling back to synthetic data.

## 15. Idempotency and retry guidance

Safe patterns:

- retry GET/read requests;
- use endpoint-specific idempotency/fingerprint behavior when provided;
- treat timeouts after consequential writes as unknown until the object is re-read.

Do not blindly retry:

- order confirmation;
- evidence submission;
- care-journey transition;
- provider acknowledgement;
- other state-changing requests without documented replay protection.

## 16. Logging and privacy

Partner integrations should log metadata needed for operations, such as:

- request/correlation ID;
- endpoint/action;
- actor/provider identifier;
- non-sensitive object identifier;
- status;
- duration;
- partner response code.

Do not log raw:

- patient messages;
- medical reports;
- prescription text;
- full addresses;
- tokens/secrets;
- hidden model prompts/responses;
- unnecessary PHI/PII.

## 17. Error handling

Integrators should expect semantic failures, not only transport failures.

Typical categories:

- `401` unauthenticated;
- `403` unauthorized/consent/tenant failure;
- `404` referenced authorized resource not found;
- `400` invalid or incomplete request;
- `409` invalid lifecycle transition/conflict where used;
- `503` external integration unavailable where the feature is intentionally integration-required.

A partner adapter should expose a truthful degraded state instead of synthesizing success.

## 18. Pilot integration checklist

Before declaring a partner integration live:

1. authenticate with non-demo credentials;
2. verify tenant/provider mapping;
3. verify patient-consent flow where patient data is involved;
4. test cross-user and cross-branch denial;
5. test timeout/retry behavior;
6. verify status mapping and freshness semantics;
7. verify LIVE/DEMO isolation;
8. verify audit/correlation metadata;
9. verify no secrets/PHI leak into logs;
10. perform a real acknowledgement round trip;
11. perform restart/redeploy verification where persistence is relevant;
12. record the external system owner, support contact, and rollback procedure.

## 19. Integration-specific prerequisites

### Pharmacy/POS
Requires a real pharmacy/dispensing partner and their inventory/order interface.

### Diagnostic provider
Requires real provider availability and booking/completion feed.

### Hospital
Requires provider onboarding plus approved scheduling/record-exchange integration.

### ABDM/ABHA/HFR
Requires authorized onboarding/access. ZENDOC does not claim production access by default.

### Insurance/government benefits
Requires authoritative eligibility/coverage/claims APIs or approved workflows.

### Ambulance/home healthcare
Requires real dispatch/workforce partners. ZENDOC's current intake software is not a live dispatch network.

### IoT/medical device
Requires vendor SDK/API, device identity, provenance mapping, and safety review.

## 20. Compatibility policy

Current partner endpoints are versioned under `/api/v1`. Breaking contract changes should be introduced under a new API version rather than silently changing v1 semantics.

Additive fields may appear in v1 responses. Partner clients should ignore unknown fields and depend only on documented stable meanings.
