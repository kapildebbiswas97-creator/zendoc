# ZENDOC — DHN / Investor Virtual Demo Runbook

**Purpose:** Reproducible 5–7 minute virtual demonstration for DHN selection, investor calls, accelerators and product reviews.

**Truth rule:** Show working software, clearly label synthetic local fixtures, and never convert software capability into a claim of real users, provider acceptance, clinical validation, revenue, external fulfilment or Snapdragon/NPU execution without evidence.

---

## 1. Freeze the exact demo source

Before presenting:

1. Use branch `competition/edgecare-ai-2026`.
2. Record the exact commit SHA.
3. Confirm that exact SHA has a green Production Gate.
4. Keep PR #68 draft/unmerged unless a separate release decision is made.
5. Do not change production `main` for the competition demo.

For local runtime and microphone setup, follow `docs/EDGECARE_LOCAL_DEMO_SETUP.md`.

---

## 2. Prepare the local demo safely

Set local-only secrets and create the visibly synthetic fixture:

```powershell
$env:ZENDOC_ENV="development"
$env:ZENDOC_ADMIN_EMAIL="your-owner-email@example.com"
$env:ZENDOC_ADMIN_PASSWORD="replace-with-a-strong-local-password"
$env:ZENDOC_DEMO_PASSWORD="replace-with-a-local-only-demo-password"

python -m zendoc.edgecare_demo_data
```

Synthetic accounts:

- Patient: `demo-patient@zendoc.local`
- Provider: `demo-doctor@zendoc.local`

The names include **DEMO ONLY**. The provider profile states that it is a synthetic competition fixture and not a real clinician/provider. Never describe this fixture as traction, a partner, a patient, a pilot, a customer or a healthcare deployment.

Start the local LLM + local ASR path using the setup guide or:

```powershell
.\scripts\start_edgecare_local_demo.ps1
```

Before the call, verify:

- `/healthz` returns ready;
- owner login works;
- `/admin/edgecare` loads;
- local LLM = ready on the actual demo machine;
- local ASR = ready on the actual demo machine;
- the fixed harmless local-AI smoke test passes;
- microphone → editable transcript works;
- transcript is **not** auto-submitted;
- the pages used below load without 404/500.

---

## 3. Recommended 5–7 minute virtual demo

### Act 1 — Problem + product thesis (30–45 sec)

Open:

```text
/showcase
```

Presenter framing:

> Healthcare is fragmented across discovery, appointments, records, labs, pharmacies and follow-up. ZENDOC is building one governed care operating layer that connects those steps while keeping provider verification, patient consent, AI safety and real-world confirmation separate.

Point to:

- connected-care operating system;
- trust architecture;
- one governed care loop;
- commercial path.

Do **not** present the commercial path as current revenue unless the owner dashboard contains real recorded evidence.

---

### Act 2 — Patient discovery → connected provider request (60–90 sec)

Sign in as the clearly labelled synthetic patient.

Open:

```text
/finder
```

Search:

```text
Kalyani
```

Open the **DEMO ONLY** provider profile.

Explain:

> This provider is a deterministic local competition fixture, not a real doctor. I use it so the demo can prove the product workflow without pretending a public directory listing is bookable.

Choose a future published slot and request the appointment.

Then open Appointments.

Show the status as **requested / waiting for provider confirmation**.

Presenter framing:

> ZENDOC does not convert a patient request into provider acceptance. Provider confirmation remains an authoritative state transition.

Do not say “instant confirmed booking” unless an actual connected provider has confirmed it.

---

### Act 3 — Local voice → local advisory → Agent OS (90 sec)

Open:

```text
/agent-os
```

Use **local voice input** for a low-risk request such as:

> Help me find the safest next step for a cardiology appointment in Kalyani.

Stop recording.

Show:

1. transcript appears as editable text;
2. nothing is submitted automatically;
3. you review it and manually run the workflow;
4. local model/SLM appears only as a non-executable advisory when the runtime is ready;
5. Health Memory context is minimum-necessary;
6. medical RAG uses approved evidence metadata only where relevant;
7. Agent OS owns the deterministic bounded plan;
8. consequential steps remain behind human gates;
9. provider/service confirmation is not inferred;
10. audit evidence links the workflow without copying raw prompt/transcript/Health Memory into the audit record.

Presenter framing:

> The AI can help understand and coordinate the goal, but the model cannot directly execute tools, prescribe, change medication, approve payment, change permissions or manufacture provider confirmation.

