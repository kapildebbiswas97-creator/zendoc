# ZENDOC 2.0 â€” Healthcare Security, Privacy & Safety Architecture

**Product:** ZENDOC 2.0  
**Document version:** 2.0.0  
**Security Standard:** HIPAA, GDPR, DISHA (India), and OWASP Top 10 Aligned  
**Status:** Mandatory Production Specification  

---

## 1. Security Philosophy & Mandate

Healthcare information is among the most sensitive data in human society. A data leak, unauthorized access, or algorithmic hallucination can cause catastrophic financial, legal, physical, and psychological harm. 

In ZENDOC 2.0:
- **Safety and Privacy Overrule Speed**: No feature is deployed without tenant isolation, role verification, and consent checks.
- **Zero Trust by Default**: Every request to an API route, Server Action, or database table must be authenticated, authorized, and audited.
- **Defense in Depth**: Client-side guards, Server Action middleware, and Supabase Database Row Level Security (RLS) enforce identical security barriers simultaneously.

---

## 2. Authentication & Identity Management

### 2.1 Identity Provider (Supabase Auth SSR)
- Authentication is governed by Supabase Auth using cryptographically signed JSON Web Tokens (JWT).
- Tokens are stored exclusively in `HttpOnly`, `Secure`, `SameSite=Lax` browser cookies managed by `@supabase/ssr`.
- Tokens are never exposed to browser `localStorage` or `sessionStorage` to eliminate cross-site scripting (XSS) credential theft.

### 2.2 Password & Lifecycle Security
- Passwords are salted and hashed using Argon2 or PBKDF2 with high iteration counts on the Supabase authentication server.
- Passwords must meet complexity requirements (minimum 10 characters, upper, lower, numeric, and symbol).
- Secure password recovery using single-use, time-limited cryptographic reset tokens delivered to verified email addresses.
- Rate limiting on login, registration, and password recovery endpoints:
  - Global IP rate limit: 120 requests/minute.
  - Auth route rate limit: 10 requests/minute per IP to defeat brute-force and credential stuffing attacks.

### 2.3 Session Lifecycle & Expiry
- Access tokens expire after **60 minutes**.
- Refresh tokens expire after **30 days** or upon explicit user sign-out.
- Idle session timeout: **120 minutes** of inactivity prompts re-authentication for protected clinical and financial screens.
- Global sign-out revokes all active refresh tokens across all devices simultaneously.

---

## 3. Authorization & Role-Based Access Control (RBAC)

### 3.1 Core Roles
ZENDOC 2.0 defines five strict, non-overlapping roles:

| Role | Definition & Authority Scope |
|---|---|
| `patient` | Accesses own medical records, vitals, appointments, family dependents, and consultations. |
| `provider` | Verified clinician, nurse, or therapist. Accesses assigned patient records under active clinical consent. Manages availability and consultation notes. |
| `org_admin` | Healthcare facility manager (hospital/clinic). Manages staff, clinic sites, bed boards, and aggregated operational reporting. Cannot view private clinical records without patient consent. |
| `platform_admin` | Platform owner and compliance officer. Accesses system health, audit logs, provider verification evidence, and incident reports. Banned from casual patient record viewing. |
| `caregiver` | Authorized proxy (family member/guardian) granted explicit, revocable surrogate access to a dependent's records. |

### 3.2 Insecure Direct Object Reference (IDOR) Elimination
No user can access or manipulate a record simply by providing another user's ID in a URL or payload:
- **Server Action Validation**: The server checks that `session.user.id` matches the target resource owner, OR that an active, valid record exists in `consent_grants` or `family_access_grants`.
- **Database Row Level Security (RLS)**: Even if an application bug bypasses server-side code, PostgreSQL RLS blocks the SQL query at the database engine level.

---

## 4. Consent Engine & Data Sharing

Consent is an active, granular, time-bounded, and revocable legal instrument in ZENDOC:

### 4.1 Consent Taxonomy (`consent_grants` table)
Every consent grant records:
1. `grantor_id`: The patient granting permission.
2. `grantee_id`: The recipient (doctor, family caregiver, or research program).
3. `purpose`: Machine-readable purpose (e.g. `CLINICAL_CONSULTATION`, `FAMILY_CARE`, `EMERGENCY_ACCESS`, `AI_CONTEXT_SUMMARIZATION`).
4. `scope`: Granular data bundle (`FULL_RECORD`, `MEDICATIONS_ONLY`, `LABS_ONLY`, `METADATA_ONLY`).
5. `valid_until`: Mandatory expiration timestamp.
6. `status`: `ACTIVE`, `REVOKED`, or `EXPIRED`.

