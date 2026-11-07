# ZENDOC 2.0 â€” Feature Truth Matrix & Capability Registry

**Product:** ZENDOC 2.0  
**Document version:** 2.0.0  
**Baseline source:** `docs/MUST_PRESERVE_CAPABILITY_MANIFEST.json` & `docs/FEATURE_TRUTH_MATRIX.md`  
**Truth Model Status:** Authoritative Runtime Specification  

---

## 1. Truth Status Taxonomy

ZENDOC enforces a rigorous, non-negotiable truth status model. Configuration existence does not imply reachability, and recorded requests do not imply external execution:

- **`WORKING`**: The ZENDOC-owned software workflow is completely implemented, verified, and operational within its stated boundary.
- **`BETA`**: The workflow is usable, but a model, browser capability, provider availability, or operational factor limits production guarantees.
- **`INTEGRATION_REQUIRED`**: A verified architectural boundary exists in code, but a live external third-party API, commercial agreement, official credentials, or verified dataset is required for execution.
- **`DISABLED`**: Deliberately prevented from operating by code policy or regulatory constraint.
- **`FUTURE`**: Intentionally reserved for subsequent regulatory or clinical validation cycles.

---

## 2. Global Non-Negotiable Safety & Clinical Invariants

1. **AUTONOMOUS PRESCRIBING STRICTLY FORBIDDEN**: System cannot issue or sign prescriptions without verified human doctor review and cryptographic signature.
2. **NO AUTONOMOUS DIAGNOSIS**: AI outputs are strictly educational, informational, and advisory. Disclaimers and emergency prompts are mandatory.
3. **DETERMINISTIC EMERGENCY-FIRST TRIAGE**: Acute conditions (severe chest pain, stroke symptoms, uncontrolled bleeding) bypass all AI generation and trigger immediate emergency hotlines (102/108/911/999).
4. **ZERO FABRICATED METRICS**: Provider ratings, distance metrics, slot availability, prices, discounts, and bed occupancies must never be faked.
5. **HUMAN-IN-THE-LOOP TOOL EXECUTION**: Consequential tools require explicit human confirmation with tamper-evident cryptographic plan hashes.
6. **PROVENANCE & AUDIT TRAIL**: Every health metric and document must record its origin (`USER_REPORTED`, `DOCUMENT_EXTRACTED`, `PROVIDER_RECORDED`, `DEVICE_RECORDED`).

---

## 3. Comprehensive 74-Capability Inventory

### 3.1 Merged Current Working Capabilities (50)

