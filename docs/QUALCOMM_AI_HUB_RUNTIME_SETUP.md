# ZENDOC EdgeCare AI — Qualcomm AI Hub Runtime Setup

This runbook is for the final competition-device/profiling session. It keeps secrets out of the repository and separates local runtime integration from Qualcomm-hosted profiling evidence.

## 1. Snapdragon Windows Python environment

For Qualcomm AI Hub Models on a Snapdragon X Elite / X2 Elite Windows PC, use **AMD64/x86-64 (64-bit) Python**, not Windows ARM64 Python. Qualcomm's current AI Hub Models setup explicitly states that Windows ARM64 Python is not supported for these Snapdragon X systems.

Use Python in the supported range for the selected Qualcomm model recipe (currently Whisper-Small documents Python 3.10 <= version < 3.14). ZENDOC itself is tested with Python 3.11, so Python 3.11 AMD64 is the safest shared choice.

```powershell
python -m venv qai_hub
.\qai_hub\Scripts\activate
python -m pip install --upgrade pip
pip install qai-hub qai-hub-models
```

Whisper-Small's current Windows setup also documents FFmpeg as a system dependency:

```powershell
winget install ffmpeg
qai-hub-models install whisper_small
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
- Snapdragon X2 Elite CRD;
- another explicitly supported Snapdragon X compute target returned by Qualcomm AI Hub.

Use the exact device name returned by Qualcomm AI Hub rather than inventing a label.

## 4. Verify the Qualcomm model recipe first

Before connecting it to ZENDOC, verify the official model recipe independently.

For Whisper-Small:

```powershell
qai-hub-models info Whisper-Small
qai-hub-models perf Whisper-Small
python -m qai_hub_models.models.whisper_small.demo
```

Use the official model-specific export/profile instructions for the exact target device and runtime. Do not copy a command for a different device and present it as a Snapdragon X measurement.

## 5. Profiling workflow

The AI Hub flow is:

1. prepare/export the model;
2. compile for the desired target runtime;
3. submit a profile job to the exact Snapdragon target;
4. run inference on the hosted target if needed;
5. download profile results/artifacts;
6. record only measured evidence in the ZENDOC benchmark envelope.

Qualcomm AI Hub Models supports Windows deployment runtimes including ONNX and Qualcomm AI Engine Direct, and published model performance data distinguishes CPU/GPU/NPU execution. Preserve the exact runtime/provider reported by the profile rather than translating it into a stronger claim.

## 6. Speech runtime and ZENDOC bridge

ZENDOC's competition UI records a maximum of 30 seconds per voice clip.

The application ASR adapter expects a deliberately small OpenAI-compatible local transcription service:

```text
GET  /v1/models
POST /v1/audio/transcriptions
```

Two valid development stages exist:

### Stage A — ordinary laptop / software-flow proof

Use the repository's optional local CPU bridge:

```powershell
python -m pip install -r requirements-edgecare-demo.txt
python -m zendoc.edgecare_demo_asr_server
```

This bridge uses Faster-Whisper for local development and always reports `npu_confirmed: false`. It proves the ZENDOC browser → local ASR → editable transcript flow but is **not** Qualcomm/NPU evidence.

Configure ZENDOC for that bridge:

```powershell
$env:ZENDOC_EDGECARE_ASR_ENABLED="true"
$env:ZENDOC_EDGECARE_ASR_PROVIDER="openai_compatible"
$env:ZENDOC_EDGECARE_ASR_BASE_URL="http://127.0.0.1:8001"
$env:ZENDOC_EDGECARE_SPEECH_MODEL="whisper_small"
```

### Stage B — final Qualcomm/Snapdragon runtime

Replace only the speech backend with the actual Qualcomm/ONNX/QNN/Voice-AI implementation or wrapper. Keep the same ZENDOC HTTP contract. Do not label that backend as NPU-backed until the actual runtime/profile evidence explicitly confirms NPU execution.

## 7. Local language-model runtime

ZENDOC can connect to either the existing Ollama adapter or an OpenAI-compatible local server.

For ordinary-laptop functional testing, Ollama is acceptable and does not imply Snapdragon acceleration:

```powershell
$env:ZENDOC_LOCAL_AI_ENABLED="true"
$env:ZENDOC_LOCAL_AI_PROVIDER="ollama"
$env:ZENDOC_LOCAL_AI_BASE_URL="http://127.0.0.1:11434"
$env:ZENDOC_LOCAL_AI_MODEL="llama3.2:3b"
$env:ZENDOC_EDGECARE_ENABLED="true"
```

For the final competition machine, use the runtime that actually hosts the measured artifact, and set `ZENDOC_LOCAL_AI_MODEL` to the exact final model id.

Example OpenAI-compatible configuration:

```powershell
$env:ZENDOC_LOCAL_AI_ENABLED="true"
$env:ZENDOC_LOCAL_AI_PROVIDER="openai_compatible"
$env:ZENDOC_LOCAL_AI_BASE_URL="http://127.0.0.1:<llm-port>"
$env:ZENDOC_LOCAL_AI_MODEL="<exact-final-model-id>"
$env:ZENDOC_EDGECARE_ENABLED="true"
```

Do not use configured target/model names as evidence that inference happened on Snapdragon or on the NPU.

## 8. Verification before demo recording

With ZENDOC running on the final machine:

1. Sign in as the configured ZENDOC owner.
2. Open `/admin/edgecare`.
3. Confirm the local language-model status is `ready`.
4. Confirm local ASR status is `ready`.
5. Run the owner-only harmless local model smoke test.
6. Run one local voice transcription from the AI Assistant.
7. Verify the transcript appears for review and is not auto-submitted.
8. Run the full low-risk demo path.

The application may remain at `benchmark_required` once the local model runtime is ready. That is expected until genuine measurement evidence is recorded.

## 9. Collect real measurement evidence

After a genuine Qualcomm-hosted or local Snapdragon profiling session, download/save the raw profile output and note:

- job/profile identifier;
- exact target device;
- chipset;
- exact model artifact;
- runtime / execution provider;
- timestamp;
- measured latency values;
- number of runs / success rate when available;
- explicit NPU execution evidence, when provided.

Then create the local `instance/edgecare_benchmark.json` using the schema documented in `docs/EDGECARE_AI_2026.md`.

Never invent a value when the tool does not report it. Use `npu_confirmed: false` unless the evidence explicitly confirms NPU execution.

## 10. Evidence archive

For the submission folder, retain:

- Git commit SHA used for the demo;
- green GitHub Actions result;
- Qualcomm AI Hub profile/job URL or exported report;
- relevant screenshots showing the actual target/runtime;
- `edgecare_benchmark.json` (metadata only);
- demo video;
- architecture diagram;
- final pitch material.

Do not include API tokens, patient data, raw health records, prompts containing private health information, hidden reasoning, passwords, or private keys.