---

### Act 4 — Safety + emergency bypass (45–60 sec)

Open:

```text
/ai
```

Enter:

> I have severe chest pain and difficulty breathing.

Show the deterministic emergency response.

Presenter framing:

> Emergency safety runs before the generative planning path. For high-risk emergency language, ZENDOC bypasses ordinary model assistance and directs the user to real emergency care.

Do not demonstrate emergency dispatch unless a real dispatch integration exists.

---

### Act 5 — Health Memory + continuity (45–60 sec)

Open the Health Memory / records surface from the patient navigation.

Show:

- timeline and provenance;
- patient-controlled access;
- provider-recorded vs patient-reported separation;
- the care-chain continuity view when a journey exists.

Presenter framing:

> ZENDOC remembers the journey, but provenance remains explicit. Patient-reported data does not silently become provider-recorded clinical truth.

---

### Act 6 — Founder evidence console (60 sec)

Switch to the owner account.

Open:

```text
/admin/edgecare
```

Show the 10-stage care-chain readiness matrix:

- local voice / ASR;
- local LLM / SLM advisory;
- Agent OS;
- Health Memory;
- approved medical RAG;
- safe actions / human gates;
- provider/service confirmation;
- outcome verification;
- longitudinal memory;
- audit evidence.

Explain the three different truth levels:

1. **implemented in software**;
2. **runtime ready on this machine**;
3. **real-world/provider/hardware evidence confirmed**.

Then open:

```text
/admin/startup
```

Show only actual observed metrics.

Presenter framing:

> ZENDOC tracks product usage, provider onboarding, pilots, financial entries and investor-readiness signals as evidence. Missing traction remains missing; the dashboard does not manufacture fundraising metrics.

---

## 4. What to say about funding

A safe fundraising framing is:

> The product foundation and governed care loop are built. Funding would accelerate real provider onboarding, verified data integrations, security/privacy/compliance work, clinical governance, pilot operations, local/on-device AI validation and focused go-to-market.

Do not quote invented user counts, hospitals, revenue, pilots, retention or valuation.

For investor discussions, use real values from `/admin/startup` only.

---

## 5. What not to claim

Do not say:

- “all hospitals are connected”;
- “all India provider data is complete”;
- “public/map listings are bookable”;
- “pharmacy stock is live” without a real inventory observation;
- “provider accepted” when only a request exists;
- “service completed externally” when the state is only a ZENDOC-internal workflow record;
- “clinical outcome verified” from a generic completion flag;
- “ABDM integrated” unless a real integration proves it;
- “HIPAA/GDPR compliant” without appropriate legal/technical validation;
- “clinically validated AI” without evidence;
- “runs on Snapdragon NPU” without Qualcomm/physical-device evidence;
- fabricated latency, throughput, accuracy, power or benchmark numbers;
- synthetic fixture records as customers, users, doctors, pilots or traction.

---

## 6. Virtual-demo backup plan

If one local runtime fails during the call:

1. keep the demo running;
2. state the exact runtime status;
3. use typed input if ASR fails;
4. use deterministic fallback if the local model is unavailable;
5. continue with Agent OS, Health Memory, provider-state truth and owner evidence pages;
6. never turn a failed integration into a fake success message.

A truthful degraded demo is stronger than a fabricated “green” integration.

---

## 7. Final pre-call checklist

- [ ] Exact demo SHA is green.
- [ ] No private patient data is visible.
- [ ] Demo fixture is visibly labelled DEMO ONLY.
- [ ] Browser notifications are disabled.
- [ ] Owner secrets/API keys are not visible.
- [ ] `/showcase` loads.
- [ ] patient login loads.
- [ ] `/finder` loads.
- [ ] synthetic provider profile loads.
- [ ] appointment request persists as requested/waiting provider.
- [ ] `/agent-os` loads.
- [ ] local voice is tested if you plan to show it.
- [ ] `/ai` emergency safety works.
- [ ] Health Memory loads.
- [ ] `/admin/edgecare` loads.
- [ ] `/admin/startup` loads.
- [ ] every number you plan to say has a real source.
- [ ] Snapdragon/NPU claims are omitted unless real evidence exists.

---

## 8. Closing line

> ZENDOC is not trying to replace clinicians or pretend that healthcare operations are connected when they are not. We are building the trusted operating layer that helps patients move from discovery to coordinated care, verified outcomes and longitudinal memory—with AI inside the workflow, but evidence and human authority controlling the truth.
