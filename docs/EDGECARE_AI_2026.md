# ZENDOC EdgeCare AI — 2026 Competition Build

**Tagline:** Privacy-first, offline-capable healthcare assistance with governed on-device AI.

This document describes the competition layer built on top of the existing ZENDOC platform. The same engineering core can be packaged for two different judging contexts without pretending they are two separate products.

## 1. Core product

ZENDOC EdgeCare AI is a local-first healthcare assistant intended for Snapdragon X Series Windows PCs. It combines:

- ZENDOC Health Memory and governed medical RAG context.
- A bounded local language model for summarization, navigation, extraction, and provider-discovery assistance.
- Local speech-to-text as a competition target using a Qualcomm AI Hub speech model.
- Deterministic safety gates for emergency, diagnosis, prescribing, medication change, permissions, payments, and other high-risk actions.
- Online ZENDOC services for provider search, appointments, maps/data integrations, and synchronization when connectivity is available.

The model is advisory. It cannot directly execute tools or perform clinical actions.

## 2. Target AI models

Competition target models:

- Language: `llama_v3_2_3b_instruct_ssd` or another validated Qualcomm AI Hub/open-source model appropriate for the final Snapdragon runtime.
- Speech: `whisper_small` or a compatible Qualcomm AI Hub ASR model.

The exact artifact used in the final demonstration must be recorded in benchmark evidence. A model name in configuration is a target declaration, not proof that the model ran on an NPU.

## 3. Architecture

```text
Patient / clinician
       |
       v
Local speech capture
       |
       v
On-device ASR target
       |
       v
ZENDOC deterministic safety gate
       |
       +---- high-risk request ---> deterministic safe flow / human escalation
       |
       v
Privacy-aware model router
       |
       +---- health-sensitive safe local task ---> local model runtime
       |                                          |
       |                                          v
       |                                  governed context / RAG
       |
       +---- permitted online operation --------> ZENDOC cloud/backend services
                                                  |
                                                  +--> provider search
                                                  +--> appointment workflow
                                                  +--> data synchronization
```

## 4. One demo flow to make bulletproof

The competition demo should optimize for reliability instead of trying to show every ZENDOC screen.

1. A user speaks or enters a non-emergency healthcare request.
2. Speech is transcribed locally when the ASR runtime is available.
3. ZENDOC classifies safety/risk deterministically before model routing.
4. The bounded local model produces structured, non-diagnostic assistance.
5. Relevant consent-governed Health Memory/RAG context can support summarization.
6. ZENDOC shows the structured result and the runtime status.
7. If connectivity is available, the user can continue into real provider discovery/appointment workflows.
8. The owner runtime page/API shows whether local inference is ready and whether real Snapdragon/NPU benchmark evidence has been recorded.

Do not use an emergency or diagnosis scenario as the primary model demo. Those intentionally remain deterministic/human-governed.

## 5. Truthful Snapdragon verification

The EdgeCare runtime exposes two owner-only endpoints:

- `GET /api/v1/admin/edgecare/runtime`
- `POST /api/v1/admin/edgecare/test`

The POST endpoint accepts no caller prompt. It reuses the existing harmless local-AI smoke test.

Readiness stages are deliberately strict:

- `disabled`: EdgeCare target is disabled.
- `runtime_verification_required`: target is enabled but local inference is not verified ready.
- `benchmark_required`: local inference is ready but no hardware benchmark evidence is recorded.
- `benchmark_recorded_npu_unconfirmed`: benchmark metadata exists but NPU execution is not confirmed.
- `npu_measurement_recorded`: benchmark metadata explicitly records confirmed NPU execution.

Even the last state is described as **recorded**, not independently verified by ZENDOC. Keep raw Qualcomm AI Hub Workbench/device evidence with the submission.

## 6. Benchmark evidence contract

Do not create `instance/edgecare_benchmark.json` until real measurements exist.

