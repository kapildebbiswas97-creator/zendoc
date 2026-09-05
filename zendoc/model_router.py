"""Privacy-aware deterministic/local/cloud model routing for ZENDOC Milestone 8.1."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .local_ai_provider import (
    LocalAISettings,
    LocalInferenceRequest,
    LocalInferenceResult,
    STRUCTURED_OUTPUT_SCHEMA,
    create_local_ai_provider,
    validate_structured_model_content,
)


class RiskClass:
    READ_ONLY = "read_only"
    LOW_RISK = "low_risk"
    CONSENT_REQUIRED = "consent_required"
    DOCTOR_APPROVAL = "doctor_approval"
    OWNER_APPROVAL = "owner_approval"
    CRITICAL_BLOCKED = "critical_blocked"


class PrivacyClass:
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    PERSONAL = "PERSONAL"
    HEALTH_SENSITIVE = "HEALTH_SENSITIVE"
    HIGH_RISK = "HIGH_RISK"

    ALL = {PUBLIC, INTERNAL, PERSONAL, HEALTH_SENSITIVE, HIGH_RISK}


class RoutingReason:
    DETERMINISTIC_SAFETY = "deterministic_safety"
    DETERMINISTIC_POLICY = "deterministic_policy"
    LOCAL_SLM = "local_slm"
    CLOUD_LLM = "cloud_llm"
    LOCAL_FALLBACK = "local_fallback"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    CLOUD_POLICY_BLOCKED = "cloud_policy_blocked"


SAFE_LOCAL_TASKS = {
    "core_agent_guidance",
    "general",
    "general_assistant",
    "general_platform_question",
    "intent_classification",
    "navigation_help",
    "non_critical_extraction",
    "owner_operational_summary",
    "planning_assistance",
    "provider_discovery_query",
    "rewriting",
    "summarization",
}
DETERMINISTIC_ONLY_TASKS = {
    "admin_promotion",
    "ambulance_dispatch",
    "arbitrary_code",
    "arbitrary_filesystem",
    "arbitrary_sql",
    "diagnosis",
    "emergency",
    "medication_change",
    "payment_approval",
    "permission_change",
    "prescribing",
}
CLOUD_ALWAYS_BLOCKED = {PrivacyClass.HEALTH_SENSITIVE, PrivacyClass.HIGH_RISK}
HARMLESS_LOCAL_TEST_PROMPT = "In one sentence, explain what the ZENDOC dashboard helps a user navigate."


@dataclass
class ModelResponse:
    text: str
    provider: str
    model: str
    latency_ms: int
    success: bool
    fallback_used: bool = False
    routing_reason: str = RoutingReason.LOCAL_FALLBACK
    error_category: str | None = None
    metadata: dict = field(default_factory=dict)
    task_type: str = "general"
    output: dict = field(default_factory=dict)
    privacy_class: str = PrivacyClass.INTERNAL
    fallback_reason: str | None = None
    structured_output: bool = True

    def __post_init__(self):
        if not self.output and self.text:
            self.output = {"text": self.text, "data": {}}

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "provider": self.provider,
            "model": self.model,
            "task_type": self.task_type,
            "output": dict(self.output),
            "text": self.text,
            "latency_ms": max(0, int(self.latency_ms or 0)),
            "fallback_used": bool(self.fallback_used),
            "routing_reason": self.routing_reason,
            "error_category": self.error_category,
            "privacy_class": self.privacy_class,
            "fallback_reason": self.fallback_reason,
            "structured_output": bool(self.structured_output),
            "metadata": dict(self.metadata),
        }


class SLMProvider:
    """Compatibility facade around provider-neutral local AI adapters."""

    name = "local_slm"

    def __init__(self, settings: LocalAISettings | None = None):
        self.settings = settings or LocalAISettings.from_runtime()
        self.adapter = create_local_ai_provider(self.settings)
        self.enabled = self.settings.enabled
        self.provider = self.settings.provider
        self.base_url = self.settings.base_url
        self.model = self.settings.model
        self.timeout = self.settings.timeout

    def is_configured(self) -> bool:
        return self.adapter.is_configured()

    def health(self) -> dict:
        return self.adapter.health_check().to_dict()

    def status(self, check_health: bool = False) -> dict:
        canonical = self.health() if check_health else self._configuration_status()
        return _legacy_slm_status(canonical)

    def _configuration_status(self) -> dict:
        configured = self.adapter.configuration_health()
        if configured:
            return configured.to_dict()
        return {
            "status": "configured",
            "provider": self.adapter.provider_name,
            "server_status": "not_checked",
            "model_status": "configured_not_checked",
            "model": self.model,
            "latency_ms": None,
            "message": "Local AI configured — use the owner runtime health check to verify readiness.",
            "error_category": None,
            "last_successful_inference": self.adapter.last_successful_inference,
            "capabilities": [],
        }

    def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        *,
        task_type: str = "general",
        privacy_class: str = PrivacyClass.INTERNAL,
        max_output_tokens: int = 512,
    ) -> ModelResponse:
        result = self.adapter.infer(
            LocalInferenceRequest(prompt, task_type, privacy_class, system_prompt, max_output_tokens)
        )
        return _model_response_from_local(result)


class CloudLLMProvider:
    """OpenAI-compatible cloud adapter. Environment configuration is never user-controlled."""

    name = "cloud_llm"

    def __init__(self):
        self.provider = _runtime_value("AI_PROVIDER", "ZENDOC_AI_PROVIDER", "").lower()
        self.api_key = _runtime_value("AI_API_KEY", "ZENDOC_AI_API_KEY", "")
        default_url = "https://api.openai.com" if self.provider == "openai" else ""
        self.base_url = _runtime_value("AI_BASE_URL", "ZENDOC_AI_BASE_URL", default_url).rstrip("/")
        self.model = _runtime_value("AI_MODEL", "ZENDOC_AI_MODEL", "")
        self.timeout = _bounded_int(_runtime_value("AI_TIMEOUT", "ZENDOC_AI_TIMEOUT", "20"), 1, 120, 20)

    def fingerprint(self) -> tuple:
        return (self.provider, bool(self.api_key), self.base_url, self.model, self.timeout)

    def is_configured(self) -> bool:
        return bool(
            self.provider in {"openai", "openai_compatible"}
            and self.api_key and self.model and _safe_cloud_base_url(self.base_url)
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
            return {
                "status": "integration_required",
                "provider": self.provider or None,
                "message": f"Cloud LLM integration requires: {', '.join(missing)}.",
            }
        if self.provider not in {"openai", "openai_compatible"}:
            return {"status": "integration_required", "provider": self.provider, "message": "Cloud provider adapter is not implemented."}
        if not _safe_cloud_base_url(self.base_url):
            return {"status": "configuration_error", "provider": self.provider, "message": "Cloud provider URL is invalid."}
        return {
            "status": "configured",
            "provider": self.provider,
            "model": self.model,
            "message": "Cloud LLM is configured; use remains subject to per-request privacy policy.",
        }

    def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        *,
        task_type: str = "general",
        privacy_class: str = PrivacyClass.PUBLIC,
    ) -> ModelResponse:
        if not self.is_configured():
            return ModelResponse(
                "External AI provider is not configured.", "cloud_llm", "not_configured", 0, False, True,
                RoutingReason.PROVIDER_UNAVAILABLE, "not_configured", task_type=task_type,
                privacy_class=privacy_class, fallback_reason="cloud_not_configured",
            )
        started = time.perf_counter()
        request = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps({
                "model": self.model,
                "messages": [
                    {"role": "system", "content": _cloud_system_prompt(system_prompt)},
                    {"role": "user", "content": str(prompt or "").strip()[:4_000]},
                ],
                "temperature": 0,
                "response_format": {"type": "json_schema", "json_schema": {"name": "zendoc_output", "schema": STRUCTURED_OUTPUT_SCHEMA}},
            }, separators=(",", ":")).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read(1_048_577)
            if len(raw) > 1_048_576:
                raise ValueError("Provider response is too large.")
            data = json.loads(raw.decode("utf-8"))
            choices = data.get("choices") if isinstance(data, dict) else None
            message = choices[0].get("message") if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
            if not isinstance(message, dict) or message.get("tool_calls"):
                raise ValueError("Provider returned an unsafe response envelope.")
            output = validate_structured_model_content(message.get("content"))
            return ModelResponse(
                output["text"], f"cloud_llm_{self.provider}", self.model, _elapsed(started), True,
                routing_reason=RoutingReason.CLOUD_LLM, task_type=task_type, output=output,
                privacy_class=privacy_class, metadata={"structured_output": True},
            )
        except Exception as exc:
            category = _classify_cloud_error(exc)
            return ModelResponse(
                "Cloud LLM is unavailable.", f"cloud_llm_{self.provider}", self.model, _elapsed(started), False, True,
                RoutingReason.PROVIDER_UNAVAILABLE, category, task_type=task_type,
                privacy_class=privacy_class, fallback_reason=category,
            )


class LocalFallbackProvider:
    name = "local_fallback"

    def complete(
        self,
        prompt: str,
        intent: str = "general",
        *,
        task_type: str = "general",
        privacy_class: str = PrivacyClass.INTERNAL,
    ) -> ModelResponse:
        started = time.perf_counter()
        text = _deterministic_response(intent, prompt, task_type)
        return ModelResponse(
            text, "local_fallback", "zendoc_deterministic_v2", _elapsed(started), True,
            routing_reason=RoutingReason.LOCAL_FALLBACK, task_type=task_type,
            privacy_class=privacy_class,
        )


class ModelRouter:
    """Deterministic-first router; model output is advisory and never executable."""

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

    def configuration_fingerprint(self) -> tuple:
        return (self.slm.settings.fingerprint(), self.cloud.fingerprint())

    def route(
        self,
        prompt: str,
        intent: str = "general",
        task_type: str = "general",
        privacy_sensitive: bool = False,
        allow_cloud: bool = False,
        system_prompt: str = "",
        actor_id: int | None = None,
        *,
        privacy_class: str | None = None,
        cloud_consent: bool = False,
        complexity: str = "low",
        latency_preference: str = "normal",
        risk_class: str = RiskClass.READ_ONLY,
        structured_output_required: bool = True,
    ) -> ModelResponse:
        self._routing_stats["requests"] += 1
        task_type = str(task_type or "general").strip().lower()[:100]
        intent = str(intent or "general").strip().lower()[:100]
        privacy = normalize_privacy_class(privacy_class)
        if privacy_sensitive and privacy != PrivacyClass.HIGH_RISK:
            privacy = PrivacyClass.HEALTH_SENSITIVE

        if _requires_deterministic(task_type, intent, privacy, risk_class, latency_preference):
            self._routing_stats["deterministic"] += 1
            response = self.fallback.complete(prompt, intent, task_type=task_type, privacy_class=privacy)
            response.routing_reason = (
                RoutingReason.DETERMINISTIC_SAFETY
                if task_type == "emergency" or intent == "emergency"
                else RoutingReason.DETERMINISTIC_POLICY
            )
            response.fallback_reason = "deterministic_safety_or_policy"
            self._finish(response, actor_id, task_type, intent, privacy, structured_output_required)
            return response

        attempted = []
        reasons = []
        local_allowed = _local_task_allowed(task_type, complexity, risk_class, latency_preference)
        if local_allowed and self.slm.is_configured():
            attempted.append("local_ai")
            response = self.slm.complete(
                prompt, system_prompt, task_type=task_type, privacy_class=privacy
            )
            if response.success:
                self._routing_stats["local_slm"] += 1
                self._finish(response, actor_id, task_type, intent, privacy, structured_output_required)
                return response
            reasons.append(response.error_category or "local_provider_error")
            response.fallback_reason = reasons[-1]
            self._routing_stats["fallback_count"] += 1
            self._log_execution(response, actor_id, task_type, intent, privacy, structured_output_required)
        elif not local_allowed:
            reasons.append("local_policy_not_applicable")
        else:
            reasons.append("local_not_configured")

        cloud_privacy_allowed = cloud_policy_allows(privacy, allow_cloud, cloud_consent)
        cloud_risk_allowed = risk_class in {RiskClass.READ_ONLY, RiskClass.LOW_RISK}
        cloud_allowed = cloud_privacy_allowed and cloud_risk_allowed
        if cloud_allowed and self.cloud.is_configured():
            attempted.append("cloud_ai")
            response = self.cloud.complete(
                prompt, system_prompt, task_type=task_type, privacy_class=privacy
            )
            if response.success:
                self._routing_stats["cloud_llm"] += 1
                response.fallback_used = bool(attempted[:-1])
                response.fallback_reason = ",".join(reasons) or None
                self._finish(response, actor_id, task_type, intent, privacy, structured_output_required)
                return response
            reasons.append(response.error_category or "cloud_provider_error")
            response.fallback_reason = reasons[-1]
            self._routing_stats["fallback_count"] += 1
            self._log_execution(response, actor_id, task_type, intent, privacy, structured_output_required)
        elif allow_cloud and not cloud_allowed:
            reasons.append(
                "cloud_policy_blocked" if not cloud_privacy_allowed else "cloud_approval_risk_blocked"
            )
        elif not allow_cloud:
            reasons.append("cloud_not_approved")
        else:
            reasons.append("cloud_not_configured")

        self._routing_stats["local_fallback"] += 1
        response = self.fallback.complete(prompt, intent, task_type=task_type, privacy_class=privacy)
        response.fallback_used = bool(attempted)
        response.fallback_reason = ",".join(dict.fromkeys(reasons)) or None
        self._finish(response, actor_id, task_type, intent, privacy, structured_output_required)
        return response

    def test_local_ai(self, actor_id: int | None = None) -> ModelResponse:
        response = self.slm.complete(
            HARMLESS_LOCAL_TEST_PROMPT,
            "Answer only the harmless platform-navigation question.",
            task_type="general_platform_question",
            privacy_class=PrivacyClass.PUBLIC,
        )
        self._log_execution(
            response,
            actor_id,
            "local_ai_health_test",
            "platform_help",
            PrivacyClass.PUBLIC,
            True,
        )
        return response

    def _finish(
        self,
        response: ModelResponse,
        actor_id: int | None,
        task_type: str,
        intent: str,
        privacy_class: str,
        structured_output: bool,
    ):
        self._routing_stats["total_latency_ms"] += max(0, int(response.latency_ms or 0))
        self._log_execution(response, actor_id, task_type, intent, privacy_class, structured_output)

    def _log_execution(
        self,
        response: ModelResponse,
        actor_id: int | None,
        task_type: str,
        intent: str,
        privacy_class: str,
        structured_output: bool,
    ):
        """Persist metadata only. Prompts, responses, keys, and hidden reasoning are excluded."""
        try:
            from flask import has_app_context
            if not has_app_context():
                return
            from .db import get_db, now_iso
            get_db().execute(
                """
                INSERT INTO model_execution_logs
                (actor_id,task_type,intent,provider,model,routing_reason,latency_ms,success,
                 fallback_used,error_category,privacy_class,fallback_reason,structured_output,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    int(actor_id) if actor_id else None,
                    str(task_type or "general")[:100],
                    str(intent or "general")[:100],
                    str(response.provider or "unknown")[:100],
                    str(response.model or "unknown")[:120],
                    str(response.routing_reason or "unknown")[:100],
                    max(0, int(response.latency_ms or 0)),
                    1 if response.success else 0,
                    1 if response.fallback_used else 0,
                    str(response.error_category)[:100] if response.error_category else None,
                    normalize_privacy_class(privacy_class),
                    str(response.fallback_reason)[:200] if response.fallback_reason else None,
                    1 if structured_output else 0,
                    now_iso(),
                ),
            )
            get_db().commit()
        except Exception:
            # Observability failure must never crash inference or the application.
            pass

    def status(self, check_health: bool = False) -> dict:
        local_canonical = self.slm.health() if check_health else self.slm._configuration_status()
        local_compat = _legacy_slm_status(local_canonical)
        cloud_status = self.cloud.status()
        stats = dict(self._routing_stats)
        persistent = _persistent_runtime_metadata()
        requests = max(stats["requests"], persistent["requests"])
        total_latency = (
            persistent["total_latency_ms"]
            if persistent["requests"]
            else stats["total_latency_ms"]
        )
        average = round(total_latency / max(requests, 1), 1)
        if persistent["last_local_success"]:
            local_canonical["last_successful_inference"] = persistent["last_local_success"]
            local_compat["last_successful_inference"] = persistent["last_local_success"]
        return {
            "local_ai": local_canonical,
            "local_slm": local_compat,
            "cloud_llm": cloud_status,
            "deterministic_safety": {"status": "working", "message": "Always available — rule-based, no LLM."},
            "local_fallback": {"status": "working", "message": "Always available."},
            "routing_mode": _routing_mode(local_canonical, cloud_status),
            "routing_policy": {
                "priority": ["deterministic_safety", "deterministic_tasks", "local_ai", "approved_cloud", "local_fallback"],
                "cloud_blocked_privacy_classes": sorted(CLOUD_ALWAYS_BLOCKED),
                "personal_cloud_requires_consent": True,
                "model_output_can_execute_tools": False,
            },
            "stats": {
                "requests": requests,
                "deterministic": max(stats["deterministic"], persistent["deterministic"]),
                "local_slm": max(stats["local_slm"], persistent["local_slm"]),
                "cloud_llm": max(stats["cloud_llm"], persistent["cloud_llm"]),
                "local_fallback": max(stats["local_fallback"], persistent["local_fallback"]),
                "fallback_count": max(stats["fallback_count"], persistent["fallback_count"]),
                "avg_latency_ms": average,
            },
            "recent_inferences": persistent["recent_inferences"],
            "provider_errors": persistent["provider_errors"],
            "fallback_reasons": persistent["fallback_reasons"],
        }


