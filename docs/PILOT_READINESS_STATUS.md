# ZENDOC Pilot Readiness — Official Data, Provider Onboarding & Pilot Analytics

**Branch:** `post-submission-production`  
**Stage:** Pilot Readiness v1

## Goal

Move ZENDOC from architecture-complete prototype toward a truthful pilot system without purchasing inventory, fleets, facilities, or regulated partner access before it is needed.

## 1. Official/public data ingestion

### Source registry

ZENDOC currently models these official/public sources:

- **LGD — Local Government Directory**
  - use: country/state/district/sub-district/block/local-body/village hierarchy
  - trust: official public administrative data
  - live status: manual download or configured connector required
  - no personal data

- **Open Government Data Platform India — public hospital directory**
  - use: public healthcare facility discovery
  - trust: official public directory
  - live status: dataset-specific API/download required
  - imported records remain `not_verified` by ZENDOC and `not_connected` for booking
  - source freshness must be retained; a directory record is not live availability

- **ABDM Health Facility Registry (HFR)**
  - use: future authoritative health-facility registry integration
  - trust: authoritative registry boundary
  - live status: onboarding / authorized access required
  - ZENDOC does not claim live HFR API access without verified integration

### Ingestion pipeline

Owner-only workflow:

1. inspect source registry
2. adapt CSV/JSON through explicit canonical field mapping
3. preview/dry-run
4. inspect accepted/rejected rows
5. explicitly apply with `apply=true`
6. persist checksum-addressed batch audit
7. upsert canonical records
8. expose imported data with its original source/trust/freshness state

Safety rules:
- dry-run is default
- max bounded batch size
- row-level rejection reasons
- duplicate batch checksum detection
- no patient/beneficiary/claims ingestion
- no imported public provider becomes ZENDOC-verified automatically
- no public directory record becomes bookable automatically

## 2. Healthcare Finder source tiers

Finder now returns three separate source groups:

1. **ZENDOC verified provider network**
   - verified inside ZENDOC
   - connected capabilities depend on provider workflow

2. **Official/public directory**
   - government/official public metadata
   - not automatically ZENDOC-verified
   - not automatically bookable
   - source freshness shown/stored separately

3. **External place discovery**
   - external unverified location discovery
   - no implied license/credential verification
   - no implied availability, stock or ZENDOC connectivity

## 3. Provider onboarding v1

Provider accounts now have:
- public profile completeness scoring
- required-field checklist
- active schedule status
- official evidence submission
- evidence history
- owner review:
  - pending
  - verified
  - rejected
- verification readiness state
- onboarding event audit trail

A provider may be **verification-ready** without being verified.

Owner evidence review does **not** automatically change `provider_profiles.verification_status`.

Provider verification and partner connectivity remain separate concepts.

## 4. Patient pilot surfaces

### CareFin
Browser workflow supports:
- state/district
- age
- occupation
- income band
- existing insurer
- charitable/CSR support need
- possible support pathways
- missing information
- evidence requirements
- official-source link
- explicit not-yet-verified status

It does not:
- claim eligibility
- submit applications
- approve coverage
- claim insurer/government payment

### Automatic Care Journey
Browser workflow supports:
- starting durable care coordination
- current state
- next safe action
- transition history
- patient-safe valid transitions
- required actor/consent visibility
- blocked state visibility

The patient UI deliberately does not expose internal transitions that require missing human-gate metadata.

## 5. Diagnostic route hardening

The Connected Care diagnostic booking endpoint now requires:
- explicit `user_confirmed=true`
- exact `test_id`
- verified-offer `lab_id`
- concrete future scheduled date
- concrete collection address
- no invented default slot

The service still blocks stale diagnostic offers.

## 6. Pilot analytics

Owner-only scorecard is computed from persisted ZENDOC records.

Metrics include:

### Provider funnel
- total profiles
- pending / verified / rejected / suspended
- evidence submission
- verified evidence
- active schedules
- verified rate

### Care Journey
- total
- active
- completed
- blocked
- transitions
- completion rate
- state distribution

### CareFin
- discovery runs
- unique users

Personal authoritative coverage confirmations and confirmed savings remain unavailable until an authoritative partner workflow exists. They are not estimated.

### Fulfilment
- staged plans
- user-confirmed plans
- orders submitted
- provider acknowledgements
- delivered orders
- conversion rates
- real acknowledgement duration when timestamps exist

### Diagnostics
- provider offers
- bookings
- completions
- report links

### Data coverage
- geography nodes
- official/public healthcare entities
- completed ingestion batches
- entities by source

### Operations
- agent tasks
- failed tasks
- waiting human/approval
- active alerts
- consultation progression

Zero-denominator rates return `null`, not invented percentages.

## 7. Still integration/partner required

This stage does **not** claim:
- live LGD automated synchronization
- live OGD automated synchronization
- live ABDM HFR lookup
- ABDM production keys
- PM-JAY beneficiary/claims data
- Swasthya Sathi patient-level entitlement
- insurer/LIC policy/claims
- hospital external booking
- pharmacy live stock feeds
- diagnostic provider live feeds
- ambulance dispatch
- production payments

## 8. Recommended next pilot work

1. ingest a small verified administrative geography slice for the pilot region
2. ingest a small official/public facility directory slice with freshness metadata
3. onboard 5–20 real providers through the evidence workflow
4. verify provider records manually before public ZENDOC verification
5. run patient CareFin/Care Journey usability tests
6. monitor pilot scorecard weekly
7. prepare ABDM/HFR integration requirements and security checklist
8. measure provider response time and patient completion funnels before spending on physical operations
