# ZENDOC 2.0 — HEALTHCARE APPLICATION SECURITY & PRIVACY REVIEW
**Threat Modeling, Architectural Controls & Vulnerability Assessment**

- **Project:** ZENDOC 2.0 — AI-Powered Healthcare Coordination Platform
- **Standards Examined:** HIPAA Security & Privacy Rules, India DPDP Act 2023, OWASP Top 10 API Security
- **Review Date:** November 7, 2026
- **Lead Security Reviewer:** Healthcare Application Security Engineer & DevSecOps Lead

---

## 1. Security Architecture & Threat Modeling

ZENDOC 2.0 processes sensitive health data (ePHI). The security architecture enforces multi-layered defense-in-depth:

```
[Browser / Mobile Client]
         │
         ▼
[Vercel Edge Gateway] ── (Strict HTTP Headers: nosniff, DENY, HSTS, Permissions-Policy)
         │
         ▼
[Next.js SSR Middleware] ── (Auth Session Verification & Cookie Integrity)
         │
    ┌────┴──────────────────────────────┐
    ▼                                   ▼
[API Routes & Server Actions]    [Emergency Triage Interceptor]
    │ (Distributed Rate Limiting)       │ (0ms bypass: Never blocks emergencies)
    ├─────────────────────────────┐     │
    ▼                             ▼     ▼
[Supabase PostgREST]     [Python Worker Boundary]
    │ (RLS Enforced)              │ (HMAC-SHA256, <60s timestamp window)
    ▼                             ▼
[PostgreSQL Database]    [Whisper ASR / Clinical OCR]
```

---

## 2. Findings & Vulnerability Matrix

| ID | Category | Severity | Finding & Risk Description | Remediation Status |
| :---: | :--- | :---: | :--- | :---: |
| **SEC-01** | **Safety / Availability** | **HIGH** | Emergency triage requests could previously be denied if an IP exceeded the AI chat rate limiter. | **RESOLVED** — Emergency triage check now evaluates *before* rate-limiting. Emergencies bypass rate limits. |
| **SEC-02** | **Privacy / Leakage** | **MEDIUM** | Standard logger could leak national IDs (Aadhaar, SSN), credit cards, or session cookies into logs. | **RESOLVED** — Implemented regex de-identification in `src/lib/monitoring/logger.ts`. |
| **SEC-03** | **Integrity / Tampering** | **HIGH** | Uploaded medical documents could potentially be modified in transit without detection. | **RESOLVED** — Enforced server-side `crypto.createHash('sha256')` checksum recorded in database. |
| **SEC-04** | **Interservice Auth** | **HIGH** | Replay attacks against internal ML/ASR worker endpoints. | **RESOLVED** — Injected 60s timestamp freshness validation and constant-time HMAC-SHA256 (`timingSafeEqual`). |
| **SEC-05** | **Abuse / Resource Depletion**| **MEDIUM** | Serverless endpoints without distributed coordination could be overwhelmed across multiple instances. | **RESOLVED** — Integrated Upstash Redis REST rate limiter with local sliding-window failover. |
| **SEC-06** | **AI Safety / Clinical Risk** | **HIGH** | AI model could provide autonomous prescriptive medication dosages. | **RESOLVED** — Sanitizer strips milligram/microgram dosages and attaches educational disclaimers. |
| **SEC-07** | **Information Disclosure** | **LOW** | Health check endpoint could disclose database connection strings or internal service credentials. | **RESOLVED** — `/api/health` sanitized to return only high-level status flags without sensitive secrets. |

---

## 3. Privacy & De-Identification Safeguards

### 3.1 Automated Safe Harbor Redaction (`logger.ts`)
The platform sanitizes all outgoing logs and metadata using deterministic pattern filters:
- **Email Addresses:** Redacted to `[EMAIL_REDACTED]`.
- **Phone Numbers:** Redacted to `[PHONE_REDACTED]` across 10-digit, 5+5, and international formats.
- **National Identifiers:** Aadhaar numbers redacted to `[AADHAAR_REDACTED]`; SSNs redacted to `[SSN_REDACTED]`.
- **Payment Cards:** 16-digit card sequences redacted to `[CARD_REDACTED]`.
- **Bearer Tokens / Session Cookies:** Redacted to `[TOKEN_REDACTED]`.

### 3.2 Limitations of Automated Regex Redaction
> [!IMPORTANT]
> Regex-based redaction is a necessary defense-in-depth measure, but does **not** guarantee 100% de-identification under HIPAA Expert Determination standards:
> - Free-text medical descriptions (e.g., *"Patient seen at Tata Memorial Hospital on Tuesday by Dr. Sen"*) contain unstructured named entities that regexes cannot capture without clinical Named Entity Recognition (NER).
> - Clinical notes must be stored in encrypted database fields rather than logged to application console drains.
> - Engineers and operators must adhere to least-privilege access protocols and never log raw patient query payloads.

---

## 4. Emergency Triage Safety Invariants

The ZENDOC AI Advisory system enforces three non-negotiable life-safety invariants:
1. **Zero-Latency Deterministic Interception:** Any query matching acute red-flag conditions (crushing chest pain, severe breathing difficulty, seizures, stroke, anaphylaxis, severe burns, poisoning) is intercepted in **0 milliseconds** by deterministic rule sets.
2. **Rate-Limiter Exemption:** A patient in acute distress is **never** denied emergency triage instructions due to rate-limit quotas. Emergency responses consume zero third-party tokens and execute locally.
3. **Autonomous Prescribing Prohibition:** The AI model router strips specific dosages (e.g., "take 500mg paracetamol") and mandates that prescriptions be issued only by licensed healthcare providers.