_router_instance: ModelRouter | None = None


def get_model_router() -> ModelRouter:
    global _router_instance
    fingerprint = _current_configuration_fingerprint()
    if _router_instance is None or _router_instance.configuration_fingerprint() != fingerprint:
        _router_instance = ModelRouter()
    return _router_instance


def reset_model_router():
    global _router_instance
    _router_instance = None


def normalize_privacy_class(value: str | None) -> str:
    normalized = str(value or PrivacyClass.INTERNAL).strip().upper()
    return normalized if normalized in PrivacyClass.ALL else PrivacyClass.INTERNAL


def cloud_policy_allows(privacy_class: str, allow_cloud: bool, cloud_consent: bool = False) -> bool:
    privacy = normalize_privacy_class(privacy_class)
    if not allow_cloud or privacy in CLOUD_ALWAYS_BLOCKED:
        return False
    if privacy == PrivacyClass.PERSONAL:
        return bool(cloud_consent)
    return privacy in {PrivacyClass.PUBLIC, PrivacyClass.INTERNAL}


def _requires_deterministic(task_type, intent, privacy, risk_class, latency_preference) -> bool:
    return bool(
        task_type in DETERMINISTIC_ONLY_TASKS
        or intent == "emergency"
        or privacy == PrivacyClass.HIGH_RISK
        or risk_class == RiskClass.CRITICAL_BLOCKED
        or latency_preference == "deterministic"
    )


