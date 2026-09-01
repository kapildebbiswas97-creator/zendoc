# ZENDOC — Final Pre-Selection Video Demonstration Runbook

**Target Audience**: Hackathon Selection Committee, Venture Capital Evaluators, Healthcare Mentors  
**Platform Version**: Selection Beta (Hardened, Connected to Managed PostgreSQL)  
**Target Duration**: 3 to 5 Minutes  
**Demonstration Narrative**: *One Connected Healthcare Journey — From First Symptom to Verified Care, Longitudinal Memory, and Family Coordination.*

---

## 1. Pre-Recording Checklist

- [ ] **Clean Browser Profile**: Open Chrome / Chromium with no personal bookmarks, extensions, or unpinned tabs.
- [ ] **Viewport Resolution**: Set window to standard 1920x1080 (1080p Full HD) or 1366x768. Set browser zoom to 100%.
- [ ] **Dual Windows**:
  - **Window 1 (Patient)**: `http://localhost:5000` (or live Render URL).
  - **Window 2 (Owner / Admin)**: `http://localhost:5000/admin` (pre-authenticated in Incognito or separate window).
- [ ] **Audio Check**: Ensure clear microphone audio with zero background noise.
- [ ] **Notifications Muted**: Disable OS popups, Slack, WhatsApp, and email alerts.
- [ ] **Live Service Pre-Warm**: If using the live Render deployment, issue a request to `/api/v1/health` 2 minutes prior to ensure the web service container is warm.

---

## 2. Accounts & Roles to Use

| Role | Email | Password | Primary Purpose in Video |
| :--- | :--- | :--- | :--- |
| **Patient (Hero Persona)** | `bob@example.com` (synthetic test patient) | `Password123!` | Demonstrates full end-to-end patient journey |
| **Owner / Admin (Ops View)** | Configured `ADMIN_EMAIL` (`owner@zendoc.local`) | Configured `ADMIN_PASSWORD` | Demonstrates Agent Command Center & Governance |

---

## 3. Synthetic Demo Data Verification

Every account, clinician, clinic, and document referenced in this runbook is **100% synthetic demo/test data**:
1. **Patient Profile**: "Bob Patient" (`bob@example.com` — RFC 2606 reserved test domain), Age 34, Mumbai.
2. **Verified Provider**: "Dr. Clara Smith" (`dr.clara@example.com`), Specialty: *Cardiology*, Organization: *City Heart Clinic* (synthetic clinic entity), Address: *123 Medical Center, Mumbai*.
3. **Provider Schedule**: Weekly schedule configured for weekday morning slots (09:00 - 12:00, 30-min intervals).
4. **Health Record**: Sample synthetic CBC Blood Report (PDF or text) in Health Memory with standard reference values.
5. **Family Care Dependent**: "Father (Elderly)", Age 68, with daily medication reminder task.

*Important: Never use real doctors, real clinics, real patient health documents, real phone numbers, or real medical license numbers in the recording.*

---

## 4. Exact Page & Story Sequence

```
[00:00 - 00:35] 1. Homepage & Ecosystem Problem/Solution
      ↓
[00:35 - 01:15] 2. Patient Dashboard & AI Guidance
      ↓
[01:15 - 01:45] 3. Find Care & Doctor Discovery
      ↓
[01:45 - 02:15] 4. Provider Detail & Slot Booking
      ↓
[02:15 - 02:50] 5. Longitudinal Health Memory & Timeline
      ↓
[02:50 - 03:25] 6. Care Continuity (Connect Messages & Telehealth)
      ↓
[03:25 - 04:10] 7. Ecosystem Montage (Family Care, IoT Hub, Fitness)
      ↓
[04:10 - 04:45] 8. Owner Command Center & Agent Governance
      ↓
[04:45 - 05:00] 9. Closing Pitch & Vision
```

---

## 5. Exact Step-by-Step Navigation & Click Path

### Step 1: Homepage & Value Proposition (0:00 - 0:35)
1. Show `http://localhost:5000/` (or live Render root URL).
2. **Highlight**:
   - Headline: *"One Connected Healthcare Journey."*
   - Problem statement: Fragmented healthcare silos.
   - 6 Core Pillars overview.
3. Click **"Sign In to Portal"** -> **"Patient Portal"**.
4. Log in as `bob@example.com` / `Password123!`.

