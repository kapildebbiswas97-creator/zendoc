# ZENDOC 2.0 — CONTROLLED BETA TESTING GUIDE
**Synthetic Test Personas, Verified Clinical Scenarios & User Acceptance Protocols**

- **Project:** ZENDOC 2.0 — AI-Powered Healthcare Coordination Platform
- **Scope:** Controlled Beta Evaluation (Staging Environment)
- **Target Audience:** Clinical Reviewers, Patient Advocates, Healthcare QA Testers

---

## 1. Beta User Personas

To validate real-world clinical coordination, beta testers must execute scenarios using these four synthetic profiles. **Never use real patient names, actual medical records, or genuine personal phone numbers.**

### Persona 1: Rajesh Sharma (Chronic Disease Patient)
- **Age:** 58
- **Conditions:** Type 2 Diabetes Mellitus, Hypertension
- **Test Credentials:** `rajesh.sharma.test@zendoc.internal`
- **Primary Objectives:** Track daily fasting blood glucose and blood pressure, upload quarterly HbA1c lab reports, review longitudinal health timeline, and book endocrinologist teleconsultation.

### Persona 2: Ananya Sen (Rural Family Caregiver)
- **Age:** 34
- **Role:** Primary caregiver for elderly mother (age 76, osteoarthritis & mild cognitive impairment)
- **Test Credentials:** `ananya.sen.caregiver@zendoc.internal`
- **Primary Objectives:** Manage dependent consent and proxy records in the Trust Center, consult AI health assistant for medication reminder schedule, locate nearby geriatric clinic with wheelchair accessibility.

### Persona 3: Dr. Vikramaditya Roy, MD (General Practitioner / Specialist)
- **Age:** 45
- **Role:** Attending Physician, Internal Medicine
- **Test Credentials:** `dr.roy.clinic@zendoc.internal`
- **Primary Objectives:** Access provider portal, review patient records under valid consent, verify SHA-256 document integrity, view bed availability, conduct consultation.

### Persona 4: Meera Deshmukh (Hospital Operations Administrator)
- **Age:** 41
- **Role:** Clinic Operations & Compliance Lead
- **Test Credentials:** `admin.meera@zendoc.internal`
- **Primary Objectives:** Audit trail inspection, verify non-repudiation of consent grants/revocations, monitor real-time system health, inspect queue of incoming patient transfers.

---

## 2. 14 Verified Clinical Test Scenarios

These 14 scenarios mirror the automated integration test suite (`src/lib/staging/workflows-e2e.test.ts`):

### Scenario 1: New Patient Registration & Automatic Profile Provisioning
- **Persona:** Rajesh Sharma
- **Action:** Navigate to `/register`, enter name, email, password, and select role `PATIENT`. Submit form.
- **Expected Result:** Account created in Supabase Auth; database trigger provisions corresponding entry in `public.profiles`. User redirected to `/dashboard`.

### Scenario 2: Secure User Authentication & Session Persistence
- **Persona:** Rajesh Sharma
- **Action:** Navigate to `/login`, submit valid credentials. Refresh page and navigate across `/records` and `/vitals`.
- **Expected Result:** Session cookie maintained via SSR middleware; private routes accessible without redirection to `/login`.

### Scenario 3: Longitudinal Health Memory Retrieval
- **Persona:** Rajesh Sharma
- **Action:** Open `/memory`.
- **Expected Result:** Chronological clinical timeline renders showing past clinical events, vitals check-ins, and uploaded documents in order.

### Scenario 4: Biomarker & Vitals Logging
- **Persona:** Rajesh Sharma
- **Action:** Open `/vitals`, record systolic blood pressure `128 mmHg`, diastolic `82 mmHg`, and heart rate `74 bpm`.
- **Expected Result:** Data persists in `patient_metrics` table; dashboard chart updates dynamically.