def _local_task_allowed(task_type, complexity, risk_class, latency_preference) -> bool:
    return bool(
        task_type in SAFE_LOCAL_TASKS
        and str(complexity or "low").lower() in {"low", "medium"}
        and risk_class in {RiskClass.READ_ONLY, RiskClass.LOW_RISK, RiskClass.OWNER_APPROVAL}
        and latency_preference != "deterministic"
    )


def _model_response_from_local(result: LocalInferenceResult) -> ModelResponse:
    text = str(result.output.get("text") or "") if result.output else ""
    if not result.success:
        text = "Local AI inference was unavailable or rejected."
    return ModelResponse(
        text=text,
        provider=result.provider,
        model=result.model,
        latency_ms=result.latency_ms,
        success=result.success,
        fallback_used=result.fallback_used,
        routing_reason=RoutingReason.LOCAL_SLM if result.success else RoutingReason.PROVIDER_UNAVAILABLE,
        error_category=result.error_category,
        metadata=result.metadata,
        task_type=result.task_type,
        output=result.output,
        privacy_class=result.privacy_class,
        fallback_reason=result.error_category if not result.success else None,
        structured_output=True,
    )


def _legacy_slm_status(canonical: dict) -> dict:
    result = dict(canonical)
    state = canonical.get("status")
    result["runtime_state"] = state
    if state == "disabled":
        result["status"] = "integration_required"
        result["message"] = "Local SLM integration ready — model not configured."
    elif state == "ready":
        result["status"] = "configured"
    return result


