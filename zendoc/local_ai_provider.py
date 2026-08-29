"""Provider-neutral, local-only structured inference adapters for Milestone 8.1."""
from __future__ import annotations

import ipaddress
import json
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlsplit


MAX_PROMPT_CHARS = 8_000
MAX_RESPONSE_BYTES = 1_048_576
MAX_OUTPUT_TEXT_CHARS = 12_000
MAX_INFERENCE_OUTPUT_TOKENS = 1_024
FORBIDDEN_ACTION_KEYS = {
    "arguments",
    "command",
    "execute",
    "filesystem",
    "function_call",
    "permissions",
    "python",
    "shell",
    "sql",
    "tool",
    "tool_call",
    "tool_calls",
}
STRUCTURED_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "output": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "data": {"type": "object"},
            },
            "required": ["text"],
            "additionalProperties": False,
        }
    },
    "required": ["output"],
    "additionalProperties": False,
}
SAFE_LOCAL_SYSTEM_PROMPT = (
    "You provide low-risk ZENDOC assistance only. Return JSON matching the supplied schema. "
    "Do not diagnose, prescribe, make emergency decisions, request tools, emit commands, change "
    "permissions, or claim that an action was executed. Put the user-facing suggestion in output.text."
)


class MalformedProviderResponse(ValueError):
    pass


class UnsafeModelOutput(ValueError):
    pass


@dataclass(frozen=True)
class LocalAISettings:
    enabled: bool
    provider: str
    base_url: str
    model: str
    timeout: int
    allow_private_network: bool = False

    @classmethod
    def from_runtime(cls) -> "LocalAISettings":
        return cls(
            enabled=_runtime_bool("LOCAL_AI_ENABLED", "ZENDOC_LOCAL_AI_ENABLED", "ZENDOC_SLM_ENABLED", False),
            provider=_runtime_value("LOCAL_AI_PROVIDER", "ZENDOC_LOCAL_AI_PROVIDER", "ZENDOC_SLM_PROVIDER", "ollama").lower(),
            base_url=_runtime_value(
                "LOCAL_AI_BASE_URL", "ZENDOC_LOCAL_AI_BASE_URL", "ZENDOC_SLM_BASE_URL", "http://127.0.0.1:11434"
            ).rstrip("/"),
            model=_runtime_value("LOCAL_AI_MODEL", "ZENDOC_LOCAL_AI_MODEL", "ZENDOC_SLM_MODEL", ""),
            timeout=_bounded_int(
                _runtime_value("LOCAL_AI_TIMEOUT", "ZENDOC_LOCAL_AI_TIMEOUT", "ZENDOC_SLM_TIMEOUT", "10"),
                1,
                120,
                10,
            ),
            allow_private_network=_runtime_bool(
                "LOCAL_AI_ALLOW_PRIVATE_NETWORK",
                "ZENDOC_LOCAL_AI_ALLOW_PRIVATE_NETWORK",
                None,
                False,
            ),
        )

    def validated_base_url(self) -> str:
        return validate_local_provider_url(self.base_url, self.allow_private_network)

    def fingerprint(self) -> tuple:
        return (
            self.enabled,
            self.provider,
            self.base_url,
            self.model,
            self.timeout,
            self.allow_private_network,
        )


@dataclass(frozen=True)
class LocalInferenceRequest:
    prompt: str
    task_type: str
    privacy_class: str
    system_prompt: str = ""
    max_output_tokens: int = 512


@dataclass
class LocalInferenceResult:
    success: bool
    provider: str
    model: str
    task_type: str
    output: dict
    latency_ms: int
    fallback_used: bool = False
    error_category: str | None = None
    privacy_class: str = "INTERNAL"
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "provider": self.provider,
            "model": self.model,
            "task_type": self.task_type,
            "output": dict(self.output),
            "latency_ms": max(0, int(self.latency_ms or 0)),
            "fallback_used": bool(self.fallback_used),
            "error_category": self.error_category,
            "privacy_class": self.privacy_class,
            "metadata": dict(self.metadata),
        }


