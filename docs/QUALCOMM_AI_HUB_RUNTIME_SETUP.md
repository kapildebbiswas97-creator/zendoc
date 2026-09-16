# ZENDOC EdgeCare AI — Qualcomm AI Hub Runtime Setup

This runbook is for the final competition-device/profiling session. It keeps secrets out of the repository and separates local runtime integration from Qualcomm-hosted profiling evidence.

## 1. Windows on ARM environment

For a Snapdragon X Windows machine, use native Windows ARM64 Python 3.11 or newer and a virtual environment.

```powershell
python -m venv qai_hub
.\qai_hub\Scripts\activate
python -m pip install --upgrade pip
pip3 install qai-hub
```

Do not commit the Qualcomm API token to this repository, `.env`, screenshots, benchmark JSON, CI logs, or demo recordings.

## 2. Qualcomm AI Hub authentication

Sign in to Qualcomm AI Hub Workbench, obtain the API token from Account → Settings → API Token, then configure the client locally:

```powershell
qai-hub configure --api_token YOUR_TOKEN_FROM_WORKBENCH
qai-hub list-devices
```

A successful `list-devices` call confirms the workstation can submit jobs. The token remains a local credential and must never be added to ZENDOC source control.

## 3. Target device

For the competition target, prefer an available Snapdragon X compute target matching the final device, for example:

- Snapdragon X Elite CRD;
- Snapdragon X Plus 8-Core CRD;
- another explicitly supported Snapdragon X compute target if required by the competition environment.

Use the exact device name returned by Qualcomm AI Hub rather than inventing a label.

## 4. Profiling workflow

The official AI Hub flow is:

1. prepare/export the model;
2. compile for the desired target runtime;
3. submit a profile job to the Snapdragon target;
4. run inference on the hosted target if needed;
5. download profile results and artifacts;
6. record only measured evidence in the ZENDOC benchmark envelope.

For compute targets, Qualcomm documentation demonstrates `--target_runtime onnx` and profiling on a `Snapdragon X Elite CRD`. Use the model-specific instructions supplied by AI Hub for the chosen LLM/ASR artifact rather than copying a computer-vision example verbatim.

## 5. Speech runtime

ZENDOC's competition UI records a maximum of 30 seconds per voice clip. This is aligned with the documented Whisper-Small input window.

The repository ASR adapter expects an OpenAI-compatible local transcription service:

```text
GET  /v1/models
POST /v1/audio/transcriptions
```

The service may wrap the final Qualcomm/ONNX Runtime implementation, but ZENDOC must not label it as NPU-backed until the actual runtime/profiling evidence confirms NPU execution.

Environment variables:

```powershell
$env:ZENDOC_EDGECARE_ASR_ENABLED="true"
$env:ZENDOC_EDGECARE_ASR_PROVIDER="openai_compatible"
$env:ZENDOC_EDGECARE_ASR_BASE_URL="http://127.0.0.1:<asr-port>"
$env:ZENDOC_EDGECARE_SPEECH_MODEL="<exact-final-asr-model-id>"
```

## 6. Local language-model runtime

ZENDOC can connect to either the existing Ollama adapter or an OpenAI-compatible local server. For the competition demo, use the runtime that actually hosts the measured artifact.

Example OpenAI-compatible configuration:

```powershell
$env:ZENDOC_LOCAL_AI_ENABLED="true"
$env:ZENDOC_LOCAL_AI_PROVIDER="openai_compatible"
$env:ZENDOC_LOCAL_AI_BASE_URL="http://127.0.0.1:<llm-port>"
$env:ZENDOC_LOCAL_AI_MODEL="<exact-final-model-id>"
$env:ZENDOC_EDGECARE_ENABLED="true"
```

Do not use the configured target/model names as evidence that inference happened on Snapdragon or on the NPU.

## 7. Verification before demo recording

With ZENDOC running on the final machine:

1. Sign in as the configured ZENDOC owner.
2. Check `GET /api/v1/admin/edgecare/runtime` using an owner API token.
3. Confirm local language-model status is `ready`.
4. Confirm `local_asr.status` is `ready`.
5. Run the owner-only harmless local model smoke test.
6. Run one local voice transcription from the AI Assistant.
7. Verify the transcript appears for review and is not auto-submitted.
8. Run the full low-risk demo path.

The application may reach `benchmark_required` once the local model runtime is ready. That is expected until genuine measurement evidence is recorded.

## 8. Collect real measurement evidence

After a genuine Qualcomm-hosted or local Snapdragon profiling session, download/save the raw profile output and note:

- job/profile identifier;
- target device;
- chipset;
- model artifact;
- runtime / execution provider;
- timestamp;
- measured latency values;
- number of runs / success rate when available;
- explicit evidence of NPU execution, if provided.

Then create the local `instance/edgecare_benchmark.json` using the schema documented in `docs/EDGECARE_AI_2026.md`.

Never invent a value when the tool does not report it. Use `npu_confirmed: false` unless the evidence explicitly confirms NPU execution.

## 9. Evidence archive

For the submission folder, retain:

- Git commit SHA used for the demo;
- green GitHub Actions result;
- Qualcomm AI Hub profile/job URL or exported report;
- relevant screenshots that show the actual target and runtime;
- `edgecare_benchmark.json` (metadata only);
- demo video;
- architecture diagram;
- final pitch material.

Do not include API tokens, patient data, raw health records, prompts containing private health information, hidden reasoning, passwords, or private keys.