def _persistent_runtime_metadata() -> dict:
    empty = {
        "requests": 0,
        "deterministic": 0,
        "local_slm": 0,
        "cloud_llm": 0,
        "local_fallback": 0,
        "fallback_count": 0,
        "total_latency_ms": 0,
        "last_local_success": None,
        "recent_inferences": [],
        "provider_errors": [],
        "fallback_reasons": [],
    }
    try:
        from flask import has_app_context
        if not has_app_context():
            return empty
        from .db import get_db
        db = get_db()
        rows = db.execute(
            """
            SELECT id,task_type,provider,model,routing_reason,latency_ms,success,fallback_used,
                   error_category,privacy_class,fallback_reason,created_at
            FROM model_execution_logs ORDER BY id DESC LIMIT 25
            """
        ).fetchall()
        all_stats = db.execute(
            """
            SELECT COUNT(*) requests,
                   COALESCE(SUM(latency_ms),0) total_latency_ms,
                   COALESCE(SUM(CASE WHEN routing_reason IN ('deterministic_safety','deterministic_policy') THEN 1 ELSE 0 END),0) deterministic,
                   COALESCE(SUM(CASE WHEN provider LIKE 'local_%' AND provider!='local_fallback' AND success=1 THEN 1 ELSE 0 END),0) local_slm,
                   COALESCE(SUM(CASE WHEN provider LIKE 'cloud_llm_%' AND success=1 THEN 1 ELSE 0 END),0) cloud_llm,
                   COALESCE(SUM(CASE WHEN provider='local_fallback' THEN 1 ELSE 0 END),0) local_fallback,
                   COALESCE(SUM(CASE WHEN success=1 AND fallback_used=1 THEN 1 ELSE 0 END),0) fallback_count
            FROM model_execution_logs
            """
        ).fetchone()
        last_local = db.execute(
            "SELECT created_at FROM model_execution_logs WHERE provider LIKE 'local_%' AND provider!='local_fallback' AND success=1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        reasons = db.execute(
            "SELECT fallback_reason,COUNT(*) count FROM model_execution_logs WHERE fallback_reason IS NOT NULL GROUP BY fallback_reason ORDER BY count DESC,fallback_reason LIMIT 10"
        ).fetchall()
        safe_rows = [dict(row) for row in rows]
        return {
            "requests": all_stats["requests"],
            "deterministic": all_stats["deterministic"],
            "local_slm": all_stats["local_slm"],
            "cloud_llm": all_stats["cloud_llm"],
            "local_fallback": all_stats["local_fallback"],
            "fallback_count": all_stats["fallback_count"],
            "total_latency_ms": all_stats["total_latency_ms"],
            "last_local_success": last_local["created_at"] if last_local else None,
            "recent_inferences": safe_rows,
            "provider_errors": [row for row in safe_rows if not row["success"]],
            "fallback_reasons": [dict(row) for row in reasons],
        }
    except Exception:
        return empty