@dataclass
class ProviderHealth:
    status: str
    provider: str
    server_status: str
    model_status: str
    model: str | None
    latency_ms: int | None
    message: str
    error_category: str | None = None
    last_successful_inference: str | None = None
    capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "provider": self.provider,
            "server_status": self.server_status,
            "model_status": self.model_status,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "message": self.message,
            "error_category": self.error_category,
            "last_successful_inference": self.last_successful_inference,
            "capabilities": list(self.capabilities),
        }


class BaseLocalAIProvider:
    provider_name = "local"

    def __init__(self, settings: LocalAISettings):
        self.settings = settings
        self.last_successful_inference: str | None = None

    def is_configured(self) -> bool:
        if not self.settings.enabled or not self.settings.model:
            return False
        try:
            self.settings.validated_base_url()
        except ValueError:
            return False
        return True

    def configuration_health(self) -> ProviderHealth | None:
        if not self.settings.enabled:
            return ProviderHealth(
                "disabled", self.provider_name, "not_checked", "not_checked", self.settings.model or None, None,
                "Local AI is disabled. Deterministic fallback remains available.",
            )
        if not self.settings.model:
            return ProviderHealth(
                "integration_required", self.provider_name, "not_checked", "not_configured", None, None,
                "Local SLM integration ready — model not configured.", "model_not_configured",
            )
        try:
            self.settings.validated_base_url()
        except ValueError:
            return ProviderHealth(
                "configuration_error", self.provider_name, "blocked", "not_checked", self.settings.model, None,
                "Local AI URL was rejected by the local/private endpoint policy.", "unsafe_provider_url",
            )
        return None

    def health_check(self) -> ProviderHealth:
        raise NotImplementedError

    def infer(self, request: LocalInferenceRequest) -> LocalInferenceResult:
        raise NotImplementedError

    def _failure(self, request: LocalInferenceRequest, started: float, category: str) -> LocalInferenceResult:
        return LocalInferenceResult(
            success=False,
            provider=self.provider_name,
            model=self.settings.model or "not_configured",
            task_type=request.task_type,
            output={},
            latency_ms=_elapsed(started),
            fallback_used=True,
            error_category=category,
            privacy_class=request.privacy_class,
        )


