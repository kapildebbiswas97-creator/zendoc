# ZENDOC 2.0 — Phase 3 Security Audit & Hardening Report

> Audit Date: 2026-11-08  
> Assessment Scope: Next.js 15 App Router, Supabase SSR Auth & RLS, Python Worker Boundary, AI Advisory Safety  
> Lead Auditor: Principal Healthcare Security Engineer

---

## 1. Executive Summary

ZENDOC 2.0 underwent a comprehensive Phase 3 security evaluation covering authentication, authorization, multi-tenant isolation, cryptographic boundary protection, AI advisory emergency safeguards, and input/output sanitization.

### Security Highlights:
- **Zero Exposed Secrets:** Service-role keys and internal worker secrets are restricted exclusively to server-side environments (`process.env` in Server Actions/Route Handlers).
- **Cryptographic Token Verification:** All calls between Next.js and the Python worker boundary require HMAC-SHA256 signatures generated with `crypto.createHmac` and validated using `timingSafeEqual`.
- **Replay Protection:** Replay window of 60 seconds is enforced with future clock-drift limits (< 5 seconds).
- **Autonomous Prescribing Prevention:** AI Advisory output passes through `sanitizeAIResponse`, which strips specific medication dosages and truncates responses exceeding length constraints.
- **Deterministic Emergency Gate:** Acute life-threatening red-flag patterns bypass generative AI models completely and directly provide verified emergency hotline data.

---

## 2. Threat Modeling & OWASP Top 10 Mapping

| OWASP Vulnerability | Risk Level | ZENDOC 2.0 Mitigation & Verification |
|---|---|---|
| **A01: Broken Access Control (IDOR)** | Critical | Double-layered defense: (1) Supabase Row Level Security (RLS) on all tables ensures `patient_id = auth.uid()`. (2) Server Actions explicitly filter and verify user ownership prior to database mutations. Tested in `api-security.test.ts` & `tenant-isolation.test.ts`. |
| **A02: Cryptographic Failures** | High | Medical document uploads generate an authentic SHA-256 integrity hash (`crypto.createHash('sha256')`). Signed download URLs use temporary 5-minute time-to-live (TTL). Internal worker proxies authenticate with HMAC-SHA256. |
| **A03: Injection (SQL / Command / XSS)** | High | Supabase PostgREST uses strictly parameterized queries. Next.js App Router enforces JSX auto-escaping for HTML elements. No `eval()`, raw shell execution, or unsanitized dynamic SQL is permitted. |
| **A04: Insecure Design (AI Safety)** | High | Pre-inference deterministic triage gate checks 25+ life-threatening medical emergency patterns (cardiac, stroke, seizure, DKA, anaphylaxis, choking). Generative completion is aborted when an emergency is flagged. |
| **A05: Security Misconfiguration** | Medium | `poweredByHeader: false` configured in `next.config.ts`. Security headers enforced in Next.js middleware. Supabase anonymous key is separated from privileged service-role credentials. |
| **A06: Vulnerable & Outdated Components** | Medium | Playwright and Vitest packages are pinned to stable releases. Known minor dev-dependency advisories documented in known limitations without destabilizing production builds. |
| **A07: Identification & Authentication Failures** | High | Password policies require a minimum of 10 characters with complexity checks. Email link verification via `/api/auth/callback` handles code-for-session exchange securely on the server. |
| **A08: Software and Data Integrity Failures** | Medium | SHA-256 hash stored alongside document metadata. Files are scanned for MIME allowlisting (PDF, DICOM, JPEG, PNG, WEBP, HEIC) with a strict 25 MB payload ceiling. |
| **A09: Security Logging and Monitoring Failures** | Medium | Append-only `audit_logs` table records actor ID, resource type, IP address, and timestamp. System logs do not record secrets, tokens, or plaintext patient health identifiers (PHI). |
| **A10: Server-Side Request Forgery (SSRF)** | High | The Python worker URL is strictly validated against internal environment configuration (`PYTHON_WORKER_URL`), preventing arbitrary outbound HTTP proxying. |

---

## 3. Worker Boundary Cryptographic Contract

Requests from Next.js to the Python Whisper / OCR worker require the following headers:
- `X-Zendoc-Timestamp`: Current epoch milliseconds.
- `X-Zendoc-User-Id`: Authenticated user UUID.
- `X-Zendoc-Hmac`: `HMAC-SHA256(secret, timestamp + ":" + userId)`.

Verification steps:
1. Timestamp age $> 60,000$ ms $\implies$ **Rejected (HTTP 401 Replay Attack)**.
2. Timestamp future drift $> 5,000$ ms $\implies$ **Rejected (HTTP 401 Clock Anomaly)**.
3. Computed HMAC $\neq$ Received HMAC (via `timingSafeEqual`) $\implies$ **Rejected (HTTP 401 Invalid Token)**.

---

## 4. AI Advisory Clinical Safeguards

### Red-Flag Emergency Triage:
If any of the following patterns are detected in the user's prompt:
- Cardiac: Crushing chest pain, radiating pain, heart attack, chest pressure.
- Neurological: Sudden numbness/weakness, facial drooping, slurred speech, worst headache of life.
- Respiratory: Inability to breathe, stridor, turning blue, severe dyspnea.
- Seizures: Active seizure, convulsions.
- Airway: Choking, throat closing, anaphylaxis, face/tongue swelling, inability to swallow.
- Other: DKA, unconscious/unresponsive, near-drowning, severe chemical/electrical burns, massive hemorrhage, suicidal ideation.

**Action:**
1. AI model query is completely bypassed.
2. Emergency hotline numbers (`102`, `108`, `112`, `911`, `999`) are prominently returned.
3. Urgent directive to contact emergency services or visit the nearest trauma center is generated.

### Output Sanitization:
- Medication dosages (e.g. `500 mg`, `10 ml`) are stripped and replaced with `[dosage omitted — consult your prescriber]`.
- Output is length-bounded to 2000 characters.
- Every response carries the mandatory educational disclaimer.

---

## 5. Outstanding Items & Staging Prerequisites
1. **Live RLS Penetration Testing:** Must be executed against a live Supabase project instance once staging database credentials are provided.
2. **WebRTC TURN Server Deployment:** Production video consultations require a managed STUN/TURN server (e.g. Twilio / Metered) with short-lived credentials.
3. **SMS OTP Gateway:** Provider and emergency verification workflows require integration with an approved SMS/WhatsApp gateway.