### 4.2 Instant Revocation via Trust Center
- Patients can view all active and historical consent grants at `/patient/trust-center`.
- Revoking a consent grant takes immediate effect across all active sessions, APIs, and database queries.
- When revoked, providers immediately lose access to the patient's records; ongoing cached data contexts are flushed.

---

## 5. Medical Document & Storage Security

### 5.1 Storage Architecture
All health records (PDF lab reports, imaging scans, prescription slips, doctor notes) are stored in private Supabase Storage buckets:
- `medical-records`
- `lab-reports`
- `prescriptions`
- `consultation-attachments`

### 5.2 Storage Access Protocol
1. **No Public URLs**: Direct bucket URLs return `403 Forbidden`.
2. **Ephemeral Signed URLs**: Downloads require generating a short-lived signed URL (valid for **5 minutes**) created only after authenticating the caller and verifying active clinical consent.
3. **Upload Validation**:
   - Strictly enforced MIME types: `application/pdf`, `image/jpeg`, `image/png`, `image/webp`. Executables, scripts, HTML, and ZIP files are rejected.
   - Max file size: **10 MB** per document.
   - Files are stored with content-addressed SHA-256 hashes to guarantee data integrity and detect tampering.

---

## 6. Audit Logging & Data Provenance

### 6.1 Immutable Audit Log (`audit_logs` table)
Every read, write, update, delete, and AI summarization of personal health information creates an append-only row in `audit_logs`:
- `actor_id`: User initiating the action.
- `target_user_id`: Patient whose record was accessed.
- `action`: `VIEW_RECORD`, `DOWNLOAD_ATTACHMENT`, `CREATE_PRESCRIPTION`, `AI_SUMMARIZE`, etc.
- `resource_type` and `resource_id`: Exact entity referenced.
- `authorization_source`: Role claim or `consent_grant_id`.
- `ip_address` & `user_agent`: Network origin (truncated for privacy where required).
- `timestamp`: UTC timestamp with microsecond resolution.

### 6.2 Data Provenance Tracking
Every clinical fact in the Health Memory timeline carries an immutable `provenance` tag:
- `USER_REPORTED`: Self-entered by patient (e.g. at-home blood pressure).
- `PROVIDER_RECORDED`: Authored and signed by a verified clinician during an encounter.
- `DOCUMENT_EXTRACTED`: Parsed from an uploaded diagnostic report or discharge summary.
- `DEVICE_RECORDED`: Ingested directly from a certified Bluetooth/IoT medical device.

Ordinary application logs (stdout/stderr) are strictly scrubbed of patient names, medical conditions, medication lists, passwords, and authorization tokens.

---

## 7. AI Safety & Clinical Risk Governance

### 7.1 Deterministic Emergency Triage Gate
Prior to sending any user query to an AI model, the input is evaluated by a deterministic, rule-based emergency triage validator.
- If keywords or clinical patterns indicate life-threatening symptoms (e.g., crushing chest pain radiating to left arm, sudden facial drooping or speech slurring, massive hemorrhaging, acute suicidal ideation), the system **aborts AI inference immediately**.
- An emergency diversion modal is triggered with immediate national emergency contact numbers (102, 108, 911, 999) and the nearest emergency trauma center.

### 7.2 Human-in-the-Loop Approval & Plan Hashes
AI agents in ZENDOC cannot execute privileged mutations (e.g. booking an appointment, dispatching a caregiver, requesting medicines) autonomously:
1. The AI model drafts a structured `Plan` containing typed action steps.
2. The server computes a cryptographic SHA-256 hash of the proposed plan (`plan_hash`).
3. The user or clinician reviews the plan and clicks "Confirm & Authorize".
4. The server verifies that the submitted hash matches the recorded plan before executing the idempotent tools.

### 7.3 Model Context Minimization
- The system never feeds a patient's entire longitudinal history to external LLMs.
- Only the specific, minimum-necessary data bundle requested for the clinical objective is assembled.
- Direct identifiers (Name, Phone, Aadhaar/SSN, Address) are redacted and replaced with synthetic session aliases before prompting.

---

## 8. Incident Response & Vulnerability Reporting

- Security vulnerabilities can be reported directly to `security@zendoc.com` or via the platform incident hotline.
- Critical vulnerabilities trigger immediate feature-flag deactivation via the `capability_registry` without requiring full application downtime.
