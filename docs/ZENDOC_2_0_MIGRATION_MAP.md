# ZENDOC 2.0 â€” Migration Map & Blueprint Transition Inventory

**Product:** ZENDOC 2.0 Rebuild  
**Document version:** 2.0.0  
**Target Architecture:** Next.js (App Router, TypeScript) + Supabase (PostgreSQL, Auth, Storage, RLS) on Vercel  
**Status:** Authoritative Migration Blueprint  

---

## 1. Executive Migration Strategy

The ZENDOC 2.0 rebuild replaces the legacy single-server Python Flask application and its reverse-proxy deployment with a native Next.js application hosted on Vercel and connected directly to Supabase.

### Migration Principles
1. **Preserve Validated Business Logic**: Clinical workflows, appointment state transitions, consent boundaries, deterministic triage rules, and provenance accounting are translated directly into TypeScript domain services and Supabase database constraints.
2. **Eliminate Architecture Antipatterns**:
   - Retire `vercel.ts` origin proxy that rewritten requests to EC2/OCI.
   - Replace manual session cookie management with standard Supabase Auth SSR cookies.
   - Replace ad-hoc SQLite fallback files with managed Supabase PostgreSQL.
   - Replace S3/boto3 custom wrappers with Supabase Storage client with private signed URLs.
3. **Decouple Heavy Python Workloads**: Retain Python only behind a microservice boundary for heavy machine-learning, ONNX inference, audio transcription (Whisper), and deep PDF document OCR.
4. **Zero Downtime / Phased Delivery**: The rebuild branch (`rebuild/zendoc-2.0-vercel`) implements and verifies the complete target application while the legacy `main` branch remains untouched.

---

## 2. Blueprint & Module Migration Matrix

Every one of the 60 Flask blueprints in the existing repository is accounted for below with its target destination and migration strategy:

| # | Flask Blueprint (`zendoc/`) | Primary Responsibility | Target Next.js / Supabase Destination | Migration Classification |
|---|---|---|---|---|
| 1 | `bp` (`routes.py`) | Core patient dashboard, landing, auth, vitals, profile | `src/app/(patient)/`, `src/app/(auth)/`, `src/actions/patient.ts` | **MIGRATED_TO_NEXTJS** |
| 2 | `ai_chat_bp` (`ai_chat_routes.py`) | AI Chat, conversation history, context assembly | `src/app/(patient)/ai/`, `src/app/api/ai/chat/route.ts` | **MIGRATED_TO_NEXTJS** |
| 3 | `calls_bp` (`call_routes.py`, `call_signaling.py`) | WebRTC signaling, ICE exchange, call rooms | `src/app/api/connect/calls/route.ts`, `src/components/connect/CallModal.tsx` | **MIGRATED_TO_NEXTJS** |
| 4 | `transport_partner_bp` (`transport_partner.py`) | Ambulance and non-emergency transport booking | `src/app/(care)/transport/`, `src/actions/transport.ts` | **MIGRATED_TO_NEXTJS** |
| 5 | `release_health_bp` (`release_health_routes.py`) | System status, release health, deployment verifier | `src/app/api/health/route.ts`, `src/app/(admin)/health/` | **MIGRATED_TO_NEXTJS** |
| 6 | `referrals_bp` (`referral_routes.py`, `referral_service.py`) | Referral OS, waiting list, doctor-to-doctor handoff | `src/app/(provider)/referrals/`, `src/actions/referral.ts` | **MIGRATED_TO_NEXTJS** |
| 7 | `workforce_incidents_bp` (`workforce_incident_routes.py`) | AI workforce incident logs, evidence gates | `src/app/(admin)/incidents/`, `src/actions/incident.ts` | **MIGRATED_TO_NEXTJS** |
| 8 | `local_controller_bp` (`local_controller_routes.py`) | On-device SLM runtime bridge (EdgeCare) | `src/app/api/ai/local-bridge/route.ts` | **INTEGRATION_BOUNDARY** |
| 9 | `health_memory_bp` (`health_memory.py`) | Longitudinal timeline, health facts, provenance graph | `src/app/(patient)/memory/`, `src/actions/memory.ts` | **MIGRATED_TO_NEXTJS** |
| 10 | `care_continuity_bp` (`care_continuity_routes.py`) | Care continuity snapshots, provider handoff ledger | `src/app/(care)/continuity/`, `src/actions/continuity.ts` | **MIGRATED_TO_NEXTJS** |
| 11 | `business_bp` (`business_routes.py`, `business_api.py`) | Partner APIs, B2B access keys, rate limits | `src/app/api/v1/business/`, `src/app/(admin)/b2b/` | **MIGRATED_TO_NEXTJS** |
| 12 | `medical_knowledge_bp` (`knowledge_routes.py`) | Curated RAG guidelines, medical authority index | `src/app/api/ai/knowledge/route.ts`, Supabase pgvector | **MIGRATED_TO_NEXTJS** |
| 13 | `personal_health_baseline_bp` (`personal_baseline_routes.py`) | Baseline metrics, clinical reference boundaries | `src/app/(patient)/vitals/baseline/`, `src/actions/vitals.ts` | **MIGRATED_TO_NEXTJS** |
| 14 | `preventive_care_bp` (`preventive_care_routes.py`) | Preventive care protocols, immunization, cancer screening | `src/app/(patient)/preventive/`, `src/actions/preventive.ts` | **MIGRATED_TO_NEXTJS** |
| 15 | `document_extraction_bp` (`document_extraction_routes.py`) | Medical report parsing, OCR metadata extraction | `src/app/api/documents/extract/route.ts`, Python Boundary | **SERVICE_BOUNDARY** |
| 16 | `device_ingestion_bp` (`device_ingestion.py`) | IoT health monitors, Bluetooth BLE sync, Apple/Google Health | `src/app/api/devices/ingest/route.ts`, `src/app/(patient)/devices/` | **MIGRATED_TO_NEXTJS** |
| 17 | `fitness_bp` (`fitness_routes.py`, `fitness_coach.py`) | Workouts, pose guidance preview, exercise plans | `src/app/(wellness)/fitness/`, `src/actions/fitness.ts` | **MIGRATED_TO_NEXTJS** |
| 18 | `family_bp` (`family_routes.py`, `family_care.py`) | Family circle, child/elder dependent proxy access | `src/app/(patient)/family/`, `src/actions/family.ts` | **MIGRATED_TO_NEXTJS** |
| 19 | `ecosystem_bp` (`ecosystem_routes.py`) | Universal health search, provider directory | `src/app/(discovery)/find-care/`, `src/actions/discovery.ts` | **MIGRATED_TO_NEXTJS** |
| 20 | `health_hub_bp` (`health_hub_routes.py`) | Consolidated health hub summary | `src/app/(patient)/dashboard/` | **MIGRATED_TO_NEXTJS** |
| 21 | `identity_verification_bp` (`identity_verification_routes.py`) | Evidence passport, clinical credential review | `src/app/(provider)/verify/`, `src/actions/verification.ts` | **MIGRATED_TO_NEXTJS** |
| 22 | `integration_readiness_bp` (`integration_routes.py`) | Health checks for external APIs (SMS, email, places) | `src/app/api/admin/integrations/route.ts` | **MIGRATED_TO_NEXTJS** |
| 23 | `interoperability_bp` (`interoperability_routes.py`) | FHIR / ABDM health data exchange adapter | `src/app/api/fhir/`, `src/lib/interop/fhir.ts` | **INTEGRATION_BOUNDARY** |
| 24 | `health_shop_bp` (`health_shop_routes.py`) | Medical supplies discovery, external merchant handoff | `src/app/(discovery)/shop/`, `src/actions/shop.ts` | **MIGRATED_TO_NEXTJS** |
| 25 | `health_social_bp` (`health_social_routes.py`) | Health Community feeds, moderated discussion, stories | `src/app/(wellness)/community/`, `src/actions/community.ts` | **MIGRATED_TO_NEXTJS** |
| 26 | `mental_wellness_bp` (`mental_wellness_routes.py`) | Private mood journal, stress assessment, guided audio | `src/app/(wellness)/mental/`, `src/actions/mental.ts` | **MIGRATED_TO_NEXTJS** |
| 27 | `payments_bp` (`payment_routes.py`, `payments.py`) | Razorpay gateway, order invoices, webhook verification | `src/app/api/payments/`, `src/actions/payment.ts` | **INTEGRATION_BOUNDARY** |
| 28 | `pharmacy_order_ops_bp` (`pharmacy_order_routes.py`) | Prescription upload, pharmacy inventory, quote review | `src/app/(care)/pharmacy/`, `src/actions/pharmacy.ts` | **MIGRATED_TO_NEXTJS** |
| 29 | `operational_fulfilment_bp` (`operational_fulfilment.py`) | Multi-step provider fulfilment plans | `src/app/(care)/fulfilment/`, `src/actions/fulfilment.ts` | **MIGRATED_TO_NEXTJS** |
| 30 | `operational_fulfilment_release_bp` | Fulfilment deployment and release checks | `src/app/api/ops/release/route.ts` | **MIGRATED_TO_NEXTJS** |
| 31 | `operational_fulfilment_ui_bp` | Operations dashboard and provider dispatch UI | `src/app/(admin)/ops/`, `src/components/ops/` | **MIGRATED_TO_NEXTJS** |
| 32 | `milestone7_bp` (`milestone7_routes.py`) | Controlled pilot appointments, feedback, receipts | `src/app/(care)/appointments/`, `src/actions/appointment.ts` | **MIGRATED_TO_NEXTJS** |
| 33 | `milestone8_bp` (`milestone8_routes.py`) | Specialist agent routing and tool execution ledger | `src/app/api/ai/agent-os/route.ts`, `src/lib/ai/` | **MIGRATED_TO_NEXTJS** |
| 34 | `edgecare_bp` (`edgecare_routes.py`, `edgecare_asr.py`) | Snapdragon NPU / local Whisper ASR streaming | `src/app/api/edgecare/route.ts`, Python Boundary | **SERVICE_BOUNDARY** |
| 35 | `milestone82_bp` (`milestone82_routes.py`) | Model Evaluation Lab, synthetic benchmarks | `src/app/(admin)/eval-lab/`, `src/actions/eval.ts` | **MIGRATED_TO_NEXTJS** |
| 36 | `connected_care_bp` (`connected_care_routes.py`) | Trust Center, consent grant revocations, provenance | `src/app/(patient)/trust-center/`, `src/actions/trust.ts` | **MIGRATED_TO_NEXTJS** |
| 37 | `care_os_bp` (`care_os_routes.py`) | Unified care action orchestrator | `src/app/(care)/orchestrator/`, `src/actions/care-os.ts` | **MIGRATED_TO_NEXTJS** |
| 38 | `india_care_rail_bp` | National health mission and regional district health routing | `src/lib/geo/india-rail.ts`, `src/actions/geo.ts` | **MIGRATED_TO_NEXTJS** |
| 39 | `universal_search_bp` (`universal_search_routes.py`) | Cross-module global search (doctors, tests, records) | `src/app/api/search/route.ts`, `src/components/search/` | **MIGRATED_TO_NEXTJS** |
| 40 | `carefin_bp` (`carefin_routes.py`, `carefin_engine.py`) | Health financing, government scheme matching (AB-PMJAY) | `src/app/(care)/carefin/`, `src/actions/carefin.ts` | **MIGRATED_TO_NEXTJS** |
| 41 | `care_journey_bp` (`care_journey_routes.py`) | Longitudinal episode journeys (e.g. maternity, cardiac) | `src/app/(care)/journeys/`, `src/actions/journey.ts` | **MIGRATED_TO_NEXTJS** |
| 42 | `nutrition_intelligence_bp` (`nutrition_routes.py`) | Dietary log, macro/micronutrient guidelines, hydration | `src/app/(wellness)/nutrition/`, `src/actions/nutrition.ts` | **MIGRATED_TO_NEXTJS** |
| 43 | `neo_analytics_bp` (`neo_analytics_routes.py`) | Telemetry, product conversion funnels, retention | `src/app/(admin)/analytics/`, `src/lib/telemetry/` | **MIGRATED_TO_NEXTJS** |
| 44 | `provider_organizations_bp` | Health network sites, multi-clinic tenant management | `src/app/(org)/sites/`, `src/actions/organization.ts` | **MIGRATED_TO_NEXTJS** |
| 45 | `organization_health_bp` (`organization_health_routes.py`) | Corporate/institution wellness plans, employee health | `src/app/(org)/benefits/`, `src/actions/org-health.ts` | **MIGRATED_TO_NEXTJS** |
| 46 | `hospital_bed_bp` (`hospital_bed_routes.py`) | Real-time IPD ward and bed availability tracker | `src/app/(provider)/beds/`, `src/actions/beds.ts` | **MIGRATED_TO_NEXTJS** |
| 47 | `language_bp` (`language_routes.py`) | Localization (English, Bengali, Hindi) dictionary/cookies | `src/lib/i18n/`, `src/components/layout/LanguagePicker.tsx` | **MIGRATED_TO_NEXTJS** |
| 48 | `geography_graph_bp` (`geography_routes.py`) | Geospatial node hierarchy (State -> District -> Facility) | `src/lib/geo/graph.ts`, Supabase PostgreSQL PostGIS | **MIGRATED_TO_NEXTJS** |
| 49 | `public_ingestion_bp` (`public_ingestion_routes.py`) | Bulk ingestion of official hospital registries | `src/app/api/admin/ingest/route.ts`, Supabase migrations | **MIGRATED_TO_NEXTJS** |
| 50 | `dataset_snapshot_ingestion_bp` | Dataset snapshot validation and sha256 attestation | `src/app/api/admin/snapshots/route.ts` | **MIGRATED_TO_NEXTJS** |
| 51 | `provider_onboarding_bp` (`provider_onboarding_routes.py`) | Clinical license submission, hospital affiliation proof | `src/app/(provider)/onboarding/`, `src/actions/provider.ts` | **MIGRATED_TO_NEXTJS** |
| 52 | `pilot_operations_bp` (`pilot_operations_routes.py`) | Pilot site enrollment, institution SLA monitoring | `src/app/(admin)/pilot/`, `src/actions/pilot.ts` | **MIGRATED_TO_NEXTJS** |
| 53 | `public_launch_bp` (`public_launch_routes.py`) | Public landing showcase, patient invitation claim | `src/app/(marketing)/`, `src/actions/invitation.ts` | **MIGRATED_TO_NEXTJS** |
| 54 | `global_data_bp` (`global_data_routes.py`) | Multi-country currency, ICD-10 code lookup | `src/lib/constants/icd10.ts`, Supabase static tables | **MIGRATED_TO_NEXTJS** |
| 55 | `showcase_bp` (`showcase_routes.py`) | Interactive feature demonstrations (demo mode only) | `src/app/(marketing)/demo/` | **MIGRATED_TO_NEXTJS** |
| 56 | `specialist_agents_bp` (`specialist_agent_routes.py`) | Clinical AI specialist team (Cardiology, Paediatrics, etc.)| `src/app/api/ai/specialists/route.ts`, `src/lib/ai/` | **MIGRATED_TO_NEXTJS** |
| 57 | `system_intelligence_bp` (`system_intelligence_routes.py`) | Autonomous error telemetry, database health watcher | `src/app/api/ops/intelligence/route.ts` | **MIGRATED_TO_NEXTJS** |
| 58 | `network_sites_bp` (`network_site_routes.py`) | Clinic branch location manager and GPS pins | `src/app/(org)/locations/`, `src/actions/location.ts` | **MIGRATED_TO_NEXTJS** |
| 59 | `payer_financial_bp` (`payer_financial_routes.py`) | Insurance claims, prior authorizations, TPA routing | `src/app/(care)/claims/`, `src/actions/claims.ts` | **MIGRATED_TO_NEXTJS** |
| 60 | `population_health_bp` (`population_health_routes.py`) | Epidemic risk surveillance, cohort analytics | `src/app/(admin)/population/`, `src/actions/population.ts` | **MIGRATED_TO_NEXTJS** |

