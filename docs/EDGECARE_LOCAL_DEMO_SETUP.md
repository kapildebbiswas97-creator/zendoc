# ZENDOC EdgeCare AI — One-Machine Local Demo Setup

This guide gets the complete EdgeCare software flow running on a normal Windows laptop before any Snapdragon device is available.

It proves:

- ZENDOC starts locally;
- a local LLM is reachable;
- microphone capture works;
- audio stays on the local machine for the development ASR path;
- a local transcript appears in the ZENDOC AI composer;
- the transcript is never auto-submitted;
- the owner readiness page reports runtime truthfully;
- the connected-care demo can run deterministically with clearly labelled synthetic local records.

It does **not** prove Snapdragon/NPU acceleration. Real Qualcomm evidence is a separate final-device step.

## Required software

- Windows 11 recommended;
- Git;
- Python 3.11 x86-64/AMD64;
- Ollama for the ordinary-laptop LLM functional test;
- the optional Python packages in `requirements-edgecare-demo.txt` for local speech transcription.

A microphone is needed only if you want to test voice capture. Headphones are useful but not required.

## Terminal 1 — prepare ZENDOC

```powershell
git checkout competition/edgecare-ai-2026
git pull origin competition/edgecare-ai-2026
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-edgecare-demo.txt
```

Set development-only secrets locally. Never commit them:

```powershell
$env:ZENDOC_ENV="development"
$env:ZENDOC_SECRET_KEY="replace-with-a-long-random-local-secret"
$env:ZENDOC_ADMIN_EMAIL="your-owner-email@example.com"
$env:ZENDOC_ADMIN_PASSWORD="replace-with-a-strong-local-password"
```

## Optional but recommended — deterministic search and booking fixture

A fresh local database may not contain any connected provider with published availability. External/public search results are intentionally **not** treated as bookable. For a reliable recording, create the repository's development-only synthetic fixture.

Choose a local-only password of at least 12 characters and run:

```powershell
$env:ZENDOC_DEMO_PASSWORD="replace-with-a-local-only-demo-password"
python -m zendoc.edgecare_demo_data
```

The command creates/updates two visibly synthetic local accounts:

```text
Patient:  demo-patient@zendoc.local
Provider: demo-doctor@zendoc.local
```

Search location:

```text
Kalyani
```

The provider and patient names contain **DEMO ONLY**, and the provider biography explicitly says it is a synthetic competition fixture and not a real clinician/provider. The fixture creates availability for every weekday so the search → profile → slot → appointment path is deterministic.

**Never describe this fixture as a real doctor, clinic, user, pilot, customer or healthcare deployment.** The seeder refuses to run when ZENDOC is configured as production.

## Terminal 2 — local LLM

Install/start Ollama, then fetch a small development model:

```powershell
ollama pull llama3.2:3b
ollama serve
```

If Ollama is already running as a Windows service/application, do not start a second server.

This model is for software-flow verification only. It is not the final Qualcomm model evidence.

## Terminal 3 — local speech server

Activate the same virtual environment and start the repository bridge:

```powershell
.\.venv\Scripts\Activate.ps1
python -m zendoc.edgecare_demo_asr_server
```

Expected local endpoint:

```text
http://127.0.0.1:8001
```

Optional health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/healthz
```

Expected truth boundary includes:

```text
status = ready
npu_confirmed = false
```

The first Faster-Whisper launch may need to obtain the selected open-source model files if they are not already cached. Do this before the recording session.

## Terminal 1 — configure and start ZENDOC

In the ZENDOC terminal:

```powershell
$env:ZENDOC_EDGECARE_ENABLED="true"

$env:ZENDOC_LOCAL_AI_ENABLED="true"
$env:ZENDOC_LOCAL_AI_PROVIDER="ollama"
$env:ZENDOC_LOCAL_AI_BASE_URL="http://127.0.0.1:11434"
$env:ZENDOC_LOCAL_AI_MODEL="llama3.2:3b"
$env:ZENDOC_LOCAL_AI_TIMEOUT="60"

$env:ZENDOC_EDGECARE_ASR_ENABLED="true"
$env:ZENDOC_EDGECARE_ASR_PROVIDER="openai_compatible"
$env:ZENDOC_EDGECARE_ASR_BASE_URL="http://127.0.0.1:8001"
$env:ZENDOC_EDGECARE_SPEECH_MODEL="whisper_small"
$env:ZENDOC_EDGECARE_ASR_TIMEOUT="60"

python run.py
```

Or, after the admin variables are set, use the repository launcher:

```powershell
.\scripts\start_edgecare_local_demo.ps1
```

Open:

```text
http://127.0.0.1:5000
```

## Functional verification

Before making any competition recording:

1. Sign in with the configured owner account.
2. Open `/admin/edgecare`.
3. Confirm local LLM status is ready.
4. Confirm local ASR status is ready.
5. Run the fixed harmless local-model smoke test.
6. Sign in as `demo-patient@zendoc.local` if using the synthetic care fixture.
7. Open Find Care and search `Kalyani`.
8. Open the clearly labelled **DEMO ONLY** ZENDOC provider profile.
9. Choose a future date, select one published slot and request the appointment.
10. Open Appointments and confirm the request appears as requested/pending provider confirmation.
11. Open the ZENDOC AI Assistant.
12. Press **Use local voice input**.
13. Speak a short non-emergency request.
14. Stop recording.
15. Confirm the transcript appears in the textarea.
16. Confirm nothing is submitted automatically.
17. Review the transcript and press Send manually.
18. Confirm the normal ZENDOC safety layer remains active.

## If microphone capture fails

Use `http://127.0.0.1:5000` or HTTPS. Browser microphone APIs generally require a secure context; loopback localhost is treated as a trustworthy development origin by modern browsers.

Check Windows Settings → Privacy & security → Microphone and allow microphone access for the browser.

Typed input remains the supported fallback.

## If ASR is unavailable

Check:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/v1/models
```

If the server is not running, restart:

```powershell
python -m zendoc.edgecare_demo_asr_server
```

If Faster-Whisper is missing:

```powershell
python -m pip install -r requirements-edgecare-demo.txt
```

## If local LLM is unavailable

Check:

```powershell
ollama list
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

Confirm `llama3.2:3b` is present or set `ZENDOC_LOCAL_AI_MODEL` to the exact installed model name.

## Stop point before real competition evidence

When all functional-verification steps above pass, ordinary-laptop software work is complete.

Do **not** record statements such as "runs on Snapdragon NPU" or "NPU latency is X ms" unless you have real evidence.

For Qualcomm hardware evidence, use `docs/QUALCOMM_AI_HUB_RUNTIME_SETUP.md` to obtain an actual Snapdragon/Qualcomm model profile and record real measurement metadata. Only update `instance/edgecare_benchmark.json` with measured values from that real source.