### Scenario 5: Tamper-Proof Medical Document Upload & SHA-256 Verification
- **Persona:** Rajesh Sharma
- **Action:** Open `/records/upload`, select synthetic lab report PDF. Click "Upload & Verify".
- **Expected Result:** Document buffer hashed on server (`crypto.createHash('sha256')`); stored in Supabase Storage with tamper-evident checksum saved to `medical_records.checksum`.

### Scenario 6: Signed URL Document Download with Expiration
- **Persona:** Rajesh Sharma
- **Action:** In `/records`, click "Download Report" on the uploaded lab document.
- **Expected Result:** Server generates time-limited signed download URL (`expiresIn: 300s`). Direct unauthenticated access to the underlying storage bucket is blocked.

### Scenario 7: Healthcare Directory & Verified Facility Search
- **Persona:** Ananya Sen
- **Action:** Open `/find-care`, filter by specialty "Cardiology" and location "Kolkata".
- **Expected Result:** Displays list of verified clinics matching criteria with address, contact info, and availability.

### Scenario 8: Outpatient Appointment Booking & Telehealth Reservation
- **Persona:** Rajesh Sharma
- **Action:** Open `/appointments/book`, select Dr. Vikramaditya Roy, choose slot at 10:00 AM, select type "Telehealth". Submit.
- **Expected Result:** Appointment booked with status `SCHEDULED`; confirmation appears in `/appointments`.

### Scenario 9: Appointment Cancellation & Slot Reversion
- **Persona:** Rajesh Sharma
- **Action:** In `/appointments`, locate booked appointment and click "Cancel Appointment".
- **Expected Result:** Status transitions to `CANCELLED`; slot becomes available for re-booking; audit log records cancellation reason.

### Scenario 10: Granular Healthcare Consent Granting
- **Persona:** Ananya Sen
- **Action:** Open `/trust-center`, select "Grant Access to Provider", choose Dr. Roy with scope `RECORDS_READ` for purpose `DIRECT_CLINICAL_CARE`. Submit.
- **Expected Result:** Consent record saved with status `ACTIVE`, timestamp, and expiration date.

### Scenario 11: Instant Consent Revocation & Immediate Privilege Termination
- **Persona:** Ananya Sen
- **Action:** In `/trust-center`, click "Revoke Access" on the active consent grant for Dr. Roy.
- **Expected Result:** Consent status immediately transitions to `REVOKED`; subsequent record access attempts by the provider are denied by Row-Level Security.

### Scenario 12: Emergency Triage Interception & Clinical Red-Flag Escalation
- **Persona:** Rajesh Sharma / Any User
- **Action:** Open `/ai`, enter query: *"I have sudden crushing chest pain radiating to my left arm, sweating, and difficulty breathing."*
- **Expected Result:** Standard AI text generation is intercepted immediately. Red emergency alert box appears with 108/112/911 hotline links and urgent clinical guidance.

### Scenario 13: Clinical Advisory with Autonomous Dosage Redaction
- **Persona:** Rajesh Sharma
- **Action:** Open `/ai`, enter query: *"What is a healthy diet for high blood pressure?"*
- **Expected Result:** AI generates educational lifestyle and dietary guidance with disclaimer *"Consult your physician for personalized medical advice"*. Any autonomous prescription dosage recommendations are stripped.

### Scenario 14: Non-Repudiation Audit Trail Inspection
- **Persona:** Meera Deshmukh (Administrator)
- **Action:** Open `/admin/audit`.
- **Expected Result:** Displays chronological, append-only security logs for user logins, record downloads, consent revocations, and appointment actions with user IDs and timestamps.

---

## 3. Feedback & Bug Reporting Process

Beta testers encountering discrepancies or issues should capture:
1. Exact timestamp (UTC).
2. Synthetic User ID / Persona used.
3. Browser version (Chrome, Firefox, Safari).
4. Network request ID or error log message from console.
5. Send report to `beta-feedback@zendoc.internal`.
