# ZENDOC — No-Capital Completion Matrix

**Branch:** post-submission-production  
**Purpose:** Separate everything ZENDOC can finish with founder/software effort from capabilities that require external credentials, regulated approval, commercial partners, physical infrastructure, or funding.

## A. Software that can be built without meaningful external capital

### Core platform
- secure auth and role isolation
- owner-only administration
- session security and CSRF
- PostgreSQL-ready persistence layer
- audit logs and provenance
- patient/family consent
- health timeline and Health Memory
- provider profile/schedule/booking workflows
- communication policy and messaging
- Care Graph
- Trust Center
- notification inbox
- universal search

### Agentic AI
- deterministic emergency safety gate
- specialized agent fleet
- bounded planner/executor
- permissioned tool registry
- human approval engine
- idempotent task engine
- model routing by risk/privacy/cost
- local open-weight model adapter
- cloud LLM adapter boundary
- structured-output validation
- synthetic model evaluation
- owner intelligence manifest
- CI regression gate
- metadata-only model observability
- prompt/response privacy controls

### Specialized software agents
- SafetyAgent
- CareFinAgent
- ProviderDiscoveryAgent
- HealthMemoryAgent
- MedicationSafetyAgent
- PharmacyAgent
- DiagnosticsAgent
- DoctorAgent
- FamilyCareAgent
- IoTAgent
- NutritionAgent
- OperationsAgent

### CareFin
- government/insurance/CSR/trust source registry
- geography-aware source filtering
- coverage truth states
- discovery vs evidence vs confirmed distinction
- eligibility-rule framework
- document/checklist generation
- official/partner connector interfaces
- patient-facing explanation logic

### Healthcare discovery
- Google Places adapter implementation
- external-provider truth labels
- ZENDOC provider verification workflow
- specialty/location filtering
- provider source provenance
- booking boundaries

### Pharmacy/diagnostics
- medicine catalog workflows
- prescription extraction review states
- inventory truth model
- fulfilment optimizer
- staged orders
- plan hashes
- explicit-confirmation order gate
- diagnostic offer model
- no-data-is-not-positive-data invariant

### Fitness/nutrition
- workout planning
- session tracking
- hydration/nutrition logs
- general evidence-aware nutrition comparison architecture
- product/claim provenance model
- medical-diet escalation boundaries

### Business/operations
- freemium pricing architecture
- provider SaaS model
- enterprise/government monetization paths
- investor use-of-funds roadmap
- warehouse trigger criteria
- unit economics framework
- staffing model
- pilot KPI framework
- regulated-domain guardrails

## B. Can be implemented in code now, but cannot become truly live without free/paid credentials or onboarding

- Google Places live responses — requires Google Maps API key/billing account
- YouTube/video search — requires provider/API key
- cloud LLM inference — requires provider key/credits
- production email — requires SMTP/email provider
- SMS/WhatsApp/push — requires messaging provider/onboarding
- object storage — requires storage account/bucket
- production WebRTC/TURN — requires signaling/TURN infrastructure
- maps/geocoding beyond configured quotas
- device-vendor APIs — requires vendor credentials/SDK agreements

The correct ZENDOC status is **integration ready**, not "working live", until credentials are configured and tested.

## C. Requires institutional/regulated onboarding even if software is complete

- ABDM production access
- ABHA/health-record exchange production workflows
- PM-JAY beneficiary/claims/pre-authorization access
- Swasthya Sathi patient-level entitlement/claim verification
- insurer policy/claim APIs
- insurance distribution/comparison activities requiring IRDAI-compliant entity/partner
- payment aggregation/payment-system activities requiring RBI/NPCI-compliant partner or authorization
- securities execution/personalized regulated advice requiring SEBI-compliant intermediary/registration
- clinical validation where ZENDOC makes regulated medical-device/clinical claims

## D. Requires commercial partners rather than merely software

- real hospital appointment inventory outside ZENDOC-connected providers
- real pharmacy stock feeds
- real medicine doorstep fulfillment
- real diagnostic slots/pricing
- real home nurse/physiotherapy fulfillment
- real ambulance dispatch
- real insurer pre-authorization
- real employer benefits
- real CSR/trust case funding
- real medical-device distribution/rental
- real payment settlement

## E. Requires physical capital

Do not purchase these until demand triggers justify them:

- medicine inventory
- medical/IoT device inventory
- compliant medicine warehouse
- refrigeration/cold chain
- warehouse racks/scanners/CCTV/fire systems
- delivery fleet
- ambulances
- diagnostic equipment
- clinical facilities
- large operations staff
- regional offices

## F. Automation policy

ZENDOC should automate by default when work is:
- read-only
- reversible
- deterministic
- source-verifiable
- authorized by existing consent
- operationally low risk

ZENDOC must pause for a human when work involves:
- diagnosis or prescribing
- emergency dispatch
- treatment changes
- medicine substitution
- purchase/order confirmation
- insurer/government approval
- financial transfer
- record sharing requiring consent
- regulated advice
- irreversible account/permission changes

## G. Technical moat to build without capital

1. consent-aware longitudinal health context
2. verified provider and geographic graph
3. CareFin coverage/benefits graph
4. agentic workflow state/history
5. provider fulfillment observations
6. provenance and trust scores
7. patient/provider workflow retention
8. model-independent agent platform
9. test/evaluation datasets built from synthetic and legally permitted data
10. integration adapters and partner-facing APIs

The moat is not "one unbeatable LLM." The moat is the combination of trusted healthcare context, verified network data, controlled actions, operational history, integrations, safety governance and user/provider workflows.

## H. Completion definition

The no-capital phase is considered software-complete only when:
- every claimed WORKING feature passes CI
- all external dependencies fail truthfully
- every consequential agent action is gated
- every private-data query enforces authorization
- every specialized agent has a measurable evaluation set
- every integration exposes health/configuration status
- every external source has provenance and freshness metadata
- no demo data can enter LIVE workflows
- production secrets never live in source
- the owner can inspect agents, models, sources and blocked dependencies
