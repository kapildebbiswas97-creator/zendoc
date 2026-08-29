"""
ZENDOC Model Router — Milestone 8
Decides which intelligence backend should handle a task.

Architecture:
  1. deterministic_safety  – always first for emergency detection
  2. local_slm             – Ollama / llama.cpp / OpenAI-compatible local endpoint
  3. cloud_llm             – external provider (OpenAI, Gemini, Claude, etc.)
  4. local_fallback        – built-in rule-based answers

Never fabricates confidence. Never pretends local SLM ran if not configured.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field


# ── Risk classes ───────────────────────────────────────────────────────────────
class RiskClass:
    READ_ONLY         = "read_only"
    LOW_RISK          = "low_risk"
    CONSENT_REQUIRED  = "consent_required"
    DOCTOR_APPROVAL   = "doctor_approval"
    OWNER_APPROVAL    = "owner_approval"
    CRITICAL_BLOCKED  = "critical_blocked"


# ── Routing categories ─────────────────────────────────────────────────────────
class RoutingReason:
    DETERMINISTIC_SAFETY   = "deterministic_safety"
    LOCAL_SLM              = "local_slm"
    CLOUD_LLM              = "cloud_llm"
    LOCAL_FALLBACK         = "local_fallback"
    PROVIDER_UNAVAILABLE   = "provider_unavailable"


# ── Common response type ───────────────────────────────────────────────────────
@dataclass
class ModelResponse:
    text: str
    provider: str
    model: str
    latency_ms: int
    success: bool
    fallback_used: bool = False
    # confidence is deliberately absent — we do NOT fabricate it
    routing_reason: str = RoutingReason.LOCAL_FALLBACK
    error_category: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "provider": self.provider,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "success": self.success,
            "fallback_used": self.fallback_used,
            "routing_reason": self.routing_reason,
            "error_category": self.error_category,
            "metadata": self.metadata,
        }


# ── SLM Provider (Ollama / llama.cpp / OpenAI-compatible local endpoint) ──────
class SLMProvider:
    """
    Adapter for a local/open small language model.

    Supported endpoints:
      - Ollama  (http://localhost:11434)
      - llama.cpp server (OpenAI-compatible)
      - Any OpenAI-compatible local inference server
      - Future ZENDOC fine-tuned SLM

    Environment config:
      ZENDOC_SLM_ENABLED   1/true/yes
      ZENDOC_SLM_PROVIDER  ollama | openai_compatible
      ZENDOC_SLM_BASE_URL  http://localhost:11434
      ZENDOC_SLM_MODEL     llama3.2:3b
      ZENDOC_SLM_TIMEOUT   10
    """

    name = "local_slm"

    def __init__(self):
        self.enabled = _env_bool("ZENDOC_SLM_ENABLED", False)
        self.provider = os.environ.get("ZENDOC_SLM_PROVIDER", "ollama").strip().lower()
        self.base_url = os.environ.get("ZENDOC_SLM_BASE_URL", "http://localhost:11434").rstrip("/")
        self.model = os.environ.get("ZENDOC_SLM_MODEL", "").strip()
        self.timeout = int(os.environ.get("ZENDOC_SLM_TIMEOUT", "10") or "10")

    def is_configured(self) -> bool:
        return bool(self.enabled and self.model and self.provider in {"ollama", "openai_compatible"})

    def status(self) -> dict:
        if not self.enabled or not self.model:
            return {
                "status": "integration_required",
                "provider": self.provider,
                "message": "Local SLM integration ready — model not configured.",
            }
        if self.provider not in {"ollama", "openai_compatible"}:
            return {"status": "integration_required", "provider": self.provider, "message": "Unsupported local SLM provider adapter."}
        return {
            "status": "configured",
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "timeout": self.timeout,
            "message": "Local SLM configured — connectivity not tested at startup.",
        }

    def complete(self, prompt: str, system_prompt: str = "") -> ModelResponse:
        """
        Call the local SLM endpoint. Returns truthful error if not configured
        or unreachable. NEVER pretends inference occurred.
        """
        if not self.is_configured():
            return ModelResponse(
                text="Local ZENDOC SLM is not configured. A fallback provider was used.",
                provider="local_slm",
                model=self.model or "not_configured",
                latency_ms=0,
                success=False,
                fallback_used=True,
                routing_reason=RoutingReason.PROVIDER_UNAVAILABLE,
                error_category="not_configured",
            )

        started = time.perf_counter()
        try:
            if self.provider == "ollama":
                return self._call_ollama(prompt, system_prompt, started)
            elif self.provider == "openai_compatible":
                return self._call_openai_compatible(prompt, system_prompt, started)
            else:
                return ModelResponse(
                    text=f"Unknown SLM provider '{self.provider}'. Configure ZENDOC_SLM_PROVIDER.",
                    provider="local_slm",
                    model=self.model,
                    latency_ms=_elapsed(started),
                    success=False,
                    fallback_used=True,
                    routing_reason=RoutingReason.PROVIDER_UNAVAILABLE,
                    error_category="invalid_provider",
                )
        except Exception as exc:
            return ModelResponse(
                text="Local SLM is not reachable. A fallback provider was used.",
                provider="local_slm",
                model=self.model,
                latency_ms=_elapsed(started),
                success=False,
                fallback_used=True,
                routing_reason=RoutingReason.PROVIDER_UNAVAILABLE,
                error_category=_classify_connection_error(exc),
                metadata={"error": str(exc)[:200]},
            )

    def _call_ollama(self, prompt: str, system_prompt: str, started: float) -> ModelResponse:
        import urllib.request, json as _json

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = _json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": False,
        }).encode()

        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = _json.loads(resp.read().decode())

        text = (data.get("message") or {}).get("content") or data.get("response") or ""
        return ModelResponse(
            text=text.strip(),
            provider="local_slm_ollama",
            model=self.model,
            latency_ms=_elapsed(started),
            success=True,
            routing_reason=RoutingReason.LOCAL_SLM,
            metadata={"done": data.get("done"), "eval_count": data.get("eval_count")},
        )

    def _call_openai_compatible(self, prompt: str, system_prompt: str, started: float) -> ModelResponse:
        import urllib.request, json as _json

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = _json.dumps({
            "model": self.model,
            "messages": messages,
        }).encode()

        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = _json.loads(resp.read().decode())

        text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        return ModelResponse(
            text=text.strip(),
            provider="local_slm_openai_compatible",
            model=self.model,
            latency_ms=_elapsed(started),
            success=True,
            routing_reason=RoutingReason.LOCAL_SLM,
        )


# ── Cloud LLM Provider (OpenAI-compatible adapter) ────────────────────────────
class CloudLLMProvider:
    """
    Adapter for external cloud LLM (OpenAI, Gemini, Claude, etc.).
    Actual API keys come from environment variables only.
    """
    name = "cloud_llm"

    def __init__(self):
        self.provider = os.environ.get("ZENDOC_AI_PROVIDER", "").strip().lower()
        self.api_key = os.environ.get("ZENDOC_AI_API_KEY", "").strip()
        default_url = "https://api.openai.com" if self.provider == "openai" else ""
        self.base_url = os.environ.get("ZENDOC_AI_BASE_URL", default_url).strip().rstrip("/")
        self.model = os.environ.get("ZENDOC_AI_MODEL", "").strip()
        self.timeout = max(1, min(int(os.environ.get("ZENDOC_AI_TIMEOUT", "20") or "20"), 120))

    def is_configured(self) -> bool:
        return bool(
            self.provider in {"openai", "openai_compatible"}
            and self.api_key and self.base_url and self.model
        )

    def status(self) -> dict:
        missing = []
        if not self.provider:
            missing.append("ZENDOC_AI_PROVIDER")
        if not self.api_key:
            missing.append("ZENDOC_AI_API_KEY")
        if not self.base_url:
            missing.append("ZENDOC_AI_BASE_URL")
        if not self.model:
            missing.append("ZENDOC_AI_MODEL")
        if missing:
            return {"status": "integration_required", "provider": self.provider or None, "message": f"Cloud LLM integration requires: {', '.join(missing)}."}
        if self.provider not in {"openai", "openai_compatible"}:
            return {"status": "integration_required", "provider": self.provider, "message": "Cloud provider adapter is not implemented."}
        return {
            "status": "configured",
            "provider": self.provider,
            "model": self.model,
            "message": f"Cloud LLM provider '{self.provider}' configured — connectivity not verified.",
        }

    def complete(self, prompt: str, system_prompt: str = "") -> ModelResponse:
        if not self.is_configured():
            return ModelResponse(
                text="External AI provider is not configured. Local fallback was used.",
                provider="cloud_llm",
                model="not_configured",
                latency_ms=0,
                success=False,
                fallback_used=True,
                routing_reason=RoutingReason.PROVIDER_UNAVAILABLE,
                error_category="not_configured",
            )
        if self.provider not in {"openai", "openai_compatible"}:
            return ModelResponse(
                text=f"Cloud provider adapter '{self.provider}' is not implemented. Local fallback was used.",
                provider=f"cloud_llm_{self.provider}",
                model=self.model,
                latency_ms=0,
                success=False,
                fallback_used=True,
                routing_reason=RoutingReason.PROVIDER_UNAVAILABLE,
                error_category="adapter_not_implemented",
            )
        import json as _json
        import urllib.request

        started = time.perf_counter()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        request = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=_json.dumps({"model": self.model, "messages": messages}).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = _json.loads(response.read().decode())
            text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            if not str(text).strip():
                raise ValueError("Provider returned an empty response.")
            return ModelResponse(
                text=str(text).strip(),
                provider=f"cloud_llm_{self.provider}",
                model=self.model,
                latency_ms=_elapsed(started),
                success=True,
                routing_reason=RoutingReason.CLOUD_LLM,
            )
        except Exception as exc:
            return ModelResponse(
                text="Cloud LLM is unavailable. Local fallback was used.",
                provider=f"cloud_llm_{self.provider}",
                model=self.model,
                latency_ms=_elapsed(started),
                success=False,
                fallback_used=True,
                routing_reason=RoutingReason.PROVIDER_UNAVAILABLE,
                error_category=_classify_connection_error(exc),
                metadata={"error": str(exc)[:200]},
            )


# ── Local Fallback (deterministic, always available) ──────────────────────────
class LocalFallbackProvider:
    name = "local_fallback"

    def complete(self, prompt: str, intent: str = "general") -> ModelResponse:
        started = time.perf_counter()
        text = _deterministic_response(intent, prompt)
        return ModelResponse(
            text=text,
            provider="local_fallback",
            model="zendoc_deterministic_v1",
            latency_ms=_elapsed(started),
            success=True,
            routing_reason=RoutingReason.LOCAL_FALLBACK,
        )


# ── Model Router ───────────────────────────────────────────────────────────────
class ModelRouter:
    """
    Routes tasks to the appropriate intelligence backend.

    Routing policy:
      1. Emergency detection → ALWAYS deterministic safety first
      2. Simple classification / routing → prefer local SLM when configured
      3. Privacy-sensitive health info → explicit policy gate before cloud
      4. Complex planning / reasoning → cloud LLM if configured
      5. Always falls back to local_fallback

    Records routing decision metadata. Never stores hidden chain-of-thought.
    """

    def __init__(self):
        self.slm = SLMProvider()
        self.cloud = CloudLLMProvider()
        self.fallback = LocalFallbackProvider()
        self._routing_stats = {
            "deterministic": 0,
            "local_slm": 0,
            "cloud_llm": 0,
            "local_fallback": 0,
            "fallback_count": 0,
            "total_latency_ms": 0,
            "requests": 0,
        }

    def route(
        self,
        prompt: str,
        intent: str = "general",
        task_type: str = "general",
        privacy_sensitive: bool = False,
        allow_cloud: bool = True,
        system_prompt: str = "",
        actor_id: int | None = None,
    ) -> ModelResponse:
        """
        Select backend and execute. Returns a ModelResponse.
        Records routing metadata (not content).
        """
        self._routing_stats["requests"] += 1

        # 1. Emergency check is ALWAYS deterministic — never routed to LLM
        if task_type == "emergency" or intent == "emergency":
            self._routing_stats["deterministic"] += 1
            response = self.fallback.complete(prompt, "emergency")
            response.routing_reason = RoutingReason.DETERMINISTIC_SAFETY
            self._routing_stats["total_latency_ms"] += response.latency_ms
            self._log_execution(response, actor_id, task_type, intent)
            return response

        # 2. Local SLM — preferred for classification / simple tasks
        attempted_provider = False
        if self.slm.is_configured():
            attempted_provider = True
            response = self.slm.complete(prompt, system_prompt)
            if response.success:
                self._routing_stats["local_slm"] += 1
                self._routing_stats["total_latency_ms"] += response.latency_ms
                self._log_execution(response, actor_id, task_type, intent)
                return response
            # SLM failed → try next
            self._routing_stats["fallback_count"] += 1

        # 3. Cloud LLM — only when allowed and not privacy-sensitive
        if self.cloud.is_configured() and allow_cloud and not privacy_sensitive:
            attempted_provider = True
            response = self.cloud.complete(prompt, system_prompt)
            if response.success:
                self._routing_stats["cloud_llm"] += 1
                self._routing_stats["total_latency_ms"] += response.latency_ms
                self._log_execution(response, actor_id, task_type, intent)
                return response
            self._routing_stats["fallback_count"] += 1

        # 4. Always-available local fallback
        self._routing_stats["local_fallback"] += 1
        response = self.fallback.complete(prompt, intent)
        response.fallback_used = attempted_provider
        self._routing_stats["total_latency_ms"] += response.latency_ms
        self._log_execution(response, actor_id, task_type, intent)
        return response

    def _log_execution(self, response: ModelResponse, actor_id: int | None, task_type: str, intent: str):
        """Persist routing metadata only; prompts and hidden reasoning are never stored."""
        try:
            from flask import has_app_context
            if not has_app_context():
                return
            from .db import get_db, now_iso
            get_db().execute(
                """
                INSERT INTO model_execution_logs
                (actor_id, task_type, intent, provider, model, routing_reason, latency_ms,
                 success, fallback_used, error_category, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(actor_id) if actor_id else None,
                    str(task_type or "general")[:100],
                    str(intent or "general")[:100],
                    response.provider[:100],
                    response.model[:120],
                    response.routing_reason[:100],
                    max(0, int(response.latency_ms or 0)),
                    1 if response.success else 0,
                    1 if response.fallback_used else 0,
                    response.error_category,
                    now_iso(),
                ),
            )
            get_db().commit()
        except Exception:
            pass

    def status(self) -> dict:
        slm_status = self.slm.status()
        cloud_status = self.cloud.status()
        stats = dict(self._routing_stats)
        avg_latency = round(stats["total_latency_ms"] / max(stats["requests"], 1), 1)
        return {
            "local_slm": slm_status,
            "cloud_llm": cloud_status,
            "deterministic_safety": {"status": "working", "message": "Always available — rule-based, no LLM."},
            "local_fallback": {"status": "working", "message": "Always available."},
            "routing_mode": _routing_mode(slm_status, cloud_status),
            "stats": {
                "requests": stats["requests"],
                "deterministic": stats["deterministic"],
                "local_slm": stats["local_slm"],
                "cloud_llm": stats["cloud_llm"],
                "local_fallback": stats["local_fallback"],
                "fallback_count": stats["fallback_count"],
                "avg_latency_ms": avg_latency,
            },
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
_router_instance: ModelRouter | None = None


def get_model_router() -> ModelRouter:
    global _router_instance
    if _router_instance is None:
        _router_instance = ModelRouter()
    return _router_instance


# ── Helpers ───────────────────────────────────────────────────────────────────
def _env_bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _elapsed(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _classify_connection_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "refused" in msg or "connection" in msg:
        return "provider_unavailable"
    return "unknown"


def _routing_mode(slm_status: dict, cloud_status: dict) -> str:
    if slm_status.get("status") == "configured" and cloud_status.get("status") == "configured":
        return "slm_primary_cloud_fallback"
    if slm_status.get("status") == "configured":
        return "slm_primary_local_fallback"
    if cloud_status.get("status") == "configured":
        return "cloud_primary_local_fallback"
    return "deterministic_local_fallback"


def _deterministic_response(intent: str, prompt: str = "") -> str:
    responses = {
        "emergency": (
            "This appears to be an emergency. Call emergency services immediately (108 or 112). "
            "Do not wait for an AI response in a life-threatening situation."
        ),
        "symptoms": (
            "I can guide you, but I cannot confirm a diagnosis. Describe your symptoms in detail, "
            "and consider booking a consultation if they persist or worsen."
        ),
        "appointment": (
            "You can book appointments through ZENDOC. "
            "Use the Appointments section to schedule with a verified provider."
        ),
        "pharmacy": (
            "ZENDOC Pharmacy lets you search medicines and request delivery. "
            "Always follow your doctor's prescription."
        ),
        "fitness": (
            "ZENDOC Fitness Coach can create a personalized plan. "
            "Start with your fitness profile to get recommendations."
        ),
    }
    return responses.get(intent) or (
        "I can guide you to the right ZENDOC service and suggest safe next steps. "
        "Tell me what you need help with."
    )
