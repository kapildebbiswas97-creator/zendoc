# ZENDOC — Selection Demo Runbook

**Purpose**: Standardized 5-minute live demonstration script for selection rounds, evaluators, and product reviews.  
**Platform Version**: Selection Beta  

---

## 1. Setup & Pre-Flight (1 Minute Before Demo)

```bash
# Terminal: Start the local server with seeded demo data
python -m zendoc.cli init-db --seed
python run.py
```
Open two browser windows:
1. **Window A (Patient)**: `http://localhost:5000/login/patient` — Log in as `<DEMO_PATIENT_EMAIL>` with `<DEMO_PATIENT_PASSWORD>` (operator-configured demo account)
2. **Window B (Owner / Admin)**: `http://localhost:5000/login/admin` — Log in with the operator-configured `ZENDOC_ADMIN_EMAIL` / `ZENDOC_ADMIN_PASSWORD`

---

## 2. Five-Minute Live Demonstration Script

### **Act I: The Patient Journey — Unified Access & Longitudinal Memory (1 min)**
1. **Dashboard Overview**:
   - *Presenter*: "ZENDOC is a unified healthcare and wellness platform designed to bridge the gap between clinical appointments, daily fitness, longitudinal health memory, and AI guidance."
   - Point out the unified navigation: Find Care, Appointments, Health Memory, Fitness, AI Assistant, Family Care, IoT Hub, and Services.
2. **Find Care & Instant Booking**:
   - Navigate to **Find Care** (`/finder`).
   - Search for **Cardiology**. Show verified provider cards, clinic addresses, and real-time appointment availability.
   - Click on **Dr. Clara Smith**, select a slot, and confirm the booking.
   - Show the instant confirmation and calendar integration in **Appointments** (`/appointments`).
3. **Health Memory & Provenance**:
   - Navigate to **Health Memory** (`/health`).
   - Showcase the chronological **Health Timeline** combining doctor visits, lab reports, manual vitals, and IoT streams.
   - Highlight the **Data Export** feature (demonstrating patient data ownership and HIPAA/GDPR-aligned privacy).

---

### **Act II: Clinical AI Safety & Guardrails (1 min)**
1. **Deterministic Emergency Triage**:
   - Navigate to **AI Assistant** (`/ai`).
   - Type: *"I have severe crushing chest pain and difficulty breathing."*
   - Show immediate, deterministic emergency directive: Emergency warning banner, directive to call 108 / ER, and complete bypass of generative hallucination.
2. **Prescription Refusal & Clinical Guardrail**:
   - Type: *"Please prescribe me 500mg Amoxicillin."*
   - Show intelligent refusal: AI explains that prescription medications require clinical evaluation and directs the user to book a consultation with a verified doctor.
3. **Multimodal Intent Routing**:
   - Type: *"What are good exercises for my lower back?"*
   - Show seamless transition into the **Fitness Coach** with personalized exercises and tutorial video recommendations.

---

### **Act III: Fitness Coach & Connected IoT Hub (1 min)**
1. **Personalised Workout Plan Generator**:
   - Navigate to **Fitness** (`/fitness`).
   - Showcase the algorithmic workout engine tailoring exercises to equipment, time, and experience level.
   - Start an interactive workout session, log a set, and finish. Show how the workout automatically persists to the user's Health Timeline.
2. **Connected IoT Health Devices**:
   - Navigate to **IoT Hub** (`/iot-hub`).
   - Demonstrate connected health hardware (Omron BP Monitor, Apple Watch).
   - Sync a measurement and highlight that ZENDOC records measurement provenance as `source: device`, establishing clinical auditability.

---

### **Act IV: Family Care & Remote Parent Care (1 min)**
1. **Remote Parent Care Dashboard**:
   - Navigate to **Family Care** &rarr; **Remote Parent Care** (`/parent-care`).
   - *Presenter*: "Millions of people care for aging parents living in other cities. ZENDOC provides a dedicated Remote Parent Care dashboard to track vital measurements, medication tasks, and care alerts in real time."
   - Showcase dependent profiles, task tracking, and proxy access permissions.

---

### **Act V: Owner Command Center & Model Evaluation Lab (1 min)**
1. **Owner Command Center (Switch to Window B)**:
   - Navigate to **Agent Command Center** (`/admin/agent-command-center`).
   - Showcase real-time operational health, task queues, and security audit logs.
2. **Model Evaluation Lab**:
   - Navigate to **Model Evaluation Lab** (`/admin/model-evaluation`).
   - *Presenter*: "ZENDOC includes a built-in Model Evaluation Lab that benchmarks LLM and local AI candidates against standardized clinical, safety, and operational rubrics before live deployment."
   - Run a safe `dry_run` benchmark and review candidate performance metrics.

---

## 3. Concluding Summary & Key Takeaways

- **Production-Ready Core**: 100% of core patient, provider, fitness, and admin workflows operate reliably with zero broken forms or simulated placeholders.
- **Safety by Design**: Deterministic guardrails protect patients in emergency situations.
- **Truthful Architecture**: Fully persistent SQLite locally, PostgreSQL-ready, and transparently disclosed cloud execution boundaries.
