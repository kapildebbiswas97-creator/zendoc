# ZENDOC EdgeCare AI — Submission Readiness

This document defines the final truth boundary for the `competition/edgecare-ai-2026` branch and separates **proposal-submission readiness** from **real-machine demo/hardware evidence**.

## Gate A — repository/proposal readiness

These items are repository-side and must be complete before the irreversible competition submission:

- Competition branch remains isolated from production `main`.
- Safety, authentication, CSRF, authorization, owner-only administration and privacy boundaries remain preserved.
- Local LLM integration path exists with explicit runtime readiness checks.
- Local ASR integration path exists with editable transcript and manual-send requirement.
- Universal care search → provider profile → published slot → appointment request → CareLoop regression coverage exists.
- Health Memory, family/lifecycle, messaging, Mental Wellness and competition-facing product surfaces remain available.
- README identifies the Snapdragon AI Lab 2026 target, developer contact, setup, run/test instructions and truth boundaries.
- Root Apache-2.0 `LICENSE` is present.
- Exact Qualcomm 2026 proposal/answer bank exists at `docs/QUALCOMM_SNAPDRAGON_AI_LAB_2026_SUBMISSION.md`.
- Qualcomm AI Hub runtime/profiling runbook exists at `docs/QUALCOMM_AI_HUB_RUNTIME_SETUP.md`.
- One-machine local demo runbook exists at `docs/EDGECARE_LOCAL_DEMO_SETUP.md`.
- Read-only runtime preflight exists at `scripts/verify_edgecare_submission.py`.
- The exact final competition commit has a green **ZENDOC Production Gate**.

Competition branches intentionally skip production Render deployment verification because Render is built from `main`, not this competition branch.

## Gate B — actual demo-machine verification

Repository code or CI cannot truthfully certify browser/microphone/local-service behavior on a laptop it cannot access. On the actual demo machine, start the local stack and run:

```powershell
.\.venv\Scripts\python.exe scripts\verify_edgecare_submission.py
```

The automatic preflight checks the competition branch/commit, required files, Faster-Whisper dependency, configured local LLM endpoint/model, local ASR endpoint/model, ZENDOC `/healthz`, and any benchmark-evidence file without inventing evidence.

Then manually verify:

1. Sign in as the configured owner and open `/admin/edgecare`.
2. Confirm local LLM status is `ready`.
3. Confirm local ASR status is `ready`.
4. Run the harmless owner-only local-model smoke test.
5. Confirm microphone → local transcription → editable composer works.
6. Confirm voice text is never auto-submitted and sends only after the user presses **Send**.
7. Run the intended low-risk demo path end to end and verify no 404/500 occurs on pages shown in the recording.
8. If using the local synthetic care fixture, retain visible **DEMO ONLY** labels and never describe it as a real doctor, clinic, pilot, customer or deployment.

These are real-environment acceptance checks, not missing repository implementation.

## Snapdragon / Qualcomm evidence boundary

The challenge build is designed/intended for Snapdragon-powered PC optimisation. That design target does **not** itself prove NPU execution.

Only claim measured Snapdragon/NPU execution, latency, throughput, power or similar hardware performance when genuine physical-device or Qualcomm AI Hub evidence exists. Preserve the exact evidence source, including where available:

- Qualcomm job/profile identifier;
- exact target device and chipset;
- exact model artifact;
- runtime / execution provider;
- timestamp;
- measured values exactly as reported;
- run count/success information;
- explicit NPU/HTP execution evidence.

If no such evidence exists, use wording such as:

> **EdgeCare AI is designed for Snapdragon deployment and optimisation; current local software validation is not Snapdragon/NPU benchmark proof.**

Do not create `instance/edgecare_benchmark.json` merely to satisfy a checklist. Create it only from genuine measurement evidence.

## Submission decision rule

For the proposal/application, repository readiness and truthful wording are the blocking software requirements. Real Snapdragon profiling strengthens a hardware-performance claim or later demo, but it must never be fabricated or implied by configuration alone.

Before pressing an irreversible final-submit button:

1. verify the exact competition branch SHA;
2. verify the exact SHA has a green Production Gate;
3. proofread the live form against `docs/QUALCOMM_SNAPDRAGON_AI_LAB_2026_SUBMISSION.md`;
4. remove any claim that is stronger than the evidence actually held;
5. ensure no API token, password, private patient information or raw health record is included.

After the final SHA is green, freeze unrelated feature development. Fix only a reproducible submission blocker. **Do not merge PR #68 into `main` merely for this competition.**
