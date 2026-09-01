# ZENDOC — Feature Truth Matrix

**Release Target**: Selection Beta  
**Branch**: `main`  
**Evaluation Date**: August 2026  
**Durability & Persistence Status**: Local SQLite Persistence (`WORKING`), Live Managed PostgreSQL Connection (`WORKING` via `DATABASE_URL`), Enterprise Multi-Region HA & Backups (`INTEGRATION REQUIRED`).

---

## 1. Feature Classification Taxonomy

Each capability in ZENDOC is evaluated and classified into one of the following five truthful operational states:

1. **`WORKING`**: Feature is fully implemented, functionally verified, covered by automated test suites, and operates end-to-end with persistent data storage in local/test SQLite.
2. **`BETA`**: Feature is functional in the reference web application with browser-local or deterministic fallbacks when external cloud services (e.g. third-party LLM keys, TURN servers) are not provisioned.
3. **`INTEGRATION REQUIRED`**: Feature provides complete frontend workflows, validation, and database records, but requires external physical infrastructure, live carrier integrations, or merchant fleet agreements for live external execution (e.g., real ambulance dispatch, live pharmacy doorstep delivery).
4. **`PROTOTYPE`**: Working browser-local prototype or UI intake demonstrating user experience and schema design without live AI model evaluation or physical hardware integration (e.g., Fitness Camera Preview).
5. **`FUTURE`**: Long-term roadmap capability scheduled for post-selection development (e.g., native mobile app binary packages, on-device Edge TPU hardware acceleration, autonomous logistics).

---

## 2. Complete Capabilities Truth Matrix