---

## 3. Web Route & API Endpoint Transition

### 3.1 Patient & Core Experience
| Legacy Flask Route | Target Next.js App Route | Method | Access Control |
|---|---|---|---|
| `/` | `src/app/page.tsx` | GET | Public |
| `/login` | `src/app/(auth)/login/page.tsx` | GET, POST | Public (redirect if authed) |
| `/register` | `src/app/(auth)/register/page.tsx` | GET, POST | Public (redirect if authed) |
| `/logout` | `src/app/api/auth/signout/route.ts` | POST | Authenticated |
| `/dashboard` | `src/app/(patient)/dashboard/page.tsx` | GET | Role: Patient |
| `/profile` | `src/app/(patient)/profile/page.tsx` | GET, POST | Role: Patient |
| `/records` | `src/app/(patient)/records/page.tsx` | GET, POST | Role: Patient / Caregiver |
| `/records/upload` | `src/app/(patient)/records/upload/page.tsx` | GET, POST | Role: Patient / Caregiver |
| `/timeline` | `src/app/(patient)/memory/page.tsx` | GET | Role: Patient / Caregiver |
| `/vitals` | `src/app/(patient)/vitals/page.tsx` | GET, POST | Role: Patient / Caregiver |
| `/connected-care/trust-center` | `src/app/(patient)/trust-center/page.tsx` | GET, POST | Role: Patient |
| `/family` | `src/app/(patient)/family/page.tsx` | GET, POST | Role: Patient |