Required fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | Must be `1`. |
| `source` | `local_snapdragon_device`, `qualcomm_ai_hub_workbench`, or `qualcomm_device_cloud`. |
| `measured_at` | Timestamp from the measurement session. |
| `device` | Actual target device used. |
| `chipset` | Actual chipset. |
| `runtime` | Actual inference runtime. |
| `execution_provider` | Actual execution provider/backend. |
| `model` | Exact measured model artifact. |
| `runs` | Number of measured runs. |
| `success_rate` | Fraction from 0 to 1. |
| `median_latency_ms` | Measured median latency. |
| `p95_latency_ms` | Measured p95 latency. |
| `npu_confirmed` | `true` only when the measurement evidence confirms NPU execution. |
| `evidence_reference` | Local reference to screenshot/report/job ID; never a secret. |

Never put patient data, prompts, model responses, credentials, API keys, or hidden reasoning in this benchmark file.

## 7. Suggested runtime configuration

```bash
ZENDOC_EDGECARE_ENABLED=true
ZENDOC_EDGECARE_TARGET_PLATFORM="Snapdragon X Series Windows PC"
ZENDOC_EDGECARE_TARGET_CHIPSET="Snapdragon X Elite"
ZENDOC_EDGECARE_LANGUAGE_MODEL=llama_v3_2_3b_instruct_ssd
ZENDOC_EDGECARE_SPEECH_MODEL=whisper_small

ZENDOC_LOCAL_AI_ENABLED=true
ZENDOC_LOCAL_AI_PROVIDER=openai_compatible
ZENDOC_LOCAL_AI_BASE_URL=http://127.0.0.1:<local-runtime-port>
ZENDOC_LOCAL_AI_MODEL=<exact-local-model-id>
```

The final provider/runtime values depend on the actual Qualcomm/Windows deployment path selected during hardware integration. Do not change labels to imply QNN/NPU use until it has been measured.

## 8. Qualcomm submission package

Emphasize:

- On-device AI and privacy.
- Snapdragon X target and measured deployment evidence.
- NPU/edge performance once measured.
- Offline/poor-connectivity value.
- Technical implementation: model conversion/deployment, routing, structured outputs, latency evidence, and safety boundaries.
- A live demonstration showing local inference without sending health-sensitive content to a cloud LLM.

Suggested title:

**ZENDOC EdgeCare AI — A Privacy-First, Offline-Capable Agentic Healthcare System for Snapdragon PCs**

Suggested one-line pitch:

**ZENDOC EdgeCare AI turns a Snapdragon-powered PC into a private healthcare intelligence hub that can understand user input, retrieve governed health context, and assist care workflows locally while reserving clinical decisions for deterministic safeguards and humans.**

## 9. IIT/Digital Health submission package

Use the same core product, but lead with the healthcare problem instead of the chipset:

- Fragmented patient records and provider discovery.
- Poor connectivity and digital access gaps.
- Consent-governed longitudinal Health Memory.
- Search-to-care continuity.
- Safe AI assistance and human/clinical boundaries.
- Scalability across clinics, hospitals, diagnostics, pharmacies, and patients.

The Snapdragon layer is still a technical advantage, but it should support the healthcare story rather than replace it.

## 10. Safety and submission claims

Allowed claims must match evidence. In particular:

- Do not say ZENDOC diagnoses disease.
- Do not say it prescribes medication autonomously.
- Do not say emergency dispatch is AI-controlled.
- Do not say a model ran on the Snapdragon NPU until evidence confirms it.
- Do not fabricate latency, accuracy, battery, privacy, user-count, hospital, provider, or deployment metrics.
- Do not describe a configured integration as live unless it is actually working in the demo environment.

## 11. Engineering completion checklist

- [x] Isolated competition branch created from production main.
- [x] EdgeCare runtime profile added.
- [x] Owner-only runtime verification API added.
- [x] Existing deterministic clinical safety boundary preserved.
- [x] Benchmark evidence is separated from target configuration.
- [x] Regression tests added for truthful hardware claims.
- [ ] Run the complete test suite in CI.
- [ ] Connect the final local runtime/model artifact.
- [ ] Integrate/verify local ASR path.
- [ ] Profile the chosen model on a real/hosted Snapdragon X target.
- [ ] Save real benchmark evidence and reviewer-verifiable report reference.
- [ ] Record a reliable end-to-end demo.
- [ ] Prepare the Qualcomm-specific pitch/submission.
- [ ] Prepare the healthcare/IIT-specific pitch/submission.