| Capability Key | Label | Domain | Status | Operational Boundary |
|---|---|---|---|---|
| `zendoc_core_agent` | ZENDOC Core Agent | AI Core | `WORKING` | Permissioned assistant with tool registry, audit trail, and emergency safety gate. |
| `connect_messaging` | ZENDOC Connect Messaging | Messaging | `WORKING` | Authenticated conversation rooms, read receipts, media attachments, participant blocking. |
| `mental_wellness_private` | Mental Wellness & Awareness | Wellness | `WORKING` | Private mood tracking, daily stress reflection, local audio guide library. |
| `health_community` | ZENDOC Health Community | Community | `WORKING` | Moderated patient peer support, story posts, comments, likes, report controls. |
| `health_shop_discovery` | Health Shop Discovery | Commerce | `WORKING` | Curated medical catalog with outbound merchant reference links (no fake stock/price). |
| `deterministic_safety_engine`| Deterministic Safety Engine | AI Safety | `WORKING` | Pattern-based emergency triage that halts AI generation on red-flag conditions. |
| `local_agent_controller` | Local Agent Controller | AI Runtime | `WORKING` | Local model connectivity test, status check, and fallback orchestrator. |
| `slm_product_layer` | ZENDOC-SLM v1 Product Layer | AI Product | `WORKING` | Prompt structuring, schema output validation, and educational guardrails. |
| `slm_knowledge_layer` | Approved Knowledge Layer | AI Knowledge | `WORKING` | Curated clinical guidelines and approved repository RAG store. |
| `slm_output_validator` | Structured Output Validator | AI Safety | `WORKING` | Zod/Pydantic schema enforcement on model completions; rejects hallucinations. |
| `model_router` | Model Router | AI Governance| `WORKING` | Privacy-aware model routing based on consent scope and query sensitivity. |
| `model_evaluation_lab` | Model Evaluation Lab | AI Ops | `WORKING` | Automated benchmark runs against standardized clinical question datasets. |
| `agent_task_engine` | Agent Task Engine | AI Execution | `WORKING` | Multi-step agent workflow execution with step-level state persistence. |
| `approval_engine` | Human Approval Engine | Governance | `WORKING` | Cryptographic plan hash verification before executing consequential user actions. |
| `proactive_alerts` | Proactive Operational Alerts | Operations | `WORKING` | Internal system warnings for high error rates, unhandled requests, and SLA breaches. |
| `capability_registry` | Capability Registry | Governance | `WORKING` | Truthful introspection endpoint reporting live system capability states. |
| `specialized_agent_routing` | Specialized Agent Routing v2 | AI Core | `WORKING` | Intent classifier routing between Cardiology, Pediatrics, Dietetics, and Triage agents. |
| `carefin_engine` | CareFin Benefits Discovery | Finance | `WORKING` | Deterministic eligibility rule matching for PMJAY, CGHS, and state welfare programs. |
| `referral_waiting_list_os` | Referral & Waiting List OS | Clinical Ops | `WORKING` | Doctor-to-doctor clinical handoff ledger, triage queue, and waitlist tracker. |
| `automatic_care_journey` | Care Journey Coordinator | Coordination | `WORKING` | Milestone-based journey state machine (e.g. Prenatal, Post-Op recovery). |
| `ai_workforce_incident_runtime` | AI Incident Runtime | AI Safety | `WORKING` | Evidence-gated logging of model degradation, prompt injections, and safety halts. |
| `safe_operations_automation` | Safe Operations Automation | Operations | `WORKING` | Automated idempotent batch cleanup of expired holds and stale sessions. |
| `diagnostics_freshness_v2` | Diagnostics Freshness Layer | Diagnostics | `WORKING` | Diagnostic test alias normalizer and pricing freshness indicator. |
| `nutrition_agent` | Nutrition & Hydration Agent | Wellness | `WORKING` | Calorie, macronutrient, and daily water intake tracker with baseline goals. |
| `multilingual_foundation` | Multilingual Foundation | i18n | `WORKING` | English, Bengali, and Hindi UI translation dictionary and language switchers. |
| `geographic_healthcare_graph` | Geographic Healthcare Graph | Geospatial | `WORKING` | Hierarchical State -> District -> Sub-district healthcare facility graph. |
| `official_public_data_ingestion`| Official Data Ingestion | Data Ops | `WORKING` | Idempotent bulk ingest pipeline for official government health directories. |
| `global_health_intelligence_fabric`| Health Intelligence Fabric | Data Ops | `WORKING` | Normalized disease surveillance and health facility directory aggregation. |
| `organization_intelligence` | Organization Intelligence | B2B | `WORKING` | Multi-branch healthcare facility profile and staff hierarchy management. |
| `global_source_research_automation`| Research Source Automation | Data Ops | `WORKING` | Automated gap detection in provider directories across underserved regions. |
| `identity_evidence_review` | Identity Evidence Review | Trust & KYC | `WORKING` | Manual operator review interface for clinical credentials, licenses, and ID cards. |
| `provider_onboarding_v1` | Provider Onboarding Workflow | Clinical Ops | `WORKING` | Step-by-step registration for doctors, clinics, labs, and pharmacies. |
| `carefin_pilot_ui` | CareFin Pilot UI | Finance | `WORKING` | Patient-facing benefits calculator and scheme documentation checklist. |
| `care_journey_pilot_ui` | Care Journey Pilot UI | Coordination | `WORKING` | Interactive visual roadmap displaying completed and pending care milestones. |
| `pilot_analytics` | Pilot Analytics Scorecard | Operations | `WORKING` | Telemetry on active consultations, booking conversions, and safety escalations. |
| `health_memory` | Health Memory & Timeline | Health Memory| `WORKING` | Chronological feed of medical events, lab results, vitals, and doctor visits. |
| `medical_records` | Medical Records Upload | Health Memory| `WORKING` | Private storage upload with MIME validation, SHA256 checksums, and metadata. |
| `appointments` | Appointments Management | Coordination | `WORKING` | Real-time appointment booking, provider slot reservation, status tracking. |
| `fitness_coach` | AI Fitness Coach | Wellness | `WORKING` | Workout routine generator tailored to user goals and physical constraints. |
| `fitness_videos` | Fitness Video Library | Wellness | `WORKING` | Curated library of instructional stretching, mobility, and rehabilitation videos. |
| `human_operations` | Human Operations | Clinical Ops | `WORKING` | Clinical review portal for escalated patient queries and human overrides. |
| `family_care` | Family Care Circle | Coordination | `WORKING` | Multi-profile account management for children, spouses, and elderly parents. |
| `home_health` | Home Healthcare Booking | Care Ops | `WORKING` | Request intake for home nursing, physiotherapy, and eldercare assistance. |
| `pharmacy` | Pharmacy Request Workflow | Pharmacy | `WORKING` | Prescription upload, digital order creation, and pharmacy bid comparison. |
| `medical_transport` | Medical Transport Requests | Transport | `WORKING` | Non-emergency patient transport and ambulance intake booking state machine. |
| `iot_hub` | IoT Health Device Hub | Hardware | `WORKING` | Manual and standardized payload entry for BP cuffs, glucometers, and pulse oximeters. |
| `healthcare_finder` | Healthcare Provider Finder | Discovery | `WORKING` | Search doctors, clinics, and hospitals with category and district filtering. |
| `in_app_notifications` | In-App Notification Center | Messaging | `WORKING` | Central notification feed with unread counts and actionable deep-links. |
| `object_storage` | Private Object Storage | Infrastructure| `WORKING` | Secure bucket storage with private signed URLs and client download authorization. |
| `realtime` | Real-time Data Sync | Infrastructure| `WORKING` | WebSocket / Server-Sent Events / Polling updates for chat and order status. |

