# Healthray competitive parity and ZENDOC hospital-operations roadmap

**Research date:** 2026-10-11  
**Scope:** Independent feature comparison based on Healthray's public *marketing* pages and code-level ZENDOC evidence. This is **not** an audit of Healthray's actual deployed installations, service-level guarantees, regulatory credentials or certifications. Do not reuse Healthray's source, UI assets, data or trademarks in ZENDOC.

## Primary source pages

- Healthray HIMS: https://healthray.com/hospital-information-management-system/
- Healthray clinic: https://healthray.com/clinic-management-software/
- Healthray EMR: https://healthray.com/emr-software/
- Healthray EHR: https://healthray.com/ehr-software/
- Healthray LIMS: https://healthray.com/laboratory-information-management-system/
- Healthray pharmacy: https://healthray.com/pharmacy-management-system/
- Healthray company home: https://healthray.com/

The pages **claim** NHA/ABDM/NABH/HIPAA/etc. Do not claim ZENDOC is similarly approved or certified. External compliance, licensed interoperability, terminology systems and legal verification require separate independent evidence.

## Feature-by-feature parity assessment

Legend:
- **Internal foundation:** ZENDOC has some relevant code and tests but *not* equivalent production functionality
- **Beta:** An actual software route/workflow exists but needs deployment and field verification
- **Gap:** no verified equivalent end-to-end module in the inspected release
- **External:** needs authorized external service, partnership, credentials or regulatory review

| Healthray-offered capability | ZENDOC current evidence / truthful state | Priority and finish line |
| --- | --- | --- |
| Patient registration & unified ID | Accounts, roles, health profile, family, appointments: internal foundation | P0: identity matching, no duplicates, consent-based inter-branch linkage |
| ABHA creation/linking, ABDM | FHIR and ABDM adapter boundary; no live authorized NHA exchange verified | External: authorized ABDM sandbox then production sign-off |
| OPD appointments & scheduling | Provider profiles/schedules/appointments tested | P0: receptionist flow, real token queues, per-clinic display |
| OPD live token queues | No complete field-tested token/doctor queue confirmed | P0: race-safe token counters, no-show, patient notifications |
| IPD admissions, ADT, transfers, discharge | **New private ward-bed board beta** covers operator-attested bed status only | P0: consent-bound ADT, bed reservations, transfers and audited discharge |
| Ward/bed occupancy | Operator-owned internal bed ledger with optimistic versioning, transitions and audit; **not** verified public capacity | P0: two-hospital real-world trial; licensed availability feeds separate |
| Nursing notes, MAR, vitals | Patient timeline and clinician notes exist; full inpatient nursing/MAR unverified | P0/P1: role-scoped eMAR, sign-off, shift handover, exception tracking |
| OT/theatre scheduling, surgical team & implants | No complete integrated OT calendar or implant/consumables ledger | P1: capacity locks, surgeon roles, consumable reconciliation |
| Emergency triage/casualty | Safety escalation, emergency/transport intake; no authoritative live emergency dispatch | P1/External: clinician triage, verified ambulance and hospital intake |
| Specialty EMR templates | Clinician SOAP drafting, prescriptions, care continuum; no 28+ licensed/specialty template parity established | P0: verified specialty templates, clinician sign-off, immutable revisions |
| Longitudinal multi-branch EHR | Health Memory 2.0 and consent; live cross-organization partner exchange missing | P0/P1: verified identity, grants, audit, export; partner-backed only |
| e-Prescription, DDI and reconciliation | Medication intelligence has tested software-level guards | P0: clinician-signed issue, licensed pharmacy dispensing reconciliation |
| Pharmacy POS and GST-ready invoicing | Pharmacy order workflow and financial foundation, not full retail POS/GST accounting | P1: itemized prices, taxes, invoices with legal/tax review |
| Batch, expiry, FEFO, supplier procurement | Inventory observation and medication SKU foundation; no full FEFO stock ledger | P0/P1: batch-level stock movements, lot expiry, controlled write-offs |
| Schedule H/H1/X registers | No evidenced complete compliant restricted-drug register | P1/Regulated: pharmacist review and local legal requirements |
| Pharmacy ward supply & unit doses | Internal medication and care action foundations | P1: signed indents, dispense/return/reconcile, eMAR links |
| Lab orders and sample chain | Diagnostics booking/catalog/freshness, no full LIMS chain | P0: accession numbers, sample timestamps, custody and patient consent |
| Analyzer two-way integration | No supported authorized analyzer link demonstrated | External: device contracts, QC, synthetic-interface testing |
| Critical lab alerts and multi-stage sign-off | Alert/safety foundations; full LIMS reviewer sign-off unverified | P1: technologist/pathologist approval, patient result delivery proof |
| QC/QA charts, Westgard and NABL workflows | No full accredited laboratory QC automation | P1: validated rules and accreditation evidence, never claim automatic certification |
| Radiology RIS/PACS, DICOM worklists | No verified PACS/DICOM patient studies workflow | P1/External: DICOMweb gateway, de-identification and clinician authorization |
| Blood bank, transfusion traceability | No end-to-end licensed blood bank module confirmed | P1/Regulated: controlled blood-component traceability and licensed operators |
| OPD/IPD charges, finance | Payer/financial OS foundations; no complete hospital books or settlement proof | P0/P1: traceable charge ledger, adjustments, audit and reconciliation |
| Insurance/TPA/PMJAY claims | Internal payer workflows; payer/NHA partner verification missing | External: signed decisions, submission, adjudication, rejection/appeal |
| Patient portal / verified results | Patient dashboard and Health Memory exist | P0: signed verified reports only, multilingual accessibility, consent proof |
| Teleconsultation | WebRTC signaling beta, TURN/two-device verification required | Beta: relay, media and access tests across real networks |
| Referral, follow-up, waiting list | Internal referral/care continuity state machines | P0: clinical actor approvals and partner outcome evidence |
| Hospital stores / equipment maintenance | Inventory foundation; no integrated biomedical CMMS | P1: audit-ready asset, calibration, procurement and work orders |
| HR, rosters, payroll | Staff/provider operations foundation, no HR/payroll equivalent | P2: rosters, credential expiry, labor/payroll partner integration |
| Multi-location hospital/clinic chain | Organization and tenant services with tested isolation | P0: site-scoped permissions, inter-branch mapping and audits |
| Hospital BI/finance dashboards | Internal analytics, several privacy-safe scores | P1: verified operations KPI provenance, schema parity and finance reconciliation |
| Migration/onboarding/training | Import foundations; no multi-hospital data migration service proven | P0: import dry-run, rollback and customer acceptance documentation |
| Cloud/on-prem/hybrid deployments | AWS EC2 + Vercel code path with passing CI; no live proven rollout | P0: reviewed staging deployment, durable backups, zero-data-loss restore |
| Security, consent and audit | Tested controls; formal certification and external pen test not established | P0: threat models, tenant IDOR tests, clinical privacy and vulnerability audits |

