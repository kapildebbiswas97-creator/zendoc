# ZENDOC EdgeCare AI — Qualcomm Submission Package

> **Current source of truth:** `docs/QUALCOMM_SNAPDRAGON_AI_LAB_2026_SUBMISSION.md`

This file is retained so older links do not break. The exact, current package for the **Snapdragon® AI Lab Build & Present Challenge — Qualcomm (2026)** is:

- `docs/QUALCOMM_SNAPDRAGON_AI_LAB_2026_SUBMISSION.md` — final proposal wording, significant-AI-modification explanation, evaluation mapping and form answer bank;
- `docs/EDGECARE_AI_2026.md` — current competition architecture and engineering status;
- `docs/EDGECARE_LOCAL_DEMO_SETUP.md` — ordinary-laptop local LLM/ASR/demo setup;
- `docs/QUALCOMM_AI_HUB_RUNTIME_SETUP.md` — real Qualcomm AI Hub / Snapdragon profiling workflow;
- `docs/EDGECARE_SUBMISSION_READINESS.md` — evidence and recording truth boundary;
- `scripts/verify_edgecare_submission.py` — read-only software/runtime preflight after local services are started.

## Important submission boundary

ZENDOC existed before this challenge. The competition branch is a significant AI modification that adds local open-source LLM routing, local Faster-Whisper speech-to-text, editable manual-send voice interaction, EdgeCare runtime/readiness states, Qualcomm AI Hub profiling/deployment guidance and deterministic healthcare safety controls.

The challenge submission may describe the system as **designed/intended for optimisation on Snapdragon-powered HP PCs**. Do **not** claim actual Snapdragon/NPU execution, measured latency, power/battery improvement or Qualcomm benchmark results unless genuine Qualcomm AI Hub or physical-device evidence has been collected.

Repository/CI completion and local-runtime verification are different things. CI can validate the code and safety regressions; microphone permissions, local runtime availability and any Snapdragon profiling must be checked on the actual machine/environment.

Production `main` remains separate. **Do not merge PR #68 merely for the competition submission.**
