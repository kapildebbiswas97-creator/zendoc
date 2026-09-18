# ZENDOC Demo Release Checklist

Use this checklist immediately before recording a competition submission.

## 1. Freeze the exact source

- [ ] Confirm the recording uses `competition/edgecare-ai-2026`.
- [ ] Record the exact Git commit SHA.
- [ ] Confirm the exact SHA has a green ZENDOC Production Gate.
- [ ] Do not merge PR #68 into production `main` for the competition recording.

## 2. Local runtime readiness

- [ ] Start ZENDOC locally.
- [ ] Open `/admin/edgecare` as the owner.
- [ ] Local LLM status = `ready`.
- [ ] Local ASR status = `ready`.
- [ ] Harmless local-model smoke test passes.
- [ ] Microphone recording works from the browser.
- [ ] Transcript appears as editable text.
- [ ] Transcript is not automatically submitted.
- [ ] Manual Send works.

## 3. Demo flow

- [ ] Login works.
- [ ] Patient dashboard loads without 404/500.
- [ ] Health Memory loads.
- [ ] Find Care loads.
- [ ] Search returns only truthful local/verified/public results according to provenance.
- [ ] If using synthetic competition data, **DEMO ONLY** labels remain visible.
- [ ] Provider profile loads.
- [ ] A published slot can be selected for the synthetic deterministic fixture.
- [ ] Appointment request is persisted and shown as requested/pending provider confirmation.
- [ ] ZENDOC AI loads.
- [ ] Mental Wellness & Awareness is visible and remains non-diagnostic.
- [ ] Messaging page loads and follows the current role/permission policy.
- [ ] Family/connected-care page used in the recording loads.

## 4. Truthful narration

Allowed when demonstrated:

- "ZENDOC has a working product foundation."
- "ZENDOC can run its local AI software path on the demo machine."
- "Voice input creates editable text and requires manual Send."
- "High-risk clinical and permission-changing actions are not model-controlled."

Not allowed without external evidence:

- "This runs on the Snapdragon NPU" unless real Qualcomm/physical-device evidence confirms it.
- Fabricated NPU latency, throughput, power, benchmark or accuracy values.
- Claims that public/map discovery listings are directly bookable without a real integration.
- Claims of real pharmacy stock/order fulfilment, ambulance dispatch, payment, insurer approval or provider confirmation without the connected external system proving it.
- Claims of users, pilots, hospitals, doctors, revenue, clinical outcomes, regulatory approval or partnerships that are not independently verified.

## 5. Qualcomm evidence, when available

- [ ] Save Qualcomm AI Hub profile/job identifier.
- [ ] Save exact target device/chipset.
- [ ] Save exact model and runtime/provider.
- [ ] Save measured performance exactly as reported.
- [ ] Save explicit NPU/HTP evidence only if the source reports it.
- [ ] Store no API token in screenshots, repository, benchmark metadata or video.

## 6. Recording assets

- [ ] Clean browser profile / no private tabs.
- [ ] No real patient data visible.
- [ ] No passwords, API keys or environment secrets visible.
- [ ] Notifications disabled during recording.
- [ ] Demo fixture prepared before recording.
- [ ] Pitch script open on a second device or printed.
- [ ] Final deck uses real screenshots and leaves unverified metrics out.

## 7. Competition-specific framing

### SBI / IIT Delhi Youth Ideathon
Lead with the patient problem, entrepreneurship, scale, accessibility and continuous-care vision. Do not make the pitch depend on Snapdragon evidence. Use `docs/SBI_IIT_DELHI_YOUTH_IDEATHON_2026.md`.

### DHN / IIT Kanpur
Lead with healthcare relevance, patient outcomes, interoperability/privacy, credible data and pilot readiness. Use `docs/DHN_IIT_KANPUR_SUBMISSION_PACKAGE.md`.

### Qualcomm
Lead with on-device privacy, local AI/ASR, deterministic healthcare safety and measured Snapdragon evidence. Use `docs/QUALCOMM_AI_HUB_RUNTIME_SETUP.md`.

## Final stop condition

Record only after the exact source SHA is green and every page intended for the demo has passed this checklist on the actual recording machine. Repository CI cannot replace microphone, local-model or Snapdragon hardware validation.