---

### 3.2 Current Beta Capabilities (8)

| Capability Key | Label | Domain | Status | Operational Boundary |
|---|---|---|---|---|
| `voice_video_calling` | Voice / Video Calling | Connect | `BETA` | WebRTC P2P signaling implemented; public network success depends on STUN/TURN relays. |
| `universal_healthcare_interoperability_gateway`| Universal Interop Gateway | Interop | `BETA` | FHIR R4 schema mapper; local transformations work, public endpoints require auth. |
| `telehealth` | Telehealth Consultation | Clinical Ops | `BETA` | Consultation room scheduling, chat, and WebRTC handoff; relies on doctor availability. |
| `report_intelligence` | Medical Report Intelligence | AI Product | `BETA` | Educational parsing of lab values with reference ranges; explicitly not a clinical diagnosis. |
| `pose_coach` | Fitness Camera Preview | Wellness | `BETA` | Browser camera feed with canvas overlays; no synthetic AI accuracy claims. |
| `organization_health` | Organization Member Health | B2B | `BETA` | Corporate dashboard for employee wellness check-ins; aggregate reporting only. |
| `video_intelligence` | Video Guidance Search | Discovery | `BETA` | Semantic tagging and search across curated medical educational videos. |
| `hospital_bed_board` | Hospital Ward & Bed Board | Clinical Ops | `BETA` | Internal hospital dashboard for tracking occupied, available, and ICU beds. |

---

### 3.3 External Integration Required Capabilities (14)

| Capability Key | Label | Domain | Status | Required External Dependency |
|---|---|---|---|---|
| `community_media_public_durability`| Durable Public Media | Storage | `INTEGRATION_REQUIRED` | CDN bucket configuration with high-volume asset lifecycle policies. |
| `affiliate_referral_revenue` | Affiliate Referral Tracking | Commerce | `INTEGRATION_REQUIRED` | Approved merchant affiliate contracts (Amazon, 1mg, Apollo) and webhook postback. |
| `connected_payments_gateway` | Connected Payments Gateway | Payments | `INTEGRATION_REQUIRED` | Active Razorpay / Stripe merchant keys and signed webhook secret. |
| `local_slm` | Local SLM Execution | AI Runtime | `INTEGRATION_REQUIRED` | Local ONNX / Ollama runtime running on user hardware (e.g. Snapdragon NPU). |
| `cloud_llm` | Cloud LLM Provider | AI Runtime | `INTEGRATION_REQUIRED` | Production API credentials for Anthropic Claude / Google Gemini / OpenAI. |
| `real_local_model_evaluation` | Real Local Model Benchmarks | AI Ops | `INTEGRATION_REQUIRED` | Dedicated hardware test runner to capture real latency/tokens-per-sec metrics. |
| `carefin_live_verification` | Live Coverage Verification | Finance | `INTEGRATION_REQUIRED` | Authorized API access to National Health Authority (ABDM) or private TPA portal. |
| `free_form_translation` | Free-form Translation | i18n | `INTEGRATION_REQUIRED` | Real-time neural machine translation API for arbitrary free-text conversations. |
| `official_live_connectors` | Live Official Data Connectors| Data Ops | `INTEGRATION_REQUIRED` | Direct government API credentials for ABDM Registry, OGD India, or LGD updates. |
| `live_external_fhir_exchange` | Live External FHIR Exchange | Interop | `INTEGRATION_REQUIRED` | Sandbox / Production M2M TLS certificates for Hospital Information Systems (HIS). |
| `external_ekyc` | External eKYC Provider | Trust & KYC | `INTEGRATION_REQUIRED` | Certified UIDAI / DigiLocker partner credentials for instant identity verification. |
| `external_places_discovery` | External Places Discovery | Discovery | `INTEGRATION_REQUIRED` | Google Places API key or TomTom API key for live establishment metadata. |
| `external_notifications` | External Notifications | Messaging | `INTEGRATION_REQUIRED` | SendGrid (Email), Twilio (SMS), or Gupshup (WhatsApp) production API keys. |
| `postgresql` | PostgreSQL Persistence | Database | `INTEGRATION_REQUIRED` | Supabase PostgreSQL production instance connection string and credentials. |

---

### 3.4 Planned Future Capabilities (2)

| Capability Key | Label | Domain | Status | Status Reason |
|---|---|---|---|---|
| `zendoc_proprietary_slm` | ZENDOC Proprietary SLM | AI R&D | `FUTURE` | Requires multi-stage clinical fine-tuning, benchmark validation, and regulatory safety clearance. |
| `autonomous_prescribing` | Autonomous Prescribing | Clinical Ops | `FUTURE` | Legally restricted worldwide. Autonomous pharmaceutical prescription issuance is prohibited by law. |

---

## 4. Verification & Audit Sign-Off

The features categorized above constitute the exhaustive capability surface of ZENDOC 2.0. Implementation on `rebuild/zendoc-2.0-vercel` preserves every single `WORKING` and `BETA` capability, creates type-safe mockable boundaries for `INTEGRATION_REQUIRED` workflows, and strictly maintains safety barriers for `DISABLED` and `FUTURE` features.