### 3.2 Discovery & Care Coordination
| Legacy Flask Route | Target Next.js App Route | Method | Access Control |
|---|---|---|---|
| `/finder` | `src/app/(discovery)/find-care/page.tsx` | GET | Public / Patient |
| `/doctor/<id>` | `src/app/(discovery)/doctor/[id]/page.tsx` | GET | Public / Patient |
| `/hospital/<id>` | `src/app/(discovery)/hospital/[id]/page.tsx` | GET | Public / Patient |
| `/appointments` | `src/app/(care)/appointments/page.tsx` | GET, POST | Role: Patient / Provider |
| `/appointments/book` | `src/app/(care)/appointments/book/page.tsx` | GET, POST | Role: Patient |
| `/pharmacy` | `src/app/(care)/pharmacy/page.tsx` | GET, POST | Role: Patient / Pharmacy |
| `/diagnostics` | `src/app/(care)/diagnostics/page.tsx` | GET, POST | Role: Patient / Lab |
| `/care-journeys` | `src/app/(care)/journeys/page.tsx` | GET, POST | Role: Patient / Caregiver |
| `/carefin` | `src/app/(care)/carefin/page.tsx` | GET, POST | Role: Patient |
| `/transport` | `src/app/(care)/transport/page.tsx` | GET, POST | Role: Patient |

