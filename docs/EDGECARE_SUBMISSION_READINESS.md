# ZENDOC EdgeCare AI — Submission Readiness

This file is the final truth checklist for competition submission. It separates completed engineering from evidence that can only come from a real Snapdragon/Qualcomm measurement session.

## Submission status legend

- **READY** — implemented and covered by repository validation.
- **RUNTIME REQUIRED** — code path exists, but a real local runtime/model must be connected on the demo machine.
- **HARDWARE EVIDENCE REQUIRED** — cannot be truthfully completed without a Snapdragon X device or Qualcomm-hosted profiling.

## Product demo path

| Area | Status | Submission evidence |
| --- | --- | --- |
| ZENDOC AI safety gate | READY | Deterministic high-risk routing remains enforced before model use. |
| Local language-model adapter | READY | Existing local provider adapter supports Ollama and OpenAI-compatible local runtimes. |
| Local ASR adapter | READY | `zendoc/edgecare_asr.py` sends bounded audio only to a configured local/private endpoint. |
| Local microphone capture | READY | AI page records with `MediaRecorder`; browser SpeechRecognition is not used by the competition control. |
| Voice transcript review | READY | Transcript is inserted into the editable AI composer; it is never auto-submitted. |
| Voice route authentication + CSRF | READY | `/edgecare/asr/transcribe` requires an authenticated session and normal ZENDOC CSRF protection. |
| Transcript persistence by ASR route | READY | The ASR route returns the transcript and does not write it to storage. |
| Typed-input fallback | READY | User can always type if microphone/runtime is unavailable. |
| Owner runtime status | READY | Owner API reports local LLM, local ASR, benchmark state and claim boundaries. |
| Local LLM model installed on demo machine | RUNTIME REQUIRED | Configure and verify the selected local model before recording the final demo. |
| Local ASR model installed on demo machine | RUNTIME REQUIRED | Configure and verify the selected Whisper-compatible model before recording the final demo. |
| Snapdragon X execution | HARDWARE EVIDENCE REQUIRED | Must be measured on real/hosted Snapdragon hardware. |
| NPU execution | HARDWARE EVIDENCE REQUIRED | Must be confirmed by runtime/profiling evidence; configuration alone is not proof. |
| Latency / throughput metrics | HARDWARE EVIDENCE REQUIRED | Record measured values only. Do not estimate. |

## Required demo-machine configuration

The competition branch does not enable local AI or local ASR automatically. Configure only the runtime that actually exists on the demonstration machine.

```bash
ZENDOC_EDGECARE_ENABLED=true

# Local language model
ZENDOC_LOCAL_AI_ENABLED=true
ZENDOC_LOCAL_AI_PROVIDER=openai_compatible
ZENDOC_LOCAL_AI_BASE_URL=http://127.0.0.1:<llm-port>
ZENDOC_LOCAL_AI_MODEL=<exact-local-model-id>

# Local speech recognition
ZENDOC_EDGECARE_ASR_ENABLED=true
ZENDOC_EDGECARE_ASR_PROVIDER=openai_compatible
ZENDOC_EDGECARE_ASR_BASE_URL=http://127.0.0.1:<asr-port>
ZENDOC_EDGECARE_SPEECH_MODEL=<exact-local-asr-model-id>
```

If the local service runs on a private LAN IP instead of loopback, use the explicit private-network opt-in only for the controlled demo environment.

## End-to-end demo acceptance test

The final recorded demo should pass every step below in one uninterrupted flow:

1. Sign in to ZENDOC as a patient/demo account.
2. Open **ZENDOC AI Assistant**.
3. Press **Use local voice input**.
4. Browser requests microphone permission.
5. Speak a low-risk healthcare navigation request such as: “Help me find the right kind of doctor for recurring back pain.”
6. Stop recording.
7. ZENDOC sends the clip to the configured local ASR runtime.
8. The transcript appears in the composer but is **not sent automatically**.
9. Review/edit the transcript and press **Send message**.
10. The deterministic safety layer runs before model routing.
11. ZENDOC returns bounded, non-diagnostic guidance.
12. Continue to provider discovery/finder if appropriate.
13. Show the owner EdgeCare runtime view/API and clearly distinguish:
    - configured target,
    - local runtime ready/not ready,
    - benchmark recorded/not recorded,
    - NPU measurement recorded/not recorded.

Do not use an emergency, diagnosis, prescribing, medication-change, payment, permission, arbitrary-code, arbitrary-SQL, or filesystem scenario as the model demo. Those intentionally remain deterministic or blocked.

## Real Snapdragon evidence package

Only after a genuine profiling session, create `instance/edgecare_benchmark.json` locally using the existing benchmark schema. Record:

- exact device;
- chipset;
- exact model artifact;
- exact runtime/execution provider;
- measurement timestamp;
- number of runs;
- success rate;
- median latency;
- p95 latency;
- whether NPU execution is explicitly confirmed;
- a reviewer-verifiable evidence reference.

Keep the raw Qualcomm AI Hub / device screenshots or reports with the submission package. Never put patient data, prompts, responses, secrets, API keys, or hidden reasoning in benchmark evidence.

## Submission claim rules

Safe claims before hardware measurement:

- “ZENDOC EdgeCare AI is designed for privacy-first local inference and local speech recognition.”
- “The competition branch includes governed local LLM and ASR adapters with deterministic clinical safety boundaries.”
- “Snapdragon X is the deployment target.”
- “The application distinguishes configured targets from measured hardware execution.”

Claims that require evidence first:

- “Runs on Snapdragon NPU.”
- “Achieves X ms latency.”
- “Uses Y% less power.”
- “Processes completely offline on the submitted hardware.”
- Any accuracy, battery, throughput, hospital, provider, or user-count metric not directly measured or documented.

## Final submission package

Prepare these artifacts after the real runtime/hardware session:

1. Working repository/commit reference.
2. Green CI screenshot or GitHub Actions link.
3. Short architecture diagram showing local ASR → safety gate → local model/RAG → care workflow.
4. End-to-end demo video.
5. Real Snapdragon/Qualcomm profiling evidence.
6. Benchmark evidence JSON/reference.
7. Qualcomm-focused pitch emphasizing edge AI, privacy, offline resilience, and measured execution.
8. Digital-health/IIT-focused pitch emphasizing continuity of care, Health Memory/RAG, safe AI, provider discovery, and poor-connectivity resilience.
9. Explicit limitations slide/section stating that ZENDOC does not autonomously diagnose, prescribe, alter medication, or dispatch emergency care.

## Merge gate

Do not merge the competition branch to production `main` solely to submit the competition build. Keep it isolated until:

- CI is green;
- the local runtime is verified on the intended demo machine;
- the final demo is stable;
- competition-specific settings do not weaken production security or reliability.

Hardware benchmark evidence may remain external/local if it contains machine-specific measurement metadata; production does not need to claim hardware verification merely because the competition build was measured.
