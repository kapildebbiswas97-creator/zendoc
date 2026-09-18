# ZENDOC EdgeCare AI — 2026 Competition Build

**Tagline:** Privacy-first, offline-capable healthcare assistance with governed on-device AI.

This document describes the competition layer built on top of the existing ZENDOC platform. The primary current target is the **Snapdragon® AI Lab Build & Present Challenge — Qualcomm (2026)**. The exact submission answer bank is maintained in `docs/QUALCOMM_SNAPDRAGON_AI_LAB_2026_SUBMISSION.md`.

## 1. Core product

ZENDOC EdgeCare AI is a local-first healthcare assistant designed and intended for optimisation on Snapdragon-powered Windows PCs. It combines:

- ZENDOC Health Memory and governed medical RAG context.
- A bounded local language-model path for summarization, navigation, extraction and care-navigation assistance.
- Local speech-to-text using an open-source Faster-Whisper development bridge and a stable adapter contract for a final Snapdragon/Qualcomm runtime.
- Deterministic safety gates for emergency, diagnosis, prescribing, medication change, permissions, payments and other high-risk actions.
- Online ZENDOC services for provider discovery, appointments and synchronization only where connectivity and real integrations exist.

The model is advisory. It cannot directly execute clinical or other high-risk actions.

## 2. Significant challenge-period AI modification

ZENDOC existed before the 2026 challenge. The competition branch is a significant AI modification rather than a renamed pre-existing product. It adds:

1. local open-source LLM routing through Ollama/OpenAI-compatible runtime contracts;
2. local speech-to-text with Faster-Whisper for development;
3. microphone capture with editable transcript and explicit manual Send;
4. owner-only EdgeCare runtime/readiness reporting;
5. strict separation between target configuration and measured Snapdragon/NPU evidence;
6. Qualcomm AI Hub profiling/deployment runbook;
7. deterministic healthcare safety and permission boundaries around all local-model behavior;
8. end-to-end care-search → provider → availability → appointment → CareLoop regression coverage.

This matches the public challenge rule that a pre-existing proposal must be significantly modified to add Qualcomm AI Hub or other open-source AI models.

## 3. Target AI models

Current development/competition direction:

- Language: a small open-source instruct model through the local model adapter; the final artifact must be named exactly as actually used.
- Speech: Faster-Whisper local development path with `whisper_small` as the target identifier; a Qualcomm AI Hub-supported artifact may be substituted for final Snapdragon profiling.

A model or chipset name in configuration is a target declaration, not proof that inference ran on a Snapdragon NPU.

## 4. Architecture

```text
Patient / clinician
       |
       v
Local speech capture / text
       |
       v
Local ASR target
       |
       v
ZENDOC deterministic safety gate
       |
       +---- high-risk request ---> deterministic safe flow / human escalation
       |
       v
Privacy-aware model router
       |
       +---- eligible low-risk task ---> local model runtime
       |                                  |
       |                                  v
       |                          governed Health Memory / RAG
       |
       +---- permitted online operation -> ZENDOC services
                                          |
                                          +--> provenance-aware care discovery
                                          +--> connected appointment workflow
                                          +--> CareLoop continuity
```

## 5. One reliable demo flow

1. User speaks or enters a low-risk healthcare-navigation request.
2. Speech is transcribed locally when ASR is enabled.
3. The transcript remains editable and is not submitted until the user presses **Send**.
4. ZENDOC classifies risk deterministically before model routing.
5. A bounded local model provides non-diagnostic assistance.
6. Consent-governed Health Memory may provide authorized context.
7. The user continues into provenance-aware provider discovery.
8. A real connected ZENDOC provider can expose published availability and accept an appointment request; external/public/map listings remain discovery-only.
9. CareLoop carries the confirmed workflow forward without inventing provider outcomes.

Do not use autonomous diagnosis, prescribing or emergency dispatch as the model demo; those are intentionally blocked or human-governed.

## 6. Truthful Snapdragon readiness

The EdgeCare runtime exposes owner-only readiness/test surfaces and uses strict states to distinguish:

- disabled/not configured;
- runtime verification required;
- local runtime ready but benchmark required;
- benchmark recorded with NPU unconfirmed;
- measurement recorded with explicit NPU evidence.

Even a recorded benchmark is only as trustworthy as the retained Qualcomm AI Hub or physical-device source evidence.

## 7. Benchmark evidence contract

Do not create or populate `instance/edgecare_benchmark.json` with invented values. When real profiling exists, record only the exact reported values, including source, timestamp, device, chipset, model, runtime/execution provider, run count, latency values and whether NPU execution is explicitly confirmed.

Never put patient data, prompts, responses, credentials, API tokens, private keys or hidden reasoning into benchmark evidence.

## 8. Local development configuration

For ordinary software-flow validation, local Ollama and Faster-Whisper are valid open-source development paths. They prove the application flow, not Snapdragon acceleration.

For setup, use:

- `docs/EDGECARE_LOCAL_DEMO_SETUP.md`
- `docs/QUALCOMM_AI_HUB_RUNTIME_SETUP.md`
- `docs/DEMO_RELEASE_CHECKLIST.md`
- `docs/EDGECARE_SUBMISSION_READINESS.md`

## 9. Challenge positioning

Suggested title:

**ZENDOC EdgeCare AI — Privacy-First, Offline-Capable Agentic Healthcare for Snapdragon PCs**

Suggested one-line pitch:

**ZENDOC EdgeCare AI turns a Snapdragon-powered PC into a private healthcare intelligence hub that can understand user input, use governed health context and assist care workflows locally while reserving consequential clinical and operational decisions for deterministic safeguards and humans.**

The public Snapdragon AI Lab challenge allows solutions that are designed, developed **or intended to be optimised** for Snapdragon-powered HP PCs. Therefore, genuine Qualcomm AI Hub/physical Snapdragon profiling is a strong enhancement, but no NPU claim is allowed unless real evidence exists.

## 10. Safety and submission claims

- Do not say ZENDOC diagnoses disease.
- Do not say it prescribes or changes medication autonomously.
- Do not say emergency dispatch is AI-controlled.
- Do not say a model ran on Snapdragon/NPU until evidence confirms it.
- Do not fabricate latency, accuracy, power, battery, privacy, users, hospitals, providers, pilots, partnerships or revenue.
- Do not describe a public/map provider as bookable unless the real ZENDOC provider integration supports that action.

## 11. Repository completion status

Repository-side competition engineering is complete for proposal submission:

- [x] Isolated competition branch retained; production `main` is not modified by the competition layer.
- [x] Local open-source LLM path implemented.
- [x] Local Faster-Whisper ASR development bridge implemented.
- [x] Voice transcript remains editable and requires explicit Send.
- [x] EdgeCare readiness/evidence states implemented.
- [x] Deterministic clinical safety and permissions preserved.
- [x] Benchmark evidence separated from target configuration.
- [x] Health Memory, provenance-aware discovery, appointments and CareLoop retained.
- [x] Mental Wellness and messaging competition surfaces retained with safety boundaries.
- [x] Apache-2.0 license present.
- [x] Local demo, recording and Qualcomm AI Hub profiling runbooks present.
- [x] Dedicated Qualcomm Snapdragon AI Lab 2026 submission package present.

Machine-dependent evidence cannot be fabricated by repository code. Local runtime checks, optional Qualcomm AI Hub profiling and the final recording must be performed on the actual machine/environment used for the demo.

## 12. Submission freeze

After the final competition branch SHA has a green Production Gate, freeze unrelated feature work. Fix only a reproducible submission blocker. **Do not merge PR #68 into `main` merely for the Qualcomm submission.**