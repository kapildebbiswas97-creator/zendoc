# ZENDOC — No-Capital Completion Status

**Branch:** `post-submission-production`  
**Checkpoint:** September 2026  
**Scope:** Software and architecture that can be built with founder/development effort before major external funding.

> This document is a product-engineering readiness checkpoint, not a claim that ZENDOC is clinically validated, regulator-approved, commercially partnered, or market-complete.

## Core rule

ZENDOC follows:

**AI thinks → policy decides → permissioned tools act → humans/authorities approve consequential actions → ZENDOC verifies → authorized outcomes enter Health Memory / Care Graph.**

No LLM receives unrestricted shell, SQL, prescribing, emergency-dispatch, payment, coverage-approval, or permission-changing authority.

---

## 1. Completed and tested software capabilities

### Safety, identity, consent and trust
- deterministic emergency safety precedence
- authentication and role isolation
- owner-only administrative boundary
- CSRF/session controls
- family/delegated consent checks
- context authorization/minimization
- audit/event infrastructure
- provider verification states
- capability truth matrix

### Agentic core
- bounded Core Agent planner
- permissioned tool registry
- bounded executor
- persistent agent task engine
- retry/idempotency rules
- human approval gates
- proactive operational alerts
- safe owner-only operations automation
- specialist routing metadata:
  - intent
  - assigned agent
  - risk class
  - privacy class
  - required context
  - tool steps
  - human gate
  - expected output
  - fallback strategy

### Specialized agents connected to real bounded software
- SafetyAgent
- CareFinAgent
- ProviderDiscoveryAgent
- HealthMemoryAgent foundation
- MedicationSafetyAgent
- PharmacyAgent
- DiagnosticsAgent
- DoctorAgent / telehealth coordination
- FamilyCareAgent
- IoTAgent
- NutritionAgent
- OperationsAgent

### CareFin v1
- official/public benefits source registry
- government / insurance / CSR / NGO / trust discovery architecture
- geography-aware candidate ranking
- missing-information detection
- evidence requirements
- verification next steps
- source provenance
- coverage state machine:
  - DISCOVERED
  - POTENTIALLY_ELIGIBLE
  - EVIDENCE_RECEIVED
  - VERIFICATION_REQUIRED
  - CONFIRMED
  - APPROVED
  - PAID
  - REJECTED
  - EXPIRED
- authoritative response/reference required for CONFIRMED / APPROVED / PAID
- uploaded policy evidence cannot impersonate insurer approval
- authenticated CareFin discovery API

### Provider discovery
- ZENDOC verified-provider search
- Google Places API (New) adapter
- external provider source labels
- external results remain EXTERNAL_UNVERIFIED
- external discovery does not imply:
  - verified credentials
  - ZENDOC connectivity
  - live appointment availability
  - emergency readiness
  - pharmacy stock

### Prescription / medication safety
- exact medication identity matching
- extraction confidence
- review-required state
- no automatic medicine substitution
- no automatic dose/frequency/form changes
- standardized Prescription Intelligence v2 stages:
  - EXTRACTED
  - LOW_CONFIDENCE
  - AMBIGUOUS
  - REVIEW_REQUIRED
  - MATCHED
  - VERIFIED
  - FULFILMENT_READY
- MedicationSafetyAgent read-only latest-prescription review
- fulfilment cannot proceed through uncertain medicine identity

### Pharmacy fulfilment
- inventory observation freshness
- UNKNOWN / STALE / CONFIRMED semantics
- fulfilment optimizer
- staged plans and plan hash
- user-confirmation order gate
- provider acknowledgement lifecycle
- no fabricated inventory fallback

### Diagnostics v2
- diagnostic catalog
- aliases
- panel field
- provider offers
- observation timestamps
- CONFIRMED / STALE / UNKNOWN truth states
- unique natural-language test alias matching without guessing
- stale offers remain visible as stale
- stale offers cannot be booked until refreshed
- explicit user confirmation required to request a diagnostic booking

### Automatic Care Journey
- deterministic coordination state machine
- next-safe-action
- blocked reason
- required actor
- required consent
- provenance
- event history
- terminal-state enforcement
- durable care-journey database tables
- authenticated create/read/list/transition APIs
- cross-patient authorization boundary

### Operations automation
- alerts for old approvals
- exhausted retries
- high platform error rate
- stale pharmacy inventory
- stale diagnostic offers
- delayed medicine-order acknowledgement
- delayed consultation response
- safe automation can re-queue only explicitly retriable failures
- safe automation executes zero arbitrary tasks
- no money, permissions, coverage approval, prescribing, emergency dispatch, or destructive data actions

### Nutrition & hydration foundation
- user-supplied label comparison
- normalized price/quantity comparison
- calories/protein/carbohydrate/fat/fibre/sugar/sodium fields
- user-supplied allergen warning
- sponsorship disclosure
- sponsorship cannot affect health-suitability ranking
- disease/therapeutic diet requests escalate to clinician/dietitian
- conservative general hydration guidance
- authenticated nutrition APIs

### Multilingual foundation
- English
- Bengali
- Hindi
- persistent user language preference
- Bengali/Devanagari script detection
- canonical internal structured-language boundary
- emergency / diagnosis / coverage safety templates
- truthful free-form translation status

