# ZENDOC Milestone 8.1 — Local AI Runtime and Model Router 2.0

## Status

Milestone 8.1 provides a real, optional local inference path. Ollama and an OpenAI-compatible local adapter are implemented. The application does not install a server, download a model, or claim inference succeeded merely because configuration exists.

The default state is **INTEGRATION REQUIRED**: local AI is disabled and no model is selected. Deterministic safety and deterministic fallback remain **WORKING** in every provider state.

## Architecture

```text
request
  -> deterministic emergency and safety policy
  -> deterministic-only task policy
  -> local AI for allowed low-risk tasks
  -> explicitly approved cloud AI when privacy policy permits
  -> deterministic local fallback

validated model suggestion
  -> safety policy -> planner -> permission check -> approval (when required) -> bounded executor
```

Model output is advisory. It has no direct reference to the tool registry or executor. A strict JSON envelope is required and action-like fields such as `tool_calls`, `shell`, `sql`, `python`, `permissions`, and `execute` are rejected.

## Configuration

Canonical environment variables:

```text
ZENDOC_LOCAL_AI_ENABLED=false
ZENDOC_LOCAL_AI_PROVIDER=ollama
ZENDOC_LOCAL_AI_BASE_URL=http://127.0.0.1:11434
ZENDOC_LOCAL_AI_MODEL=
ZENDOC_LOCAL_AI_TIMEOUT=10
ZENDOC_LOCAL_AI_ALLOW_PRIVATE_NETWORK=false
```

`ZENDOC_SLM_*` remains a read-only compatibility alias for existing M8 environments. New deployments should use `ZENDOC_LOCAL_AI_*`.

By default, the local base URL must be loopback (`127.0.0.1`, `::1`, `localhost`, or a reserved `.localhost` name). A private IP literal can be enabled deliberately with `ZENDOC_LOCAL_AI_ALLOW_PRIVATE_NETWORK=true`; public hosts, hostname-based private-network guessing, URL credentials, paths, queries, and fragments are rejected. The local-AI API is not exposed as an application proxy.

## Optional Ollama Setup

These are human-run examples, not installation actions performed by ZENDOC:

```powershell
ollama serve
ollama pull llama3.2:3b
$env:ZENDOC_LOCAL_AI_ENABLED="true"
$env:ZENDOC_LOCAL_AI_PROVIDER="ollama"
$env:ZENDOC_LOCAL_AI_BASE_URL="http://127.0.0.1:11434"
$env:ZENDOC_LOCAL_AI_MODEL="llama3.2:3b"
$env:ZENDOC_LOCAL_AI_TIMEOUT="10"
python run.py
```

The owner can then open Command Center 2.0 and use **Test Local AI**. That operation uses one fixed, harmless ZENDOC navigation question; it does not accept a caller-supplied prompt.

Practical starting points vary by quantization, context size, OS, and available memory:

| Machine class | Models to evaluate | Operational note |
|---|---|---|
| Low RAM | Qwen 3 0.6B/1.7B or Gemma 3 1B | Smallest footprint; validate structured-output quality for the selected task set. |
| Development laptop | Llama 3.2 3B, Qwen 3 4B, or Gemma 3 4B | Reasonable starting class for local development. |
| Stronger machine | Qwen 3 8B or Gemma 3 12B | Higher resource use; benchmark latency before increasing request timeout. |

Use an exact model tag present in the local Ollama library. These are general-purpose model families, not ZENDOC-trained models, medical devices, or clinically certified diagnostic models.

## Runtime States

The provider health adapter distinguishes:

- `disabled`: local AI is intentionally off; no network call occurs.
- `integration_required`: no model is configured.
- `configuration_error`: provider adapter or URL violates configuration policy.
- `unavailable`: server is offline/unreachable or returns a provider error.
- `timeout`: the bounded health/inference request timed out.
- `malformed_response`: provider JSON or the structured model envelope is invalid.
- `model_missing`: server is online but the configured model is absent.
- `ready`: server is online and its model inventory contains the configured model.

Inference success is recorded only after the HTTP response and strict structured output both validate.

## Routing and Privacy Policy

Privacy classes are `PUBLIC`, `INTERNAL`, `PERSONAL`, `HEALTH_SENSITIVE`, and `HIGH_RISK`.

- Emergency and high-risk actions are deterministic first and never wait for a model.
- Diagnosis, prescribing, prescription changes, ambulance dispatch, payment approval, permission/Admin changes, arbitrary SQL, shell, Python, code, and filesystem actions are deterministic-only/blocked model tasks.
- Local AI is allowed for bounded low-risk intent help, summarization, navigation, platform help, provider-query understanding, rewriting, non-critical extraction, owner operational summaries, and low-risk planning assistance.
- Cloud inference is opt-in per request. `HEALTH_SENSITIVE` and `HIGH_RISK` are always cloud-blocked. `PERSONAL` additionally requires explicit cloud consent.
- A local provider failure never relaxes cloud privacy policy.
- Model configuration never changes actor authorization, tool permissions, approval requirements, or owner identity enforcement.

## Structured Interface

Providers must return content matching:

```json
{
  "output": {
    "text": "bounded advisory text",
    "data": {}
  }
}
```

ZENDOC returns a normalized result with `success`, `provider`, `model`, `task_type`, `output`, `latency_ms`, `fallback_used`, routing/error metadata, and privacy class. Empty, oversized, malformed, extra-field, nested-action, and provider tool-call responses fail safely.

## Observability and Command Center

The owner-only AI Runtime view shows provider/server/model states, health latency, capabilities, last successful inference, recent routing metadata, provider errors, fallback counts/reasons, cloud configuration state, and privacy restrictions.

`model_execution_logs` stores only metadata: actor reference, task/intent category, provider, model, routing reason, latency, success, fallback flag/reason, error category, privacy class, structured-output flag, and timestamp. Raw prompts, responses, medical content, API keys, credentials, tokens, and hidden chain-of-thought are not schema fields and are not logged.

Owner-only endpoints:

- `GET /api/v1/admin/model-router`
- `POST /api/v1/admin/model-router/test`
- `POST /admin/ai-runtime/test`

## Resilience and Compatibility

The application starts normally when Ollama is absent, stopped, disabled, missing a model, timing out, or returning malformed output. A failure is converted to metadata and deterministic fallback rather than an application exception.

The additive migration `m8_1_local_ai_runtime_v1` adds privacy/fallback/structured fields after old M8 tables exist and preserves legacy rows. It does not alter users, owner reconciliation, health records, or associated data.

## Capability Matrix

- **WORKING:** deterministic emergency handling, deterministic-only task policy, privacy policy, strict response validation, fallback, metadata logging, owner authorization.
- **BETA:** Ollama and OpenAI-compatible local inference adapters, owner AI Runtime controls.
- **INTEGRATION REQUIRED:** an installed/running local server and explicitly selected model; cloud provider credentials if cloud use is desired.
- **FUTURE:** ZENDOC-proprietary trained model, clinical validation/certification, autonomous prescribing (blocked and not planned without legal/clinical governance).

