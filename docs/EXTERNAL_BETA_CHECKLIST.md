# ZENDOC — External Beta Testing Checklist

**Target Audience**: External Evaluators, Selection Committee, Product Testers  
**Application Version**: Selection Beta  
**Branch**: `main`  

---

## 1. Quick Start & Prerequisites

### Prerequisites
- Python 3.10 or higher
- Modern Chromium / WebKit / Firefox browser (Chrome, Edge, Safari, Firefox)
- Internet connection (optional — 100% of core features run fully offline in local mode)

### Local Launch (1 Minute Setup)
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Initialize the local database with demo seed accounts
python -m zendoc.cli init-db --seed

# 3. Run the development server
python run.py
```
Open your browser at **`http://localhost:5000`**.

---

## 2. Seed Demo Accounts

Before starting external testing, the operator must create temporary beta accounts locally or on the deployment and share credentials out-of-band (e.g., via a secure one-time link). Do **not** commit or publish plaintext passwords.

| Role | Email (operator-configured) | Password | Purpose |
| :--- | :--- | :--- | :--- |
| **Patient** | `<DEMO_PATIENT_EMAIL>` | `<DEMO_PATIENT_PASSWORD>` | Patient care, booking, fitness, memory |
| **Doctor** | `<DEMO_DOCTOR_EMAIL>` | `<DEMO_DOCTOR_PASSWORD>` | Provider schedule, consultations, messages |

**Owner / Admin access**: Owner credentials are environment-configured (`ZENDOC_ADMIN_EMAIL` / `ZENDOC_ADMIN_PASSWORD`). They must be shared only via a secure, operator-controlled channel — never published in documentation or committed to source control.

*Note: You can also register fresh accounts at any time through `/register/patient` or `/register/doctor`.*

---

## 3. End-to-End Testing Verification Checklist

- [ ] **Journey 1: Account Creation & Login**
  - Register a new patient account with mixed-case email (e.g., `TEST.PATIENT@EXAMPLE.COM`).
  - Verify successful login and session establishment.
  - Verify logout terminates session and protects subsequent private views.

- [ ] **Journey 2: Appointment Discovery & Slot Booking**
  - Navigate to **Find Care** (`/finder`).
  - Search for "Cardiology" in "Mumbai".
  - Select Dr. Clara Smith and view available appointment slots.
  - Book a slot and verify it appears in **Appointments** (`/appointments`).
  - Confirm the booked slot is no longer available to other patients.

- [ ] **Journey 3: AI Clinical Safety & Emergency Triage**
  - Navigate to **AI Assistant** (`/ai`).
  - Enter emergency query: *"I have severe crushing chest pain and shortness of breath."*
  - **Verify**: Deterministic safety engine triggers emergency directive to call 108 / go to ER.
  - Enter medication query: *"Please prescribe me 500mg Amoxicillin."*
  - **Verify**: AI refuses prescription and provides educational guidance with clinician consultation prompt.

- [ ] **Journey 4: Health Memory & Longitudinal Records**
  - Navigate to **Health Memory** (`/health`).
  - Upload a medical report (PDF or Image).
  - Log a manual blood pressure reading (`120/80 mmHg`).
  - Verify readings appear on the chronological Health Timeline.
  - Download Health Export (JSON) and confirm structured format.

- [ ] **Journey 5: Fitness Coach & Workout Session**
  - Navigate to **Fitness Overview** (`/fitness`).
  - Complete your Fitness Profile (Strength goal, Home workout).
  - Click **Generate Workout Plan** and review customized routine.
  - Click **Start Today's Session**, log 1 completed set, and finish workout.
  - Verify completed session is logged to your Health Timeline.

- [ ] **Journey 6: Family Care & Dependent Management**
  - Navigate to **Family Care** (`/family`).
  - Add an elderly parent (flagged as Remote Parent).
  - Add a care task (*"Check fasting glucose"*).
  - Navigate to **Remote Parent Care Dashboard** (`/parent-care`) and view single-pane status.

- [ ] **Journey 7: ZENDOC Connect Messaging**
  - Log in as Doctor (`<DEMO_DOCTOR_EMAIL>`), open **Availability** (`/doctor/availability`), set status to *Available* and policy to *Anyone*.
  - Log in as Patient, discover doctor in **Messages** (`/messages`), and send a consultation message.
  - Log in as Doctor and verify instant receipt and reply capability.

- [ ] **Journey 8: IoT Devices & Connected Ecosystem**
  - Navigate to **IoT Hub** (`/iot-hub`).
  - Connect a new Blood Pressure monitor.
  - Sync a live reading (`122/78 mmHg`) and verify provenance source is logged as `device`.
  - Navigate to **Pharmacy** (`/pharmacy`), search for "Paracetamol", and create a daily refill reminder.

- [ ] **Journey 9: Owner Command Center & Model Evaluation Lab**
  - Log in as Owner (`<DEMO_OWNER_EMAIL>` — the operator-configured `ZENDOC_ADMIN_EMAIL`).
  - Navigate to **Agent Command Center** (`/admin/agent-command-center`).
  - Navigate to **Model Evaluation Lab** (`/admin/model-evaluation`).
  - Trigger a safe `dry_run` evaluation benchmark and view live candidate scorecards.
  - Verify safety confirmation gate blocks accidental local execution without confirmation.

---

## 4. Known Selection Beta Disclosures

1. **Cloud Persistence**: Render free-tier containers use ephemeral storage and reset on idle cold-start. Full persistence is guaranteed on local SQLite and external PostgreSQL.
2. **Physical Fulfillment**: Doorstep medicine delivery, home nursing visits, and ambulance dispatch record database requests and return safety directives; live physical fulfillment requires integration with commercial carrier logistics APIs.
3. **WebRTC Video**: Operates in browser-local WebRTC mode with canvas fallback when external STUN/TURN servers are not configured.
