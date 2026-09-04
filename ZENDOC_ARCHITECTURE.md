# ZENDOC System Map

**Product standard review:** 4 September 2026  
**Implementation reviewed:** Interactive synthetic family prescription-to-pharmacy prototype  
**Evidence baseline:** No previous master prompt, source repository, production services, or live integrations were supplied. This document therefore distinguishes implemented prototype behavior from proposed production architecture.

## Executive decision

The highest-value first slice is not 45 disconnected features. It is one complete, safety-bounded journey built from three integrated systems:

1. **Consent-Aware Care Context** — determines who is acting, for whom, for what purpose, and returns only the minimum authorized context with provenance.
2. **Controlled Health Action Protocol** — turns an objective into typed, reviewable steps; requires explicit approval for consequential action; verifies execution before reporting success.
3. **Family Prescription Fulfilment Loop** — connects an authorized prescription to exact-item inventory, explainable complete/split options, confirmation, tracking, audit, and a safe follow-up.

The recommended production shape is a **modular monolith backed by one relational database**, with strict module APIs, a transactional outbox, background workers, and provider adapters. A graph database and microservices are not justified for the first pilot.

## Capability audit after this implementation

| Capability group | Status | Evidence and next requirement |
|---|---|---|
| Synthetic family prescription journey | **EXISTS** | Interactive compare → plan review → explicit confirmation → provider acknowledgement → delivery → memory-event demonstration. |
| Synthetic/live separation and labelling | **EXISTS** | Persistent demo banner, synthetic references, no payment, no external submission, and isolated in-browser state. Production still needs environment-level enforcement. |
| Mobile patient simplicity | **EXISTS** | Responsive single-task surface, one dominant action at each consequential step, mobile navigation. |
| Consent and minimum-necessary context | **PARTIAL** | Context inclusions/exclusions, consent scopes, revocation, and blocked state are demonstrated. Server-enforced authorization, expiry, and revocation propagation remain missing. |
| Provenance and chat/health-fact separation | **PARTIAL** | Prescription items show document/provider provenance and confidence; completion records a logistics event only. Durable provenance storage remains missing. |
| Health Action Protocol and approval binding | **PARTIAL** | Immutable-plan language, confirmation gate, recheck state, and verified acknowledgement are demonstrated. Production needs plan hashes, idempotency keys, policy decisions, and append-only audit. |
| Availability freshness and explainable ranking | **PARTIAL** | CONFIRMED and STALE states, timestamp freshness, named strategies, considered/not-considered factors, and complete/split options are visible. Live provider adapters remain missing. |
| Journey state, universal status, closed loop | **PARTIAL** | Compare, confirm, track, complete, record, and reminder states are connected in the prototype. Durable event processing and notifications remain missing. |
| Healthcare inbox and Next Safe Action | **PARTIAL** | Unified summary and non-clinical next actions are present. Cross-service aggregation is not implemented. |
| AI/agent action surface | **PARTIAL** | Page registers a read tool and a safe staging tool when WebMCP is available. The staging tool cannot submit or bypass confirmation. Model, policy, and tool services remain missing. |
| Care Graph / Health Memory backend | **MISSING** | Requires relational entities, provenance-bearing facts, authorization, and audited writes. |
| Pharmacy inventory, orders, and provider portal | **MISSING** | Requires real provider participation, manual/CSV update paths, reservations, restrictions, and acknowledgement adapters. |
| Authentication, payments, notifications, analytics | **MISSING** | No production identity, payment, messaging, telemetry, or patient-level persistence exists. |
| Doctors, diagnostics, home care, transport adapters | **FUTURE** | Reuse the same context, action, availability, journey, and status contracts after the pharmacy pilot is proven. |
| Health Wallet, emergency card, scoped QR | **FUTURE** | Build only after identity, consent, revocation, token expiry, audit, and incident handling mature. |
| Locality launch, liquidity, and care-access analytics | **FUTURE** | Capture de-identified operational events first; build dashboards after real pilot volume exists. |
| FHIR or other interoperability claims | **FUTURE** | Keep clean adapter seams; evaluate and review separately. Similar field names are not compliance. |
| Autonomous medicine, opaque medical quality scores, unsupported treatment plans, raw records in public QR, fake live inventory | **NOT JUSTIFIED** | These conflict with the safety and trust standard. |

## ZENDOC system map