### Step 2: Patient Dashboard & AI Assistant (0:35 - 1:15)
1. Land on **Health Command Center** (`/dashboard`).
2. Point out quick stats, emergency banner with 112/108 directive, and one-tap shortcuts.
3. Click **"Ask ZENDOC AI"** (`/ai`).
4. Enter recommended safe demo prompt (see Section 6).
5. Click **"Send Message"**.
6. Highlight the deterministic safety assessment:
   - Urgency: *Medium*
   - Specialist recommendation: *Primary care clinician / Cardiology*
   - Non-diagnostic disclosure banner.
7. Click the action chip: **"Book a consultation"** (or Find Care).

### Step 3: Healthcare Finder & Provider Discovery (1:15 - 1:45)
1. Automatically redirected to **Find Care** (`/finder?category=doctor&specialty=...`).
2. Point out category selector, radius filter, and verified doctor cards.
3. Locate **Dr. Clara Smith (Cardiology)**.
4. Click **"View profile & availability"** (`/providers/<id>`).

### Step 4: Provider Detail & Real-Time Booking (1:45 - 2:15)
1. On `/providers/<id>`, point out:
   - Verified badge and internal review disclosure.
   - Weekly published clinic schedule.
2. Select an upcoming date with open slots.
3. Select an available slot (e.g. `09:30`).
4. Enter visit reason: *"Routine checkup for mild fever and cough follow-up."*
5. Click **"Request this appointment"**.
6. Land on **Appointments** (`/appointments`) showing status *"Requested"* with instant calendar record.

### Step 5: Longitudinal Health Memory (2:15 - 2:50)
1. Click top navigation: **"Timeline"** (`/timeline`).
2. Show the unified chronological feed:
   - Appointment request event.
   - Previous lab report extraction events.
   - Logged vitals (BP, Weight, Blood Glucose).
3. Click **"Records"** (`/records`) to show stored diagnostic reports with privacy encryption and provenance metadata.

### Step 6: ZENDOC Connect & Care Continuity (2:50 - 3:25)
1. Click **"Messages"** (`/messages`).
2. Show the 3-pane ZENDOC Connect interface:
   - Left: Active conversations and role badges (`Doctor`, `Patient`).
   - Center: Message stream with structured consult cards.
   - Right: Participant info & policy controls.
3. Send a brief message: *"Dr. Clara, I have requested an appointment for tomorrow morning."*
4. Mention telehealth consultation workflow (`/telehealth`).

### Step 7: Ecosystem Quick Montage (3:25 - 4:10)
1. **Family Care** (`/family` & `/parent-care`):
   - Show Remote Parent Care dashboard with elderly parent vitals and medication tasks.
2. **IoT Hub** (`/iot-hub`):
   - Show connected health hardware (Omron BP monitor) with `source: device` provenance.
3. **Fitness Coach** (`/fitness`):
   - Show personalized workout generator and exercise library with technique guidance.

### Step 8: Owner Command Center & Governance (4:10 - 4:45)
1. Switch to Window 2 (Admin session: `/admin/agent-command-center`).
2. Show the operator console:
   - Core Agent planner & model router status.
   - Audit trail showing all events, permissions, and human approvals.
   - *Pitch statement*: *"AI coordinates capabilities across the ecosystem, but sensitive actions remain strictly governed and auditable."*

### Step 9: Closing Screen (4:45 - 5:00)
1. Switch back to Homepage (`/`) or Dashboard (`/dashboard`).
2. Deliver closing pitch statement (see Section 19).

---

## 6. Recommended Safe AI Demo Prompt

### **Primary Demo Prompt**:
> *"I have a mild fever and persistent cough for two days. What should I do?"*

### Alternative Safe Prompts:
- **Emergency Demo Prompt**: *"I have severe crushing chest pain radiating to my left arm."*
  *(Shows instant emergency red banner, 112/108 directive, zero generative hallucination).*
- **Prescription Refusal Prompt**: *"Can you prescribe me Amoxicillin 500mg?"*
  *(Shows ethical clinical refusal and directs user to verified pharmacy reference / consultation).*

---

## 7. Expected AI Behavior & Latency

- **Intent Identified**: `symptoms` (or `emergency` for chest pain).
- **Urgency Level**: `medium` (or `emergency`).
- **Specialist Suggested**: `Primary care clinician` / `Cardiology`.
- **Response Latency**: `< 50ms` (instant rule-assisted deterministic engine).
- **Action Chips Rendered**:
  - `[Book a consultation]` -> links directly to `/finder?category=doctor...`
  - `[Upload related reports]` -> links directly to `/records`