class OllamaLocalAIProvider(BaseLocalAIProvider):
    provider_name = "local_ollama"

    def health_check(self) -> ProviderHealth:
        configured = self.configuration_health()
        if configured:
            return configured
        started = time.perf_counter()
        try:
            data = _request_json(
                f"{self.settings.validated_base_url()}/api/tags",
                timeout=min(self.settings.timeout, 5),
            )
            models = data.get("models")
            if not isinstance(models, list):
                raise MalformedProviderResponse("Model list is missing.")
            installed = {
                str(item.get("name") or item.get("model") or "").strip()
                for item in models if isinstance(item, dict)
            }
            ready = any(_same_ollama_model(self.settings.model, candidate) for candidate in installed)
            if not ready:
                return ProviderHealth(
                    "model_missing", self.provider_name, "online", "missing", self.settings.model,
                    _elapsed(started), "Ollama is online, but the configured model is not installed.", "model_missing",
                    self.last_successful_inference, _local_capabilities(),
                )
            return ProviderHealth(
                "ready", self.provider_name, "online", "ready", self.settings.model, _elapsed(started),
                "Ollama is online and the configured model is ready.", None,
                self.last_successful_inference, _local_capabilities(),
            )
        except Exception as exc:
            category = _classify_provider_exception(exc)
            return ProviderHealth(
                category if category in {"timeout", "malformed_response"} else "unavailable",
                self.provider_name,
                "offline" if category in {"timeout", "provider_unavailable"} else "error",
                "unknown",
                self.settings.model,
                _elapsed(started),
                _health_message(category),
                category,
                self.last_successful_inference,
                _local_capabilities(),
            )

    def infer(self, request: LocalInferenceRequest) -> LocalInferenceResult:
        started = time.perf_counter()
        configured = self.configuration_health()
        if configured:
            return self._failure(request, started, configured.error_category or configured.status)
        try:
            prompt = _bounded_prompt(request.prompt)
            system = _safe_system_prompt(request.system_prompt)
            payload = {
                "model": self.settings.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "think": False,
                "format": STRUCTURED_OUTPUT_SCHEMA,
                "options": {
                    "temperature": 0,
                    "num_predict": _bounded_int(request.max_output_tokens, 16, MAX_INFERENCE_OUTPUT_TOKENS, 512),
                },
            }
            data = _request_json(
                f"{self.settings.validated_base_url()}/api/chat",
                payload=payload,
                timeout=self.settings.timeout,
            )
            message = data.get("message")
            if not isinstance(message, dict) or message.get("tool_calls"):
                raise UnsafeModelOutput("Tool calls are not accepted from model output.")
            output = validate_structured_model_content(message.get("content"))
            self.last_successful_inference = _now_iso()
            return LocalInferenceResult(
                True,
                self.provider_name,
                self.settings.model,
                request.task_type,
                output,
                _elapsed(started),
                privacy_class=request.privacy_class,
                metadata={
                    "structured_output": True,
                    "eval_count": _safe_nonnegative_int(data.get("eval_count")),
                },
            )
        except urllib.error.HTTPError as exc:
            category = "model_missing" if exc.code == 404 else "provider_error"
            return self._failure(request, started, category)
        except Exception as exc:
            return self._failure(request, started, _classify_provider_exception(exc))


class OpenAICompatibleLocalAIProvider(BaseLocalAIProvider):
    provider_name = "local_openai_compatible"

    def health_check(self) -> ProviderHealth:
        configured = self.configuration_health()
        if configured:
            return configured
        started = time.perf_counter()
        try:
            data = _request_json(
                f"{self.settings.validated_base_url()}/v1/models",
                timeout=min(self.settings.timeout, 5),
            )
            models = data.get("data")
            if not isinstance(models, list):
                raise MalformedProviderResponse("Model list is missing.")
            installed = {str(item.get("id") or "").strip() for item in models if isinstance(item, dict)}
            if self.settings.model not in installed:
                return ProviderHealth(
                    "model_missing", self.provider_name, "online", "missing", self.settings.model,
                    _elapsed(started), "Local server is online, but the configured model is missing.", "model_missing",
                    self.last_successful_inference, _local_capabilities(),
                )
            return ProviderHealth(
                "ready", self.provider_name, "online", "ready", self.settings.model, _elapsed(started),
                "Local OpenAI-compatible server and model are ready.", None,
                self.last_successful_inference, _local_capabilities(),
            )
        except Exception as exc:
            category = _classify_provider_exception(exc)
            return ProviderHealth(
                category if category in {"timeout", "malformed_response"} else "unavailable",
                self.provider_name,
                "offline" if category in {"timeout", "provider_unavailable"} else "error",
                "unknown",
                self.settings.model,
                _elapsed(started),
                _health_message(category),
                category,
                self.last_successful_inference,
                _local_capabilities(),
            )

    def infer(self, request: LocalInferenceRequest) -> LocalInferenceResult:
        started = time.perf_counter()
        configured = self.configuration_health()
        if configured:
            return self._failure(request, started, configured.error_category or configured.status)
        try:
            data = _request_json(
                f"{self.settings.validated_base_url()}/v1/chat/completions",
                payload={
                    "model": self.settings.model,
                    "messages": [
                        {"role": "system", "content": _safe_system_prompt(request.system_prompt)},
                        {"role": "user", "content": _bounded_prompt(request.prompt)},
                    ],
                    "temperature": 0,
                    "max_tokens": _bounded_int(request.max_output_tokens, 16, MAX_INFERENCE_OUTPUT_TOKENS, 512),
                    "response_format": {"type": "json_schema", "json_schema": {"name": "zendoc_output", "schema": STRUCTURED_OUTPUT_SCHEMA}},
                },
                timeout=self.settings.timeout,
            )
            choices = data.get("choices")
            message = choices[0].get("message") if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
            if not isinstance(message, dict) or message.get("tool_calls"):
                raise UnsafeModelOutput("Tool calls are not accepted from model output.")
            output = validate_structured_model_content(message.get("content"))
            self.last_successful_inference = _now_iso()
            return LocalInferenceResult(
                True, self.provider_name, self.settings.model, request.task_type, output, _elapsed(started),
                privacy_class=request.privacy_class, metadata={"structured_output": True},
            )
        except urllib.error.HTTPError as exc:
            return self._failure(request, started, "model_missing" if exc.code == 404 else "provider_error")
        except Exception as exc:
            return self._failure(request, started, _classify_provider_exception(exc))


