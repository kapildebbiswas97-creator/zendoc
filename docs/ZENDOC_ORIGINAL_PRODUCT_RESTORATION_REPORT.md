# ZENDOC — Original Product Restoration & Verification Report

**Date:** 2026-11-08  
**Restored Branch:** `restore/original-zendoc`  
**Base Commit SHA:** `545fc35758f749b46779c41e729d55667fc2118a`  
**Commit Message:** `Merge pull request #142 from kapildebbiswas97-creator/repair/production-readiness-beta-20261014`  
**ZENDOC 2.0 Backup Branch:** `rebuild/zendoc-2.0-vercel` (HEAD: `ff22072`)  
**Main Branch Status:** `545fc35758f749b46779c41e729d55667fc2118a` — **100% UNTOUCHED**  
**Working Tree Status:** Clean  

---

## 1. Executive Summary

As instructed, the original ZENDOC application has been restored as the primary product. The Next.js 2.0 rebuild has been preserved intact as a reference/backup on branch `rebuild/zendoc-2.0-vercel`.

The original ZENDOC application is not a mockup: it is a comprehensive, production-grade Python/Flask application featuring **275 Python modules in `zendoc/`**, **582 registered HTTP endpoints**, **70+ Jinja2 templates styled with Google Stitch**, **dual-engine database support (SQLite + PostgreSQL 16)**, and **1,491 automated tests across 255 test files**.

The application was restored onto dedicated branch `restore/original-zendoc`, verified against its automated test suite (117/117 targeted tests passing in 100% green status), launched on a local live server (`http://127.0.0.1:5000`), and verified via end-to-end HTTP registration, authentication, dashboard, Health Memory, and records flows.

---

## 2. Commit & History Audit

| Branch | Latest Commit | Description | Role |
|---|---|---|---|
| `restore/original-zendoc` | `df3feb0` (on `545fc35`) | Original full-stack Python/Flask ZENDOC application | **PRIMARY PRODUCT** |
| `main` | `545fc35` | PR #142 merged Oct 22, 2026 | **UNTOUCHED BASELINE** |
| `rebuild/zendoc-2.0-vercel` | `ff22072` | Next.js 15 App Router + Supabase rebuild | **BACKUP / REFERENCE** |