### 3.3 ZENDOC AI & Messaging
| Legacy Flask Route | Target Next.js App Route | Method | Access Control |
|---|---|---|---|
| `/ai/chat` | `src/app/(patient)/ai/page.tsx` | GET, POST | Role: Patient |
| `/api/ai/chat` | `src/app/api/ai/chat/route.ts` | POST | Authenticated |
| `/connect` | `src/app/(connect)/messages/page.tsx` | GET | Authenticated |
| `/connect/c/<id>` | `src/app/(connect)/messages/[id]/page.tsx` | GET, POST | Conversation Participant |
| `/api/connect/calls/signal` | `src/app/api/connect/calls/route.ts` | POST | Authenticated |

### 3.4 Provider & Administration
| Legacy Flask Route | Target Next.js App Route | Method | Access Control |
|---|---|---|---|
| `/provider/dashboard` | `src/app/(provider)/dashboard/page.tsx` | GET | Role: Provider |
| `/provider/onboarding` | `src/app/(provider)/onboarding/page.tsx` | GET, POST | Authenticated Provider |
| `/provider/verification`| `src/app/(provider)/verify/page.tsx` | GET, POST | Role: Admin / Provider |
| `/admin/overview` | `src/app/(admin)/overview/page.tsx` | GET | Role: Platform Admin |
| `/admin/audit-logs` | `src/app/(admin)/audit/page.tsx` | GET | Role: Platform Admin |
| `/admin/incidents` | `src/app/(admin)/incidents/page.tsx` | GET | Role: Platform Admin |

---

## 4. Database Schema Migration Plan

1. **Normalized PostgreSQL Schema**:
   All 169 tables from `zendoc/db.py` are mapped into clean, strongly typed PostgreSQL schemas under `supabase/migrations/`.
2. **Identity Harmonization**:
   Legacy `users` table maps to `auth.users` in Supabase Auth, with a public profile extension `public.profiles` storing role, phone, KYC status, and preferences.
3. **Primary Key Standardization**:
   Standardize on `UUID DEFAULT gen_random_uuid()` for all primary keys (with backward-compatible integer aliases where required by foreign keys).
4. **Audit and Timestamps**:
   Every table implements `created_at TIMESTAMPTZ DEFAULT now()` and `updated_at TIMESTAMPTZ DEFAULT now()`.
5. **PostGIS Support**:
   Enable `postgis` extension in Supabase for high-performance geospatial nearest-provider queries, eliminating brittle in-memory haversine calculations.

---

## 5. Security & Migration Risk Safeguards

- **No Real Patient Data in Git**: Migrations operate exclusively with synthetic, anonymized test fixtures.
- **Rollback Readiness**: All SQL migrations are paired with idempotent `DROP` / down-migration definitions.
- **Continuous Gate Checking**: Rebuild components undergo strict TypeScript build verification (`npm run build`) and Vitest test execution before any milestone is considered complete.