class UnsupportedLocalAIProvider(BaseLocalAIProvider):
    provider_name = "local_unsupported"

    def is_configured(self) -> bool:
        return False

    def configuration_health(self) -> ProviderHealth:
        return self.health_check()

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            "configuration_error", self.provider_name, "not_checked", "not_checked", self.settings.model or None, None,
            "Unsupported local AI provider adapter.", "invalid_provider",
        )

    def infer(self, request: LocalInferenceRequest) -> LocalInferenceResult:
        return self._failure(request, time.perf_counter(), "invalid_provider")


def create_local_ai_provider(settings: LocalAISettings | None = None) -> BaseLocalAIProvider:
    settings = settings or LocalAISettings.from_runtime()
    if settings.provider == "ollama":
        return OllamaLocalAIProvider(settings)
    if settings.provider == "openai_compatible":
        return OpenAICompatibleLocalAIProvider(settings)
    return UnsupportedLocalAIProvider(settings)


def validate_local_provider_url(value: str, allow_private_network: bool = False) -> str:
    """Allow loopback endpoints by default; private IP literals require explicit opt-in."""
    parsed = urlsplit(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Local AI URL must use http/https and include a host.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Credentials, query strings, and fragments are not permitted in local AI URLs.")
    if parsed.path not in {"", "/"}:
        raise ValueError("Local AI base URL must not contain a path.")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("Local AI URL contains an invalid port.") from exc
    host = parsed.hostname.lower().rstrip(".")
    allowed = host == "localhost" or host.endswith(".localhost")
    try:
        address = ipaddress.ip_address(host)
        allowed = address.is_loopback or (
            allow_private_network and (address.is_private or address.is_link_local)
        )
    except ValueError:
        pass
    if not allowed:
        raise ValueError("Local AI URL must resolve to loopback, or use an explicitly allowed private IP literal.")
    return str(value).strip().rstrip("/")


def validate_structured_model_content(content) -> dict:
    if not isinstance(content, str) or not content.strip():
        raise MalformedProviderResponse("Structured model content is missing.")
    if len(content) > MAX_RESPONSE_BYTES:
        raise MalformedProviderResponse("Structured model content is too large.")
    try:
        parsed = json.loads(content)
    except (TypeError, json.JSONDecodeError) as exc:
        raise MalformedProviderResponse("Structured model content is invalid JSON.") from exc
    if not isinstance(parsed, dict) or set(parsed) != {"output"} or not isinstance(parsed["output"], dict):
        raise MalformedProviderResponse("Structured model content does not match the ZENDOC envelope.")
    output = parsed["output"]
    if not set(output).issubset({"text", "data"}):
        raise UnsafeModelOutput("Structured model content contains unsupported action fields.")
    text = output.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_OUTPUT_TEXT_CHARS:
        raise MalformedProviderResponse("Structured output text is missing or invalid.")
    data = output.get("data", {})
    if not isinstance(data, dict):
        raise MalformedProviderResponse("Structured output data must be an object.")
    _validate_safe_data(data)
    return {"text": text.strip(), "data": data}


def _validate_safe_data(value, depth: int = 0):
    if depth > 4:
        raise UnsafeModelOutput("Structured output nesting is too deep.")
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).strip().lower() in FORBIDDEN_ACTION_KEYS:
                raise UnsafeModelOutput("Model output attempted to provide an executable action.")
            _validate_safe_data(item, depth + 1)
    elif isinstance(value, list):
        if len(value) > 100:
            raise UnsafeModelOutput("Structured output list is too large.")
        for item in value:
            _validate_safe_data(item, depth + 1)
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise UnsafeModelOutput("Structured output contains an unsupported value type.")