def _current_configuration_fingerprint() -> tuple:
    settings = LocalAISettings.from_runtime()
    cloud = CloudLLMProvider()
    return (settings.fingerprint(), cloud.fingerprint())


def _routing_mode(local_status: dict, cloud_status: dict) -> str:
    local_ready = local_status.get("status") == "ready"
    cloud_configured = cloud_status.get("status") == "configured"
    if local_ready and cloud_configured:
        return "local_primary_policy_approved_cloud_fallback"
    if local_ready:
        return "local_primary_deterministic_fallback"
    if cloud_configured:
        return "policy_approved_cloud_or_deterministic_fallback"
    return "deterministic_local_fallback"


def _deterministic_response(intent: str, prompt: str = "", task_type: str = "general") -> str:
    if task_type in DETERMINISTIC_ONLY_TASKS - {"emergency"}:
        return "This action cannot be performed by a language model. Use the authorized ZENDOC workflow and required human approval."
    responses = {
        "emergency": (
            "This appears to be an emergency. Call emergency services immediately (108 or 112). "
            "Do not wait for an AI response in a life-threatening situation."
        ),
        "symptoms": (
            "I can guide you, but I cannot confirm a diagnosis. Describe your symptoms in detail, "
            "and consider booking a consultation if they persist or worsen."
        ),
        "appointment": "Use the ZENDOC Appointments section to schedule with a verified provider.",
        "pharmacy": "Use ZENDOC Pharmacy for medicine information and requests, and follow your doctor's prescription.",
        "fitness": "Start with your ZENDOC fitness profile to receive bounded wellness guidance.",
    }
    return responses.get(intent) or "I can guide you to the appropriate ZENDOC service and safe next step."