```text
UNTRUSTED USER DEVICE
┌─────────────────────────────────────────────────────────────────────┐
│ PATIENT EXPERIENCE                                                  │
│ Objective · Family selector · Review · Confirm · Inbox · Status     │
└─────────────────────────────────────────────────────────────────────┘
                               │ authenticated actor + subject + purpose
════════════════════ TB1: IDENTITY / DELEGATION ══════════════════════
  A family relationship is descriptive. It never grants data access.
                               ▼
TRUSTED ZENDOC CONTROL PLANE
┌────────────────────────────┐       ┌───────────────────────────────┐
│ ACTION / APPROVAL          │◀─────▶│ SAFETY LAYER                  │
│ typed plan and steps       │       │ policy, scope, restrictions   │
│ immutable approval record  │       │ escalation and fallback       │
└────────────────────────────┘       └───────────────────────────────┘
               │ ContextRequest(actor, patient, purpose, action, fields)
               ▼
┌────────────────────────────┐       ┌───────────────────────────────┐
│ HEALTH CONTEXT             │──────▶│ HEALTH MEMORY / CARE GRAPH    │
│ authorization + consent    │       │ relational events and facts   │
│ minimum necessary bundle   │       │ artifacts + provenance        │
└────────────────────────────┘       └───────────────────────────────┘
               │ minimized, provenance-tagged context only
════════════════════ TB2: NONDETERMINISTIC AI ════════════════════════
               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ AI / SLM LAYER                                                      │
│ intent candidate · extraction candidate · plan or summary draft    │
│ NO direct database writes · NO provider calls · NO final authority │
└─────────────────────────────────────────────────────────────────────┘
               │ typed proposal + confidence + unresolved fields
               ▼
         SAFETY LAYER ──▶ ACTION / APPROVAL
               │ user-approved idempotent execution request
               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PROVIDER NETWORK GATEWAY                                            │
│ adapter contracts · availability normalization · result verification│
└─────────────────────────────────────────────────────────────────────┘
       │              │               │              │              │
       ▼              ▼               ▼              ▼              ▼
 PHARMACY        DOCTORS         DIAGNOSTICS      HOME CARE      TRANSPORT
 pilot first     future          future           future         future
════════════════════ TB3: PROVIDER / EXTERNAL ════════════════════════
 External data is untrusted or stale until normalized.
 CONFIRMED · STALE · UNKNOWN · UNAVAILABLE · INTEGRATION_REQUIRED
 Execution is incomplete until explicit provider acknowledgement.
       │
       ▼
┌───────────────────────────────┐
│ FULFILMENT + RANKING          │
│ exact eligibility first       │
│ complete and split options    │
│ known costs + visible unknowns│
│ named ranking explanations    │
└───────────────────────────────┘
       │
       ├── options ──▶ APPROVAL ──▶ PATIENT EXPERIENCE
       └── verified events
               ├──▶ HEALTH MEMORY (authorized logistics event only)
               ├──▶ HEALTHCARE INBOX / UNIVERSAL STATUS
               ├──▶ NOTIFICATIONS
               ├──▶ APPEND-ONLY AUDIT
               └──▶ NEXT SAFE ACTION

════════════════════ TB4: HEALTH DATA / OPERATIONS ═══════════════════
┌────────────────────────────┐       ┌───────────────────────────────┐
│ DATA / SECURITY            │──────▶│ OPERATIONS                    │
│ encryption · RBAC/ABAC     │       │ aggregate/de-identified only  │
│ consent · revocation · audit│      │ fulfilment + safety funnels   │
└────────────────────────────┘       └───────────────────────────────┘
 Operations cannot read patient-level clinical content by default.

════════════════════ TB5: LIVE / SYNTHETIC ═══════════════════════════
 Demo identities, inventory, credentials, orders, and events must be
 physically/configurationally isolated from all live counterparts.
```

## End-to-end data flow

```text
Objective
  → resolve acting caregiver and patient
  → authorize task-scoped consent
  → build minimum context bundle
  → retrieve one legitimate prescription and provenance
  → show uncertain extraction for review
  → exact-match medicines; never infer substitutions
  → query participating providers
  → normalize availability and freshness
  → apply hard eligibility rules
  → produce named complete/split strategies
  → explain ranking inputs and unknowns
  → snapshot patient + items + provider + address + costs + freshness
  → user confirms that exact plan
  → recheck consent, prescription, quote, restrictions, and inventory
  → submit once with idempotency key
  → require provider acknowledgement
  → track status events
  → record an authorized logistics event
  → offer a user/provider-defined Next Safe Action
```

