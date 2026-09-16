# ZENDOC EdgeCare AI — Qualcomm Submission Package

## Submission identity

**Project:** ZENDOC EdgeCare AI

**Suggested title:**
ZENDOC EdgeCare AI — Privacy-First Healthcare Intelligence for Snapdragon PCs

**One-line pitch:**
ZENDOC EdgeCare AI adds governed local language and voice intelligence to an existing connected-care platform so users can navigate healthcare with privacy-first, offline-capable assistance while deterministic safeguards keep diagnosis, prescribing, emergency actions, permissions, payments, and tool execution outside model control.

## Why this qualifies as a significant AI modification

ZENDOC existed before the competition as a connected-health platform. The competition branch is not a simple reskin or unchanged prior project. It adds a new EdgeCare AI layer designed for Snapdragon-powered PCs:

- explicit Snapdragon X target profile;
- local language-model runtime adapter and readiness verification;
- local speech-recognition adapter;
- browser microphone capture using `MediaRecorder`;
- local-ASR transcription route with authentication, CSRF, type and size boundaries;
- editable transcript review before submission;
- deterministic clinical safety boundaries around all model use;
- owner-only runtime/measurement verification dashboard;
- strict separation of target configuration from real NPU measurement evidence;
- Qualcomm AI Hub profiling and final-runtime runbooks;
- regression coverage for truthful claims and voice/runtime safety.

Production `main` remains separate from the competition branch so the competition-specific AI work is auditable as a concrete modification.

---

# 1. Technical Implementation

## Architecture

```text
Patient voice / typed request
          |
          +---- typed ------------------------------------------+
          |                                                     |
          v                                                     |
Browser MediaRecorder                                           |
          |                                                     |
          v                                                     |
ZENDOC local ASR endpoint                                       |
          |                                                     |
          v                                                     |
Editable transcript --------------------------------------------+
          |
          v
Deterministic safety / privacy classification
          |
          +---- emergency / diagnosis / prescribing / high-risk
          |          -> deterministic safe flow / human escalation
          |
          v
Privacy-aware model router
          |
          +---- permitted low-risk local task
          |          -> local LLM -> structured advisory output
          |
          +---- approved knowledge / Health Memory context
          |
          v
User-reviewed care navigation
          |
          +---- provider discovery / appointments / records / care workflow
```

## Core engineering points

### Local language model

ZENDOC already has provider-neutral local adapters for:

- Ollama;
- OpenAI-compatible local runtimes.

The competition branch layers EdgeCare runtime truth and measurement status on top of that router.

### Local speech recognition

`zendoc/edgecare_asr.py` implements a bounded OpenAI-compatible local transcription client. It:

- accepts only supported audio media types;
- imposes a strict maximum audio size;
- validates local/private provider URLs using the existing local-AI security policy;
- exposes runtime/model readiness;
- does not persist the transcript itself;
- returns structured success/failure metadata.

The AI UI records at most 30 seconds per clip and sends the audio to the local ZENDOC transcription route. Browser `SpeechRecognition` is not used by the competition voice control.

### Safety architecture

The model router remains deterministic-first. Model output cannot directly execute:

- diagnosis;
- prescribing;
- medication changes;
- emergency dispatch;
- arbitrary code;
- arbitrary SQL;
- filesystem actions;
- permission changes;
- payment approval.

Model output is advisory and structured. High-risk flows remain deterministic or human-governed.

### Truthful hardware verification

The EdgeCare readiness model intentionally distinguishes:

1. Snapdragon target declared;
2. local runtime actually ready;
3. benchmark metadata actually recorded;
4. NPU execution explicitly recorded in evidence.

A configured target never becomes a performance/NPU claim automatically.

---

# 2. Application Use Case & Innovation

## Problem

Healthcare journeys are fragmented across provider search, appointments, medical records, family context, pharmacy, diagnostics and follow-up. Cloud-only AI can also create privacy, connectivity and latency concerns for health-sensitive interactions.

## ZENDOC EdgeCare approach

EdgeCare turns the user's device into a privacy-first intelligence layer around the connected-care workflow:

- local voice capture for natural interaction;
- local speech transcription target;
- local bounded language assistance target;
- deterministic safety gate before model use;
- consent-governed Health Memory / RAG context;
- continuity from assistance into provider discovery and care workflows;
- typed fallback when microphone or local runtime is unavailable.

## Differentiation

The innovation is not simply “a healthcare chatbot.” The product combines:

- longitudinal health context;
- care navigation;
- local AI;
- local voice;
- deterministic clinical boundaries;
- auditable runtime/measurement truth;
- real connected-care workflows.

The model is an assistance layer, not the authority controlling healthcare actions.

---

# 3. Deployment & Accessibility

## Snapdragon PC target

The competition branch is designed for Snapdragon-powered Windows PCs. Qualcomm AI Hub / hosted profiling is used for target validation and measurement evidence when available.

## Accessible interaction

Users can interact through:

- ordinary typed input;
- microphone input when supported;
- an editable voice transcript before sending;
- explicit status messages when microphone or local ASR is unavailable.

Voice input never removes the typed fallback.

## Poor-connectivity value

The architecture is intended to keep bounded language and speech processing local where the validated runtime supports it. Online services remain available for data that genuinely requires network access, such as live provider availability or synchronization.

Do not claim “fully offline” until the final demonstrated configuration is actually verified without required network dependencies.

## Runtime transparency

The owner `/admin/edgecare` page exposes:

- deployment target;
- local LLM readiness;
- local ASR readiness;
- benchmark presence;
- NPU evidence status;
- measured values only when evidence exists.

This makes the technical state visible during judging instead of hiding integration gaps.

---

# 4. Presentation & Documentation

The repository contains:

- `docs/EDGECARE_AI_2026.md` — architecture and dual-submission engineering runbook;
- `docs/EDGECARE_SUBMISSION_READINESS.md` — final truth/acceptance checklist;
- `docs/QUALCOMM_AI_HUB_RUNTIME_SETUP.md` — final device/profiling workflow;
- this file — criterion-mapped Qualcomm submission package;
- automated regression tests for runtime truth, ASR behavior, ASR route security and owner verification UI.

## Recommended live-demo order

1. Introduce the fragmented-care/privacy problem in 20–30 seconds.
2. Open ZENDOC AI Assistant.
3. Record one low-risk request with **Use local voice input**.
4. Show that the transcript appears for review and is not auto-submitted.
5. Send the reviewed request.
6. Show deterministic safety-aware guidance.
7. Continue into provider discovery or another real ZENDOC workflow.
8. Open `/admin/edgecare`.
9. Show local LLM and ASR readiness.
10. Show real Snapdragon benchmark/NPU evidence only if it has actually been recorded.
11. Close with the privacy + connected-care value proposition.

## Recommended demo request

“Help me find the right kind of doctor for recurring back pain and explain what information I should prepare before the appointment.”

This is suitable because it demonstrates navigation/assistance without turning the model into a diagnostic or emergency decision-maker.

---

# Submission form content

## Problem statement

Patients often move between disconnected healthcare systems for provider discovery, appointments, records, diagnostics, pharmacy and follow-up. When AI assistance is added as a cloud-only chatbot, health-sensitive interactions can also depend on connectivity and external processing. ZENDOC EdgeCare AI addresses both problems by adding governed local voice and language intelligence to a connected-care platform while keeping clinical and high-risk actions under deterministic safeguards and human control.

## Proposed solution

ZENDOC EdgeCare AI is a Snapdragon-PC-targeted healthcare assistance layer combining local speech recognition, bounded local language-model routing, consent-governed Health Memory/RAG context and connected provider/care workflows. A user's voice is recorded locally, transcribed through the configured local ASR runtime, shown for review, then passed through a deterministic safety/privacy gate before any permitted model assistance. The model can help summarize, organize, navigate and support provider discovery, but cannot diagnose, prescribe, alter medication, dispatch emergencies, approve payments/permissions or execute arbitrary tools.

## Innovation

EdgeCare treats on-device AI as a governed component of a healthcare operating workflow rather than an autonomous clinical agent. Its key differentiators are local voice + local model routing, longitudinal care context, search-to-care continuity, deterministic safety controls, and explicit proof boundaries that prevent configured hardware targets from being misrepresented as measured NPU execution.

## Technical implementation

The Flask-based ZENDOC platform includes provider-neutral local model adapters, an EdgeCare runtime status layer, a bounded OpenAI-compatible local ASR adapter, MediaRecorder-based microphone capture, authenticated/CSRF-protected transcription, structured model output validation, deterministic high-risk routing and an owner readiness dashboard. The competition branch is tested separately from production and contains dedicated regression coverage for runtime truth, ASR configuration, route security and UI verification.

## Deployment plan

The final demonstration will run on or be profiled for a supported Snapdragon X Windows target. Qualcomm AI Hub is used to identify/profile the chosen model artifact and collect genuine device/runtime metrics. The repository does not claim NPU execution, latency or performance until actual measurement evidence is recorded. Typed input remains available when voice/runtime capabilities are unavailable.

## Impact

The approach can make healthcare assistance more accessible in privacy-sensitive and connectivity-constrained settings while preserving continuity into real care workflows. It is designed to help users organize the next step and reach appropriate services without positioning an AI model as an autonomous doctor.

---

# Evidence still required before final submit

Do not replace these with estimates:

- exact final Snapdragon-powered HP/device target;
- exact deployed LLM artifact;
- exact deployed ASR artifact;
- real runtime/execution provider;
- successful local LLM test on final demo setup;
- successful local ASR test on final demo setup;
- real profiling job/report;
- measured latency/performance values;
- explicit NPU confirmation if available;
- final demo video/screenshots.

Everything else in this document can be prepared before hardware profiling; these evidence fields must come from the real final environment.