### Geographic Healthcare Graph v1
- country/state/district/subdivision/block/municipality/panchayat/city/town/village/locality hierarchy
- validated parent relationships
- coordinates
- source/source reference
- verification state
- freshness
- entity links for healthcare ecosystem entities
- search/indexes
- authenticated search
- owner-only ingestion
- production graph starts empty rather than fabricating locations

### AI/model infrastructure
- deterministic safety
- local AI/SLM adapter
- cloud adapter boundary
- model-independent roles
- privacy-aware routing
- structured-output validation
- tool-like model output rejection
- sensitive-health cloud blocking
- model evaluation foundations
- platform remains usable with zero LLM configured

### Engineering reliability
- GitHub Actions CI
- Python compile gate
- full automated test suite on each branch push
- SQLite test compatibility
- PostgreSQL-ready persistence architecture
- environment-backed secrets
- LIVE / DEMO separation

---

## 2. Working software but external integration still required for live capability

The software boundary can be complete while the external service remains unavailable.

- Google Places live data — API key / Google Maps billing-quota configuration
- free-form multilingual translation — configured local multilingual model or provider
- cloud LLM inference — provider credentials/credits
- production email
- SMS / WhatsApp / push
- object storage account/bucket
- production WebRTC / TURN
- device-vendor live sync
- managed PostgreSQL deployment/verification where not yet configured

These must remain **INTEGRATION_REQUIRED** until configured and tested.

---

## 3. Partner / institutional access required

Code cannot truthfully create these capabilities alone:

- ABDM / ABHA production onboarding
- health-record exchange production approval
- PM-JAY beneficiary / claims / pre-authorization data
- Swasthya Sathi patient-level entitlement/claims
- LIC / insurer policy and claims APIs
- insurer coverage/pre-authorization confirmation
- external hospital booking feeds
- real pharmacy stock/dispensing feeds
- real diagnostic availability feeds
- real ambulance dispatch
- home nurse / physiotherapy / home-care fulfilment
- CSR/trust funding acceptance
- employer-benefit verification
- medical-device vendor SDK/API access
- authorized payments/settlement rails

ZENDOC can stage, explain and coordinate these workflows, but must not claim the external action occurred until the responsible organization confirms it.

---

## 4. Regulated activity gates

The platform may build education, orchestration and partner adapters before holding the relevant authority.

Regulated activities still need compliant partner/entity/legal review where applicable, including:
- insurance distribution/comparison
- payment aggregation/payment-system operation
- personalized regulated securities advice/execution
- regulated medical-device/clinical claims
- medicine storage/sale/dispensing operations

---

## 5. Physical/funding-required capabilities

Not part of the no-capital software phase:

- medicine inventory
- compliant pharmacy/medicine warehouse
- refrigeration/cold chain
- racks/scanners/CCTV/fire systems
- owned IoT/medical-device inventory
- delivery fleet
- riders
- ambulances
- diagnostic equipment
- clinical facilities
- large field operations workforce

These should be added only after demand and unit economics justify them.

---

## 6. CI / testing checkpoint

Automated suites cover, among other things:
- emergency precedence
- cloud privacy blocking
- malformed/model-tool output rejection
- CareFin truth states
- CareFin API authorization
- prescription ambiguity/review
- no medicine substitution
- pharmacy stock freshness
- explicit order confirmation
- diagnostics freshness and stale-booking rejection
- family consent isolation
- specialist agent/tool authorization
- safe operations automation
- nutrition sponsorship/allergen safeguards
- multilingual detection/preferences
- geographic hierarchy/provenance
- owner-only intelligence/readiness controls
- durable care-journey authorization/history

GitHub CI is the release gate. A module should not be promoted based only on code being committed.

---

## 7. Owner visibility

The owner intelligence manifest exposes:
- agent fleet
- model roles
- benefits sources
- regulated domains
- capability matrix
- no-capital progress report
- integration dependencies
- partner dependencies
- physical-capital dependencies

The readiness percentage is computed from a named software checklist. Only **WORKING** counts as complete; **BETA** does not. It explicitly does not measure regulatory approval, partnerships, clinical validation, product-market fit, or company completion.

---

## 8. Remaining no-capital engineering opportunities

Recently completed:
- deeper HealthMemoryAgent scoped context orchestration with minimum-necessary context and IDOR/consent tests
- provider-facing pharmacy inventory and diagnostic-offer freshness queues with explicit reconfirmation and branch-tenancy enforcement
- partner-facing v1 API contract and integration specification

The highest-value remaining founder/software work is:

1. richer official-data ingestion connectors for the geographic/benefits graph
2. local multilingual-model adapter/evaluation when a suitable model can run safely on available hardware
3. further synthetic adversarial evaluation for every specialist agent
4. richer reliability/observability dashboards
5. security hardening, dependency scanning and deployment verification
6. pilot instrumentation for retention, provider response time, CareFin verified savings and fulfilment outcomes
7. machine-readable API schema/versioning for future partner SDK generation

---

## 9. Next recommended milestone

**Pilot Readiness & Official Data Ingestion**

Focus on:
- importing verified official/public geographic and benefits metadata with provenance
- provider onboarding workflows
- real Google Places key/runtime verification
- CareFin UI
- durable Care Journey UI
- operational dashboards
- pilot analytics
- partner API specifications
- security/deployment verification

Do not purchase warehouses, inventory, fleets or large teams before pilot demand proves where physical capital improves the economics.