def _request_json(url: str, *, payload: dict | None = None, timeout: int = 10) -> dict:
    body = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise MalformedProviderResponse("Provider response is too large.")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MalformedProviderResponse("Provider response is malformed.") from exc
    if not isinstance(data, dict):
        raise MalformedProviderResponse("Provider response must be a JSON object.")
    return data


def _runtime_value(config_key: str, env_key: str, legacy_env_key: str | None, default: str) -> str:
    try:
        from flask import current_app, has_app_context
        if has_app_context() and config_key in current_app.config:
            value = current_app.config.get(config_key)
            return str(value if value is not None else default).strip()
    except (ImportError, RuntimeError):
        pass
    value = os.environ.get(env_key)
    if value is None and legacy_env_key:
        value = os.environ.get(legacy_env_key)
    return str(default if value is None else value).strip()


def _runtime_bool(config_key: str, env_key: str, legacy_env_key: str | None, default: bool) -> bool:
    try:
        from flask import current_app, has_app_context
        if has_app_context() and config_key in current_app.config:
            value = current_app.config.get(config_key)
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "on"}
            return bool(value)
    except (ImportError, RuntimeError):
        pass
    value = os.environ.get(env_key)
    if value is None and legacy_env_key:
        value = os.environ.get(legacy_env_key)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _bounded_int(value, minimum: int, maximum: int, default: int) -> int:
    try:
        return max(minimum, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


def _bounded_prompt(prompt: str) -> str:
    value = str(prompt or "").strip()
    if not value:
        raise ValueError("Inference prompt is required.")
    return value[:MAX_PROMPT_CHARS]


def _safe_system_prompt(extra: str) -> str:
    extra = str(extra or "").strip()[:1_000]
    return f"{SAFE_LOCAL_SYSTEM_PROMPT}\nAdditional task context: {extra}" if extra else SAFE_LOCAL_SYSTEM_PROMPT


def _classify_provider_exception(exc: Exception) -> str:
    if isinstance(exc, UnsafeModelOutput):
        return "unsafe_model_output"
    if isinstance(exc, MalformedProviderResponse):
        return "malformed_response"
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(exc, urllib.error.HTTPError):
        return "provider_error"
    if isinstance(exc, urllib.error.URLError):
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            return "timeout"
        return "provider_unavailable"
    return "provider_error"


def _health_message(category: str) -> str:
    return {
        "timeout": "Local AI health check timed out.",
        "malformed_response": "Local AI server returned a malformed health response.",
        "provider_unavailable": "Local AI server is offline or unreachable.",
        "unsafe_model_output": "Local AI response was rejected by the output safety policy.",
    }.get(category, "Local AI provider returned an error.")


def _same_ollama_model(configured: str, installed: str) -> bool:
    configured = str(configured or "").strip()
    installed = str(installed or "").strip()
    return configured == installed or f"{configured}:latest" == installed or f"{installed}:latest" == configured


def _local_capabilities() -> list[str]:
    return [
        "structured_text",
        "low_risk_summarization",
        "intent_assistance",
        "navigation_help",
        "non_critical_extraction",
    ]


def _safe_nonnegative_int(value):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _elapsed(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