### Last Known Good Original Commit
- **SHA:** `545fc35758f749b46779c41e729d55667fc2118a`
- **Date:** Thu Oct 22 13:51:25 2026 +0530
- **Author:** Kapil Deb Biswas <kapildebbiswas97@gmail.com>
- **Subject:** `Merge pull request #142 from kapildebbiswas97-creator/repair/production-readiness-beta-20261014`
- **Child Commits Included:** `efd05fe` (harden beta invitations, PostgreSQL and production readiness), `18ce434` (consolidated AWS, security and Stitch frontend release #138).

---

## 3. Architecture & Functional Components

### 3.1 Backend Architecture
- **Framework:** Python 3.11/3.12 Flask Monolith (`run.py` -> `zendoc.create_app()`)
- **Modules:** 275 core modules inside `zendoc/`
- **Endpoint Count:** 582 distinct URL rules registered in `app.url_map`
- **Database Architecture:** Dual-engine architecture in `zendoc/db.py`:
  - **SQLite:** WAL mode with foreign keys enabled, used for local development, testing, and zero-dependency operation (`instance/zendoc.sqlite`).
  - **PostgreSQL 16:** Managed production backend via `psycopg` with connection pooling (`connect_postgresql`).

### 3.2 Frontend Architecture
- **Rendering:** Server-Side Rendered (SSR) Jinja2 templates (70+ templates in `templates/`).
- **Design System:** Google Stitch Visual Refresh (`static/stitch-refresh.css`, `static/style.css`, `static/ui-polish.css`, `static/product-expansion.css`).
- **Interactive UI Modules:**
  - `static/app.js` (core application interactions)
  - `static/finder.js` (healthcare provider & facility search with radius & filters)
  - `static/calls.js` & `static/incoming_calls.js` (WebRTC telemedicine signaling)
  - `static/copilot.js` (clinical AI copilot dock)
  - `static/edgecare_voice.js` & `static/mental_wellness_voice.js` (voice AI interfaces)
  - `static/pose_coach.js` (physical therapy pose tracking)
  - `static/pwa.js` & `static/sw.js` (Progressive Web App offline support)

### 3.3 Core Capabilities Preserved

| Capability | Implementing Modules | Verification |
|---|---|---|
| **Health Memory & RAG** | `zendoc/health_memory_continuity.py`, `zendoc/health_memory_rag.py` | Verified (200 OK on `/timeline`, 24 tests passing) |
| **FHIR & Interoperability** | `zendoc/interoperability_gateway.py`, `zendoc/interoperability_routes.py` | Verified (endpoints registered, routes active) |
| **Patient Records & OCR** | `zendoc/record_storage.py`, `zendoc/report_intelligence.py` | Verified (200 OK on `/records`, download routes active) |
| **AI Agents & Orchestration** | `zendoc/orchestrator.py`, `zendoc/specialist_orchestrator.py`, `zendoc/agent_os.py` | Verified (200 OK on `/agent-os`, `/admin/agent-command-center`) |
| **Care OS & Care Journeys** | `zendoc/care_os_routes.py`, `zendoc/care_journey_routes.py` | Verified (200 OK on `/care-os`) |
| **Provider Discovery & Find Care** | `zendoc/healthcare_finder.py`, `zendoc/places_provider.py` | Verified (Stitch finder active) |
| **Appointments & Telehealth** | `zendoc/telehealth.py`, `zendoc/call_signaling.py`, `zendoc/call_routes.py` | Verified (200 OK on `/appointments`) |
| **Pharmacy & Orders** | `zendoc/pharmacy_service.py`, `zendoc/pharmacy_order_routes.py` | Verified (200 OK on `/pharmacy`) |
| **Connected Care Diagnostics** | `zendoc/connected_care_routes.py`, `zendoc/home_health.py` | Verified (200 OK on `/connected-care`) |
| **Audit Trails & Compliance** | `zendoc/audit_logs.py`, `zendoc/policy_acceptance.py` | Verified (strict privacy acceptance required on signup) |
| **Patient Consent Control** | `zendoc/health_access.py` (`ensure_consent_schema`) | Verified (`test_consent_purpose_v1.py` passing) |
| **Role-Based Security** | `zendoc/security.py`, `zendoc/security_headers.py` | Verified (403 on admin routes for patients) |

---

## 4. Test Verification Results

### Summary: 117 / 117 Tests Passed (100% Green)

| Test Gate | Suite / File | Tests Run | Result | Duration |
|---|---|---|---|---|
| **Critical Safety & Security** | `test_security_hardening_v3.py`, `test_provider_permission_matrix_v1.py`, `test_workflow_state_integrity_v1.py`, `test_concurrency_integrity_v1.py`, `test_database_reliability_v1.py`, `test_careloop_consent_scope_boundary.py`, `test_health_memory_rag_v1.py`, `test_public_launch_v1.py`, `test_telehealth_truth_v1.py`, `test_policy_acceptance_v1.py` | 81 | ✅ **81 / 81 PASSED** | 102.95s |
| **Domain Clinical Features** | `test_health_memory_2_v1.py`, `test_agent_autonomy_v1.py`, `test_pharmacy_truth_v1.py`, `test_diagnostics_v2.py`, `test_consent_purpose_v1.py` | 24 | ✅ **24 / 24 PASSED** | 19.78s |
| **Admin & Owner QA Gate** | `test_admin_dashboard_preview_v1.py` | 6 | ✅ **6 / 6 PASSED** | 5.67s |
| **Gateway Contract Gate** | `test_vercel_oci_gateway_v2.py` | 5 | ✅ **5 / 5 PASSED** | 0.12s |
| **Full-Stack Smoke Flow** | `test_smoke.py` | 1 | ✅ **1 / 1 PASSED** | 2.78s |
| **Total Targeted Verification** | — | **117** | ✅ **117 / 117 PASSED** | — |

*Repository contains 1,491 total automated test cases collected across 255 test files.*

---

## 5. Live Application Verification (End-to-End HTTP)

The original Flask server was started and tested against live HTTP requests on `http://127.0.0.1:5000`:

```
1. GET /api/v1/health          -> 200 OK {"check":"liveness","service":"zendoc","status":"ok"}
2. GET /                       -> 200 OK (29,326 bytes HTML, title: "ZENDOC — One Connected Healthcare Journey")
3. GET /static/stitch-refresh.css -> 200 OK (28,456 bytes)
4. GET /static/app.js          -> 200 OK (12,350 bytes)
5. GET /register/patient       -> 200 OK (CSRF token generated & extracted)
6. POST /register/patient      -> 302 Redirect to /login/patient (compliance checkboxes accepted)
7. POST /login/patient         -> 302 Redirect to /dashboard (session cookie authenticated)
8. GET /dashboard              -> 200 OK (Authenticated user banner verified)
9. GET /timeline               -> 200 OK (Health Memory timeline active)
10. GET /appointments          -> 200 OK (Appointments view active)
11. GET /records               -> 200 OK (Medical records store active)
12. GET /care-os               -> 200 OK (Care OS clinical workflow active)
13. GET /agent-os              -> 200 OK (Agent OS autonomous routing active)
```

---

## 6. Deployment Architecture & Preview Comparison

### Comparison of Available Deployments

| Property | Original ZENDOC (Restored) | ZENDOC 2.0 (Backup Reference) |
|---|---|---|
| **Branch** | `restore/original-zendoc` | `rebuild/zendoc-2.0-vercel` |
| **Architecture** | Full-Stack Python/Flask Monolith + PostgreSQL 16 / SQLite | Next.js 15 App Router + Supabase PostgreSQL |
| **Backend** | Real Python backend, 275 modules, 582 routes | Next.js Server Actions + Supabase RLS |
| **Frontend** | Google Stitch CSS + SSR Jinja2 templates (70+ pages) | Tailwind CSS + React 19 Client/Server Components |
| **Local Preview URL** | **`http://127.0.0.1:5000`** (Live now) | `http://localhost:3000` (via `npm run dev`) |
| **Cloud Preview URL** | AWS EC2 / OCI origin via Vercel Gateway (`vercel.ts`) | `https://kapildebbiswas97-creator-zendoc-2eeh0ir9m.vercel.app` |
| **Deployment Guard** | `git: { deploymentEnabled: false }` in `vercel.ts` prevents unverified broken builds | Automatic Vercel Git deployments |

---

## 7. Next Steps & Operating Instructions

1. **Local Access:**
   The original application is running live at:
   `http://127.0.0.1:5000`
   Open this URL in any browser to experience the restored application immediately.

2. **Branch Management:**
   - Primary branch for all future work: `restore/original-zendoc`
   - Backup reference branch: `rebuild/zendoc-2.0-vercel`
   - Production branch `main`: Untouched at `545fc35`

3. **Cloud Deployment Options:**
   - **Docker Compose (AWS / OCI):** `cd deploy/aws && docker compose up -d`
   - **Render Web Service:** Uses `Procfile` / `deploy/render-public.example.yaml` (`gunicorn -c gunicorn.conf.py run:app`)
   - **Vercel Gateway:** Configured via `vercel.ts` pointing to `ZENDOC_ORIGIN_URL`.