## Production domain model

### Context and memory

- `actors`, `patients`, `care_relationships`
- `consent_grants` with subject, grantor, grantee, purpose, scopes, resources, validity, expiry, revocation
- `context_requests`, `context_bundles`, and explicit exclusions
- `health_artifacts`, `health_facts`, `provenance_records`
- provenance source: `USER_REPORTED`, `DOCUMENT_EXTRACTED`, `PROVIDER_RECORDED`, `DEVICE_RECORDED`
- verification: `UNVERIFIED`, `USER_CONFIRMED`, `PROVIDER_VERIFIED`

### Orchestration and trust

- `intents`, `action_plans`, `action_steps`, `policy_decisions`
- `approval_snapshots`, `execution_attempts`, `audit_events`
- `journeys`, `journey_transitions`, `status_events`, `notifications`
- plan change or consent expiry invalidates approval
- every external mutation uses an idempotency key and explicit acknowledgement

### Fulfilment

- `prescriptions`, immutable `prescription_items`
- `providers`, `provider_locations`, `provider_capabilities`
- `medication_skus`, `inventory_observations`, `offers`
- `fulfilment_options`, `orders`, `order_items`, `order_events`
- inventory observations carry source, observed time, expiry, quantity/capability evidence, and reason

Every row includes `environment_id` and `data_mode`. Server-side constraints prohibit synthetic/live joins or synthetic requests to live connectors.

## Journey state machine

```text
CREATED
 → SUBJECT_SELECTED
 → CONSENT_VERIFIED
 → PRESCRIPTION_SELECTED
 → ITEMS_VERIFIED
 → SEARCHING
 → OPTIONS_READY
 → OPTION_SELECTED
 → AWAITING_CONFIRMATION
 → SUBMITTING
 → PROVIDER_PENDING
 → CONFIRMED
 → FULFILLING
 → COMPLETED
 → RECORDED
```

Guarded side states: `CONSENT_REQUIRED`, `CONSENT_REVOKED`, `ITEM_REVIEW_REQUIRED`, `NO_CONFIRMED_COMPLETE_OPTION`, `QUOTE_EXPIRED`, `EXTERNAL_UNAVAILABLE`, `SUBMISSION_UNCERTAIN`, `PROVIDER_REJECTED`, `NEEDS_HUMAN`, `CANCELLED`.

## Ranking contract

Hard eligibility runs before ranking: valid prescription, exact medicine/strength/form/quantity, permitted location, provider capability, and confirmed inventory. Stale or unknown inventory cannot be promoted by AI.

Present strategies instead of one opaque score:

- Complete with freshest confirmation
- Lowest known landed total
- Nearest complete pharmacy
- Fewest-provider confirmed split

Unknown fees or ETA are shown as unknown and never treated as zero. Sponsorship is separately labelled and cannot affect medical suitability, eligibility, or rank.

## Clinical boundary

Allowed: authorized retrieval, confidence-aware extraction, exact-match catalog search, logistics comparison, cart preparation, explicit user confirmation, verified execution, tracking, and reminders defined by a user or provider.

Blocked: diagnosis, treatment selection, dose/frequency/duration changes, refill inference, therapeutic substitution, contraindication clearance, prescription creation, adherence inference, or autonomous ordering. Clinical ambiguity escalates to a licensed professional.

## Competitive test

| Workflow | A normal product | ZENDOC differentiation |
|---|---|---|
| Medicine search | Marketplace query | Authorized prescription context + exact matching + freshness + complete/split optimization + explanation |
| Family care | Shared profile | Revocable subject/purpose/resource-scoped consent + minimum context + audit |
| AI assistance | Chat response | Typed proposal + policy gate + immutable user approval + verified execution |
| Order completion | Receipt page | Journey status + inbox event + provenance-bearing memory event + safe follow-up |

The defensible formula is: **AI + authorized context + local availability + controlled action + continuity**.

## Pilot quality gate

Do not call the pharmacy workflow production-ready until it proves all of the following with participating providers:

- no unrelated health context is disclosed;
- uncertain extraction cannot silently pass;
- stale/unknown inventory never appears confirmed;
- no order submits before approval;
- any material plan change requires confirmation again;
- success is reported only after provider acknowledgement;
- failures offer a real next step;
- demo data cannot reach live connectors;
- mobile completion, fulfilment success, response time, and safety events are measurable without storing unnecessary prompt contents.