## Differentiation: beyond hospital ERP

Focus investment on advantages a simple hospital HIS may not offer consistently. **None are promises of field performance until verified**:

1. **Patient-controlled longitudinal health memory:** minimum-necessary consent, revocable sharing, family delegation and provenance instead of institution-owned silos.
2. **Agentic Care OS with hard human gates:** permissioned read-only agents, safe task planning and explicit clinician/patient confirmation for consequential steps. Never permit autonomous diagnosis/prescribing.
3. **Rural-first multilingual and bandwidth-adaptive care discovery:** Bengali/Hindi/English accessibility, official provenance and offline-safe user experiences without fabricated results.
4. **Truthful real-time capability evidence:** independently verified hospital capacity, clinician slot and pharmacy inventory with last-confirmed timestamps; always UNKNOWN when feed missing.
5. **Referral + waiting list + outcome continuity:** end-to-end handoffs with consent and explicit acceptance evidence.
6. **Healthcare provider network storefronts:** curated provider-owned branded pages, booking, services, operating hours, no unreviewed auto-published healthcare claims.
7. **Researcher/ops governed intelligence:** legal public datasets with named licensing, permitted ingestion, provenance, audit and reproducible refresh.
8. **Interoperability-by-contract:** FHIR/ABDM adapter interfaces are useful only with legally valid partner credentials, patient authorization and validated exchanges.
9. **Real-world operations resilience:** incident triage, restore drills, measurable uptime, staged rollout, synthetic monitoring and rollback without bypassing production approval.

## Implementation sequencing

### Wave A — foundational code (current PR)

- Keep previously implemented features and CI baseline unchanged.
- Add verified-hospital-only private bed board with allowed occupancy transitions, optimistic conflict detection, history and zero patient information. This is an **internal beta**, not hospital IPD admission or live public bed availability.
- Add direct multi-hospital IDOR, unauthorized access and concurrency tests, and PostgreSQL startup smoke.
- Extend capability registry and preserved inventory to **74 features: 50 WORKING / 8 BETA / 14 INTEGRATION_REQUIRED / 2 FUTURE**.
- Confirm prior working modules still pass original release gates.

### Wave B — operational hospital parity

- Operator workflows for verified appointments/OPD token queues, patient consent and ADT episodes, discharge and nursing.
- LIMS accession/sample lifecycle/validated report signing, pharmacy FEFO lot movement, traceable charge ledger.
- Multi-tenant sites and branch permission boundaries; pilot staff training and documented governance.
- Clinical sign-off and testing for every result/prescription; high-risk actions always authorized and auditable.

### Wave C — enterprise HIMS

- OT surgical lists, biomedical inventory and CMMS, RIS/DICOM integration, licensed blood bank, payroll, accounting, insurers/TPA.
- Real migrations, reporting reconciliation, accessibility/performance, disaster recovery drills and operational SLAs.

### Wave D — external/regulatory evidence and public launch

- Authorized ABDM/ABHA, EHR/HIE, PMJAY/TPA, payment, messaging, certified devices and lab analyzers.
- Complete data-protection review, clinician evaluation, field trials and independent compliance verification.
- AWS/Vercel origin and backups; staged provider cohort followed by 2-hospital pilot, only then scale.

## Release acceptance (non-negotiable)

- Every write is authorized by role + **verified tenant**, audited, idempotent/concurrency controlled, and protects patient confidentiality.
- Internal bed state must **never** be advertised as live hospital bed availability or clinical admission.
- CI and live staging both pass; no fabricated partner connectivity, medication stock, prices, insurance decisions, official datasets or certifications.
- No auto-prescribing. No unconsented data sharing or automated consequential clinical decisions.
- All PRs stay draft until owner-approved tests, screenshots, staging persistence, security review and rollback evidence exist.

**Current result:** wave A software PR, not full Healthray parity, not a market-performance claim.