def _runtime_value(config_key: str, env_key: str, default: str) -> str:
    try:
        from flask import current_app, has_app_context
        if has_app_context() and config_key in current_app.config:
            value = current_app.config.get(config_key)
            return str(value if value is not None else default).strip()
    except (ImportError, RuntimeError):
        pass
    return str(os.environ.get(env_key, default) or default).strip()


def _safe_cloud_base_url(value: str) -> bool:
    parsed = urlsplit(str(value or "").strip())
    return bool(
        parsed.scheme in {"http", "https"}
        and parsed.hostname
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
        and parsed.path in {"", "/"}
    )


def _cloud_system_prompt(extra: str) -> str:
    base = (
        "Return JSON matching the supplied schema. Provide low-risk advisory text only. "
        "Never emit tool calls, commands, diagnoses, prescriptions, permission changes, or claims of execution."
    )
    extra = str(extra or "").strip()[:1_000]
    return f"{base}\nAdditional task context: {extra}" if extra else base


def _classify_cloud_error(exc: Exception) -> str:
    message = str(exc).lower()
    if isinstance(exc, TimeoutError) or "timeout" in message or "timed out" in message:
        return "timeout"
    if isinstance(exc, urllib.error.URLError):
        return "provider_unavailable"
    if isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError, ValueError)):
        return "malformed_response"
    return "provider_error"


def _bounded_int(value, minimum: int, maximum: int, default: int) -> int:
    try:
        return max(minimum, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


def _elapsed(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))
