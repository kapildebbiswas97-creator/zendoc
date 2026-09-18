# ZENDOC EdgeCare AI — Snapdragon AI Lab Build & Present Challenge 2026

This is the final preparation source for the **Snapdragon® AI Lab Build & Present Challenge — Qualcomm (2026)**. It maps the already-built ZENDOC competition layer to the exact public challenge rules without converting targets into evidence.

## Competition truth

Public challenge requirements currently state:

- individual participation;
- resident of India and age 18+;
- one submission per participant;
- proposed solution must be designed, developed, or intended to be optimised for Snapdragon-powered HP PCs;
- an existing project is permitted only when it has been significantly modified to add AI models from Qualcomm AI Hub or other open-source platforms;
- a properly submitted entry cannot be changed afterward;
- public deadline: **30 September 2026, 11:59 PM IST**.

Recheck the live Unstop challenge page immediately before final submission because organizer terms can change.

## Submission title

**ZENDOC EdgeCare AI — Privacy-First, Offline-Capable Agentic Healthcare for Snapdragon PCs**

## One-line pitch

ZENDOC EdgeCare AI turns a Snapdragon-powered PC into a privacy-first healthcare intelligence hub that can understand speech, use consent-governed health context, assist care navigation locally, and keep diagnosis, prescribing, emergency actions, payments and permission changes outside autonomous model control.

## Proposal description

ZENDOC EdgeCare AI is the on-device AI evolution of ZENDOC, an India-first healthcare continuity platform. The competition build significantly extends the pre-existing product with local open-source language-model routing, local speech-to-text, an editable voice workflow, EdgeCare runtime/readiness reporting, deterministic healthcare safety gates, consent-aware Health Memory and provenance-aware care discovery. It is designed for Snapdragon-powered HP PCs so sensitive low-risk assistance can run locally while real-world provider/service actions remain evidence-bound and human controlled. The architecture supports Qualcomm AI Hub profiling without claiming Snapdragon/NPU execution until genuine measurement evidence exists.

## Why this is a significant AI modification of the existing project

The challenge permits a pre-existing project only when significantly modified with Qualcomm AI Hub or open-source AI models. The competition branch adds a distinct EdgeCare layer rather than merely renaming the original ZENDOC product:

1. **Local open-source LLM path** — ZENDOC can route eligible, low-risk tasks to an Ollama or OpenAI-compatible local model runtime instead of requiring a cloud model.
2. **Local speech-to-text path** — the browser voice flow connects to a loopback OpenAI-compatible ASR service; the development bridge uses Faster-Whisper locally.
3. **Manual voice review** — microphone audio is transcribed locally into an editable composer and is never auto-submitted; the user explicitly presses Send.
4. **EdgeCare runtime truth states** — the owner-only readiness surface distinguishes configuration, local runtime readiness, benchmark evidence and NPU-confirmed evidence.
5. **Snapdragon deployment contract** — the runtime is designed so the local LLM/ASR backend can be replaced by the actual Qualcomm/ONNX/QNN implementation while preserving the same safety and application interfaces.
6. **Qualcomm AI Hub profiling workflow** — the repository includes a dedicated runbook for compiling/profiling the chosen model against a real supported Snapdragon target and recording only genuine measurements.
7. **Healthcare safety architecture** — local model output remains advisory; deterministic policy controls diagnosis, prescribing, medicine changes, emergency actions, payments, permissions and tool execution.

## Current implemented product path

A competition demo can show one coherent journey:

**Voice/text goal → deterministic safety gate → local AI assistance → consent-governed Health Memory → provenance-aware care discovery → provider profile → real connected availability where present → appointment request → CareLoop continuity.**

External/public/map healthcare listings remain discovery-only unless a real ZENDOC connection proves booking or fulfillment capability.

## Target model/runtime direction

Development path already supported by the repository:

- **Speech:** Faster-Whisper local development bridge, with `whisper_small` as the competition target model identifier.
- **Language:** local Ollama/OpenAI-compatible runtime, with a small open-source instruct model for low-risk assistance.
- **Final Snapdragon direction:** use the exact Qualcomm AI Hub-supported model artifact and target returned by the real profiling environment.

A configured target name is not measurement evidence. Until a Qualcomm AI Hub or physical Snapdragon run exists, describe the system as **designed/intended for Snapdragon optimisation**, not as NPU-verified.

## Evaluation mapping

### Technical Implementation

- local model routing and health checks;
- local ASR adapter with bounded upload and privacy headers;
- deterministic safety and permission controls before model/tool actions;
- consent-aware Health Memory and governed retrieval;
- provider provenance and discovery-vs-confirmation separation;
- appointment/CareLoop continuity;
- automated SQLite, PostgreSQL, security and regression test gates.

### Application Use Case & Innovation

ZENDOC addresses the fragmentation between healthcare records, AI assistance, care discovery, appointments and follow-up. The EdgeCare layer moves sensitive low-risk intelligence toward the local device while retaining human/clinical authority for consequential decisions.