| Domain / Subsystem | Capability / Feature | Classification | Execution Mode & Truthful Description | Verification Method |
| :--- | :--- | :--- | :--- | :--- |
| **Auth & Security** | Multi-Role Registration & Login (Patient, Doctor, Hospital, Pharmacy, Gov) | `WORKING` | Argon2id password hashing, session tokens, role authorization | Automated Tests (`tests/test_final_release_hardening.py`) |
| **Auth & Security** | Email Case & Whitespace Normalization | `WORKING` | Normalizes uppercase/whitespace inputs preventing duplicate account collisions | Automated Tests |
| **Auth & Security** | Owner Isolation & Admin Access Control | `WORKING` | Admin route (`/admin`) restricted exclusively to configured `ADMIN_EMAIL` | Automated Tests |
| **Auth & Security** | CSRF Protection on All Web Forms | `WORKING` | Server-validated CSRF tokens on all POST requests across all 18 templates | Template audit & automated web tests |
| **Auth & Security** | Session Rotation & Logout Invalidation | `WORKING` | Secure cookie rotation on login/logout, legacy GET logout compatibility | Unit & Integration tests |
| **Auth & Security** | Password Reset & Recovery | `BETA` | Local demo recovery token flow; email transport requires SMTP credentials | Web test flow |
| **Database & Durability** | Local SQLite File Persistence | `WORKING` | ACID transactions, foreign keys, write-ahead logging (WAL), table triggers | Full suite restart tests |
| **Database & Durability** | Managed PostgreSQL Backend | `WORKING` | Schema-ordered migrations applied; active for live Render selection deployment via `DATABASE_URL` | Automated Tests & Schema Verification |
| **Database & Durability** | Enterprise Multi-Region HA & Disaster Recovery | `INTEGRATION REQUIRED` | Multi-region failover and automated backups not provisioned in selection tier | Documented Infrastructure Scope |
| **Appointments & Finder** | Healthcare Provider Directory & Filters | `WORKING` | Filter by specialty, city, provider type, ratings, and verified badge | Web & API tests |
| **Appointments & Finder** | Provider Schedule & Slot Management | `WORKING` | Doctors create weekly recurring schedules with custom slot durations | Automated Tests |
| **Appointments & Finder** | Real-Time Slot Booking & Double-Booking Prevention | `WORKING` | Atomic appointment reservation, prevents double-booking same slot | Automated Tests |
| **Appointments & Finder** | Universal Multimodal Search (`/search`) | `WORKING` | Full text search across doctors, medicines, records, workouts, and services | Automated Tests |
| **Clinical Intelligence (AI)** | Deterministic Emergency Triage (Chest Pain, Stroke, Trauma) | `WORKING` | Rule-based safety gate overrides LLM, directs user immediately to 108 / ER | Safety engine test suite |
| **Clinical Intelligence (AI)** | Non-Diagnosis Disclaimer & Refusal on Prescriptions | `WORKING` | Refuses to prescribe Rx medications; provides structured guidance and encourages clinician visits | Intelligence test suite |
| **Clinical Intelligence (AI)** | Multimodal Intent Router (28+ intents) | `WORKING` | Rule-assisted intent routing across health, fitness, family, and ecosystem | Intent test suite |
| **Clinical Intelligence (AI)** | Configurable Cloud LLM Router | `BETA` | Fallback to deterministic engine when cloud API keys (OpenAI/Gemini/Anthropic) are absent | Model router tests |
| **Health Memory** | Medical Records Upload & Storage | `WORKING` | Multi-format record upload (PDF, PNG, JPG, TXT, DOCX) with audit provenance | Storage & access tests |
| **Health Memory** | Health Timeline & Longitudinal History | `WORKING` | Chronological aggregation of visits, uploads, measurements, and workouts | Timeline tests |
| **Health Memory** | Manual Vitals & Metric Logging | `WORKING` | Record BP, heart rate, blood glucose, weight, SpO2 with range validation | Analytics tests |
| **Health Memory** | IDOR Multi-Tenant Privacy Isolation | `WORKING` | Strict RBAC prevents cross-patient record/summary viewing | Automated security tests |
| **Health Memory** | Full Health Data Export (JSON) | `WORKING` | Structured export of health profile, timeline, metrics; sanitizes file paths | Export verification tests |
| **Fitness Coach** | Fitness Profile & Goal Configuration | `WORKING` | Captures experience level, goal, location, equipment, available minutes | Fitness test suite |
| **Fitness Coach** | Personalised Workout Plan Generator | `WORKING` | Algorithmic plan generation based on user constraints and muscle focus | Automated Tests |
| **Fitness Coach** | Interactive Workout Session & Set Logger | `WORKING` | Live set/rep logging, timer tracking, automatic timeline recording | Automated Tests |
| **Fitness Coach** | Nutrition & Meal Logging | `WORKING` | Food, macro, and calorie tracking without fabricated calorie claims | Automated Tests |
| **Fitness Coach** | Daily Hydration Tracker | `WORKING` | Quick-log presets (250ml, 500ml, 750ml) with daily wellness target progress | Automated Tests |
| **Camera & Video** | Fitness Camera Preview Prototype | `PROTOTYPE` | Browser-local camera preview and duration capture; automatic pose analysis and rep counting not connected | Camera test suite |
| **Camera & Video** | Curated Educational Exercise Videos | `BETA` | Searches verified educational fitness videos; graceful offline fallback | Video search tests |
| **Family Care** | Family Member & Dependent Management | `WORKING` | Add parents, children, spouse with proxy permissions and emergency flags | Family test suite |
| **Family Care** | Care Tasks & Medication Reminders | `WORKING` | Assign and mark completed care tasks for dependents | Automated Tests |
| **Family Care** | Remote Parent Care Dashboard | `WORKING` | Single-pane monitoring of elderly parent vitals, tasks, and alert triggers | Remote parent tests |
| **ZENDOC Connect** | Permission-Governed Direct Messaging | `WORKING` | Patient-doctor and doctor-doctor messaging with strict privacy controls | Connect test suite |
| **ZENDOC Connect** | Doctor Availability & Message Policies | `WORKING` | Doctors control online/busy/offline status and accepted message scopes | Telehealth tests |
| **ZENDOC Connect** | WebRTC Consultation Rooms | `BETA` | Real-time audio/video room creation; local WebRTC demo mode in browser | Telehealth detail tests |
| **Connected Ecosystem** | IoT Health Device Hub & Sync | `WORKING` | Register BP monitors, smartwatches, glucometers; records provenance as `device` | IoT Hub tests |
| **Connected Ecosystem** | Pharmacy Medicine Catalog Search | `WORKING` | Search OTC and Rx medicines with clinical usage and dosage notes | Pharmacy tests |
| **Connected Ecosystem** | Refill & Dosage Reminders | `WORKING` | Schedule recurring daily/weekly medicine reminders with push alerts | Reminders tests |
| **Connected Ecosystem** | Doorstep Medicine Delivery | `INTEGRATION REQUIRED` | Order creation with delivery address; requires pharmacy logistics partner API | Ecosystem tests |
| **Connected Ecosystem** | Medical Transport & Ambulance Booking | `INTEGRATION REQUIRED` | Request BLS, ICU van, wheelchair transport; requires live dispatch fleet API | Transport tests |
| **Connected Ecosystem** | Doorstep Home Healthcare Booking | `INTEGRATION REQUIRED` | Book nurse, physiotherapist, elder attendant visits; requires clinician staffing API | Home health tests |
| **Owner Command Center** | Model Evaluation Lab | `WORKING` | Multi-candidate benchmark engine with strict two-step confirmation for local models | Evaluation Lab tests |
| **Owner Command Center** | Real-Time Operations Monitoring | `WORKING` | System health, database connection metrics, queue latencies, audit log stream | Command Center tests |
| **Owner Command Center** | Role Management & Provider Verification | `WORKING` | Owner review and verification workflow for registered doctors and clinics | Admin tests |

---

## 3. Truthful Testing Disclosure Summary

- **Local/Test Environment**: 100% of capabilities function reliably using SQLite.
- **Production Server (Render Selection Beta)**: Connected to managed PostgreSQL database via `DATABASE_URL` with ordered schema migrations applied. Application state persists across service lifecycles. Temporary web service sleep/cold-start characteristics after prolonged inactivity remain disclosed.
- **No Deceptive Demos**: ZENDOC does not simulate fake ambulance dispatches, fake camera AI detections, or fake payment confirmations. All external execution boundaries are truthfully labeled.
