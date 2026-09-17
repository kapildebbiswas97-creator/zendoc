# ZENDOC EdgeCare AI — Submission Readiness

This document defines the final truth boundary for the `competition/edgecare-ai-2026` branch.

## Repository-complete items

- Competition branch isolated from production `main`.
- Safety, authentication, CSRF, authorization, owner-only administration and privacy boundaries preserved.
- Local LLM integration path with explicit runtime readiness checks.
- Local ASR integration path with editable transcript and manual-send requirement.
- Universal care search → provider profile → published slot → appointment request → CareLoop regression coverage.
- Health Memory, family/lifecycle, messaging, mental-wellness visibility and competition-facing product surfaces retained.
- Qualcomm-specific README section with setup, usage, truth boundaries and developer contact.
- Root Apache-2.0 `LICENSE` for open-source competition submission.
- Qualcomm AI Hub runtime/profiling runbook in `docs/QUALCOMM_AI_HUB_RUNTIME_SETUP.md`.
- One-machine local demo runbook in `docs/EDGECARE_LOCAL_DEMO_SETUP.md`.
- DHN/IIT Kanpur submission package.
- SBI/IIT Delhi Youth Ideathon 2026 submission package in `docs/SBI_IIT_DELHI_YOUTH_IDEATHON_2026.md`.

## Final repository gate

The exact final competition commit must have a green **ZENDOC Production Gate** before recording. A historical green run does not validate a newer SHA.

Competition branches intentionally skip production Render deployment verification. Production deployment verification applies only to `main`.

## Demo-machine evidence still required from the actual recording laptop

These steps cannot be truthfully completed by repository code or CI alone:

1. Confirm `/admin/edgecare` loads for the owner.
2. Confirm local LLM status reports `ready` on the actual demo machine.
3. Confirm local ASR status reports `ready` on the actual demo machine.
4. Run the harmless owner-only local-model smoke test.
5. Confirm microphone → local transcription → editable composer works.
6. Confirm voice text is not auto-submitted and sends only after the user presses **Send**.
7. Run the intended low-risk demo flow end to end and verify no 404/500 occurs on the pages that will be recorded.
8. If using the local synthetic care fixture, visibly retain the **DEMO ONLY** labels and never describe it as a real doctor, clinic, pilot, customer or deployment.

## Snapdragon / Qualcomm evidence boundary

Do not claim Snapdragon/NPU execution because a target name or model is configured.

A Snapdragon/NPU claim is allowed only when supported by real physical-device or Qualcomm AI Hub evidence showing the actual target/runtime. Preserve:

- Qualcomm job/profile identifier;
- exact target device and chipset;
- exact model artifact;
- runtime / execution provider;
- timestamp;
- measured latency/performance values exactly as reported;
- run count/success information where available;
- explicit NPU/HTP execution evidence when the profiling source provides it.

Until that exists, use wording such as **"EdgeCare AI is architected for Snapdragon deployment; current local software validation is not NPU proof."**

## Submission freeze rule

After the exact competition SHA is green and the demo-machine checks pass, freeze feature development for the recording. Only fix a reproducible submission blocker after that point; do not add unrelated features immediately before recording.