### Deployment & Accessibility

- Windows/Python local setup path;
- local LLM and local ASR paths;
- web UI usable from the same machine;
- optional online services only where real external data/workflows are needed;
- architecture intended for Snapdragon-powered HP PCs.

### Presentation & Documentation

Repository contains:

- root README with app description, developer contact, setup, run and test instructions;
- Apache-2.0 `LICENSE`;
- `docs/EDGECARE_LOCAL_DEMO_SETUP.md`;
- `docs/QUALCOMM_AI_HUB_RUNTIME_SETUP.md`;
- `docs/DEMO_RELEASE_CHECKLIST.md`;
- `docs/EDGECARE_SUBMISSION_READINESS.md`;
- this exact Qualcomm 2026 submission package.

## Evidence already available

- isolated competition branch: `competition/edgecare-ai-2026`;
- PR #68 intentionally remains separate from production `main`;
- safety, authentication, CSRF, authorization, privacy and owner-only administration preserved;
- local LLM integration path implemented;
- local Faster-Whisper ASR development bridge implemented;
- microphone → editable transcript → manual-send workflow implemented;
- Health Memory, care discovery, appointments/CareLoop, family care, messaging and Mental Wellness competition surfaces retained;
- Apache-2.0 license present;
- exact competition branch previously passed the complete repository production gate at baseline commit `ddbb4a6d18364527c730e626d3770717ee03d973`.

The final submission SHA must be rechecked after any later documentation/code commit.

## Evidence that must remain truthful

Do not claim any of the following without real evidence:

- Snapdragon/NPU execution;
- Qualcomm AI Hub benchmark values;
- latency, throughput, power or battery improvements;
- clinical accuracy or diagnostic performance;
- autonomous diagnosis or prescription;
- real pharmacy stock, insurance approval or emergency dispatch;
- provider confirmation from a public/map listing;
- hospitals, users, pilots, revenue or partnerships that do not exist.

## High-value final evidence (not to be fabricated)

Before final submission, collect as much of the following as is genuinely available:

1. local LLM status `ready` on the demo machine;
2. local ASR status `ready` on the demo machine;
3. microphone → local transcript → editable composer → manual Send recording;
4. uninterrupted low-risk product demo with no 404/500 on shown routes;
5. Qualcomm AI Hub job/profile identifier and exact target/model/runtime if profiling is completed;
6. measured values copied exactly from the profiling source;
7. demo video/screenshots that contain no patient secrets, API keys or passwords.

The public challenge wording allows a solution **intended to be optimised** for Snapdragon-powered HP PCs, so genuine Snapdragon profiling strengthens the submission but must never be invented merely to fill a field.

## Final form answer bank

**Project / solution name**  
ZENDOC EdgeCare AI

**Short tagline**  
Privacy-first, offline-capable healthcare intelligence designed for Snapdragon PCs.

**What problem does it solve?**  
Healthcare journeys are fragmented across records, provider discovery, appointments and follow-up, while cloud-first AI can create privacy, connectivity and trust problems. ZENDOC EdgeCare AI brings governed low-risk AI assistance closer to the user while preserving evidence and human authority for consequential healthcare actions.

**What is innovative?**  
It combines longitudinal Health Memory, local speech/LLM assistance, deterministic safety, consent, provenance-aware healthcare discovery and closed-loop care coordination in one system. The model is intentionally not the clinical authority.

**How is it designed for Snapdragon-powered HP PCs?**  
The EdgeCare layer separates the application from the local inference backend through bounded local model and ASR adapters. This allows the chosen open-source/Qualcomm AI Hub model artifact to be profiled and deployed on a supported Snapdragon target without changing the healthcare safety and consent architecture.

**Existing-project modification statement**  
ZENDOC existed before the challenge. For this submission it has been significantly modified with an EdgeCare AI layer including local open-source LLM routing, Faster-Whisper speech-to-text, manual-review voice interaction, local-runtime readiness states, Snapdragon-target deployment/profiling contracts and deterministic healthcare safety boundaries.

**Current evidence statement**  
The software architecture and local open-source AI paths are implemented and regression-tested. Snapdragon/NPU performance is not claimed unless separately supported by genuine Qualcomm AI Hub or physical-device evidence.

## Final submission gate

Before pressing the irreversible final-submit button:

- [ ] confirm personal eligibility and individual participation;
- [ ] confirm the exact project title;
- [ ] proofread all Unstop fields;
- [ ] verify no confidential health information, credentials or trade secrets are included;
- [ ] verify all claims match actual evidence;
- [ ] record the final competition-branch commit SHA and green CI run;
- [ ] attach/link only artifacts explicitly requested by the live form;
- [ ] remember that only the first submission is eligible and a submitted entry cannot be edited.

Do not merge PR #68 into `main` merely for this submission.