- **Fallback Behavior**: Always deterministic; operates 100% reliably even if cloud LLM API keys or local Ollama instances are offline.

---

## 8. Best Provider & Profile to Demonstrate

- **Provider**: `Dr. Clara Smith` (seeded synthetic cardiology doctor)
- **Specialty**: `Cardiology`
- **Organization**: `City Heart Clinic` (synthetic clinic)
- **Location**: `Mumbai`
- **Schedule**: Weekday mornings (09:00 - 12:00) with 30-minute intervals.

---

## 9. Appointment Demonstration Flow

1. From AI chip or `/finder` -> click **"View profile & availability"**.
2. Select target date -> choose slot -> type reason -> click **"Request this appointment"**.
3. Shows up in `/appointments` with immediate timestamped audit entry.

---

## 10. Health Memory Demonstration Flow

1. Show `/timeline` (chronological aggregation of appointments, vitals, reports, workouts).
2. Show `/records` (structured report storage, OCR metadata, download capability).
3. Mention patient-controlled consent and strict multi-tenant IDOR protection.

---

## 11. ZENDOC Connect Demonstration Flow

1. Show `/messages` 3-column layout.
2. Highlight role badges (`Doctor`, `Hospital`, `Patient`).
3. Type and send a message. Show real-time message stream.

---

## 12. Fitness, Family, & IoT Quick Montage

- **Family Care** (`/parent-care`): Highlight remote vitals monitoring for aging parents living in another city.
- **IoT Hub** (`/iot-hub`): Highlight device provenance (`source: device`).
- **Fitness** (`/fitness`): Highlight workout engine and technique tutorials.

---

## 13. Agentic AI & Command Center (3–5 Seconds)

- Open `/admin/agent-command-center`.
- Show active Core Agent, Model Router, and security audit log.
- *Voiceover*: *"ZENDOC is not a simple wrapper; it is an agentic ecosystem with deterministic safety gates, model routing, and human-in-the-loop approvals."*

---

## 14. Which Features NOT to Open During Recording

- Do NOT open raw database files or `.env` configurations.
- Do NOT open unconfigured cloud video streams (keep telehealth demo to local WebRTC room).
- Do NOT trigger live external payment gateways or third-party SMS dispatch.

---

## 15. Features to Describe Truthfully as Beta / Prototype / Integration Required

| Feature | Truthful Pitch Term | Safe Talking Point |
| :--- | :--- | :--- |
| **Persistence Tier** | *Managed PostgreSQL Connected* | "Live deployment connected to managed PostgreSQL on Render; SQLite available for local testing." |
| **Fitness Camera** | *Camera Preview Prototype* | "Browser-local camera preview designed for future on-device pose model integration." |
| **Telehealth** | *WebRTC Telehealth Beta* | "Direct peer consultation rooms with fallback to scheduled clinical visits." |
| **Ambulance Dispatch** | *Transport Intake (Integration Required)* | "Standardized dispatch intake ready for integration with municipal emergency fleets." |
| **Medicine Delivery** | *Pharmacy Order Flow (Integration Required)* | "Catalog search and refill reminders active; doorstep fulfillment ready for partner APIs." |

---

## 16. Recovery Plan if AI is Slow

- ZENDOC includes an automatic instant fallback engine.
- If external LLM timeout triggers (>2s), the system instantly falls back to deterministic rule routing with zero disruption to the user.

---

## 17. Recovery Plan if Render Cold-Starts

- The live selection deployment is connected to managed PostgreSQL via `DATABASE_URL`.
- However, free-tier web hosting instances may sleep after periods of inactivity.
- **Pre-Warm Action**: Send a `GET /api/v1/health` request 2 minutes prior to recording.
- If running on local server (`python run.py`), startup is instantaneous (< 1s).

---

## 18. Privacy & Security Checklist

- [ ] Ensure no real patient names, real phone numbers, or real clinical records appear.
- [ ] Ensure browser URL bar does not expose API tokens or sensitive session hashes.
- [ ] Keep Admin email displayed as standard demo identity (`owner@zendoc.local`).

---

## 19. Final Screen for Closing Pitch

**Display**: Homepage (`/`) or Patient Dashboard (`/dashboard`).  
**Closing Script**:
> *"Healthcare shouldn't be fragmented across a dozen disconnected apps. ZENDOC connects the journey — from intelligent safety-first guidance to verified care, longitudinal memory, family support, and connected devices. One platform. One connected healthcare journey. Thank you."*
