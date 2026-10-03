"""Owner-scoped local controller for the ZENDOC Agent OS.

The controller is the laptop/local control-plane entry point. It may consult the
configured local model fleet for advisory language/reasoning, but deterministic
policy remains authoritative. Safe operational execution is deliberately
limited to existing bounded workflows: source research, approved public-data
refresh, and evidence-gated incident intake.

It has no shell, SQL, filesystem, secret, payment, prescribing, emergency
dispatch, permission-expansion, or direct production-deployment authority.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from .agent_feature_coverage import feature_agent_coverage_snapshot
from .ai_workforce import WORKFORCE, enqueue_incident_case, workforce_manifest
from .global_source_research import enqueue_source_research_batch, global_source_gap_report
from .interoperability_gateway import interoperability_readiness_snapshot
from .local_ai_provider import (
    LocalAISettings,
    LocalInferenceRequest,
    create_local_ai_provider,
    validate_local_provider_url,
)
from .model_router import ModelRouter, PrivacyClass, RiskClass
from .personal_agents import personal_agent_manifest
from .public_data_refresh import public_refresh_snapshot, refresh_official_public_data
from .security import assert_owner


MAX_AUXILIARY_MODELS = 8
MAX_AUXILIARY_ATTEMPTS = 2
MAX_AUXILIARY_TIMEOUT_SECONDS = 30
MAX_AUXILIARY_OUTPUT_TOKENS = 512
ALLOWED_MODEL_ROLES = {
    "language",
    "operations_analysis",
    "research_synthesis",
    "document_extraction",
    "translation",
    "classification",
    "summarization",
}
FORBIDDEN_COMMAND_MARKERS = (
    "execute payment",
    "send payment",
    "upi pin",
    "cvv",
    "prescribe medicine",
    "write prescription",
    "change medication dose",
    "dispatch emergency",
    "dispatch ambulance",
    "show secret",
    "reveal secret",
    "read api key",
    "run shell",
    "execute shell",
    "run sql",
    "execute sql",
    "delete production",
    "disable safety",
    "disable audit",
    "expand permission",
    "deploy directly to production",
    "self modify production",
)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _clean_command(command: str) -> str:
    return " ".join(str(command or "").strip().split())[:2000]


def _fleet_error(category: str, message: str, *, profile_id: str = "fleet-config") -> dict:
    return {
        "id": profile_id,
        "status": "configuration_error",
        "error_category": category,
        "message": message,
        "tool_authority": False,
        "secret_access": False,
    }


def _strict_bool(value, *, field: str, default: bool = False) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a JSON boolean.")
    return value


def _strict_bounded_int(value, *, field: str, minimum: int, maximum: int, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer.")
    if value < minimum or value > maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}.")
    return value


def _validated_roles(raw) -> list[str]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("roles must be a non-empty JSON list.")
    roles = []
    for item in raw:
        if not isinstance(item, str):
            raise ValueError("roles entries must be strings.")
        role = item.strip().lower()
        if role not in ALLOWED_MODEL_ROLES:
            raise ValueError(f"Unsupported auxiliary model role: {role or '<empty>'}.")
        if role not in roles:
            roles.append(role)
    return roles


def _auxiliary_model_profiles(*, check_health: bool = False) -> list[dict]:
    raw = str(os.environ.get("ZENDOC_LOCAL_MODEL_FLEET_JSON") or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return [_fleet_error("invalid_json", "ZENDOC_LOCAL_MODEL_FLEET_JSON must be valid JSON.")]
    if not isinstance(data, list):
        return [_fleet_error("invalid_shape", "ZENDOC_LOCAL_MODEL_FLEET_JSON must be a JSON list.")]
    if len(data) > MAX_AUXILIARY_MODELS:
        return [_fleet_error(
            "fleet_limit_exceeded",
            f"At most {MAX_AUXILIARY_MODELS} auxiliary local models may be configured.",
        )]

    allowed_keys = {
        "id",
        "provider",
        "model",
        "base_url",
        "roles",
        "timeout",
        "allow_private_network",
        "max_output_tokens",
        "priority",
        "enabled",
    }
    profiles = []
    seen = set()
    for index, item in enumerate(data):
        default_id = f"aux-{index + 1}"
        if not isinstance(item, dict):
            profiles.append(_fleet_error(
                "invalid_profile",
                "Each auxiliary model profile must be a JSON object.",
                profile_id=default_id,
            ))
            continue

        unknown = sorted(str(key) for key in item.keys() if key not in allowed_keys)
        if unknown:
            profiles.append(_fleet_error(
                "unknown_profile_fields",
                f"Unsupported auxiliary model fields: {', '.join(unknown)[:240]}.",
                profile_id=str(item.get("id") or default_id).strip()[:80] or default_id,
            ))
            continue

        profile_id = str(item.get("id") or default_id).strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", profile_id or "") or profile_id in seen:
            profiles.append(_fleet_error(
                "duplicate_or_invalid_id",
                "Auxiliary model id must be unique and use only letters, numbers, dot, underscore or hyphen.",
                profile_id=profile_id[:80] or default_id,
            ))
            continue
        seen.add(profile_id)

        try:
            enabled = _strict_bool(item.get("enabled"), field="enabled", default=True)
            allow_private = _strict_bool(
                item.get("allow_private_network"),
                field="allow_private_network",
                default=False,
            )
            roles = _validated_roles(item.get("roles"))
            timeout = _strict_bounded_int(
                item.get("timeout"),
                field="timeout",
                minimum=1,
                maximum=MAX_AUXILIARY_TIMEOUT_SECONDS,
                default=10,
            )
            max_output_tokens = _strict_bounded_int(
                item.get("max_output_tokens"),
                field="max_output_tokens",
                minimum=64,
                maximum=MAX_AUXILIARY_OUTPUT_TOKENS,
                default=384,
            )
            priority = _strict_bounded_int(
                item.get("priority"),
                field="priority",
                minimum=0,
                maximum=100,
                default=50,
            )
        except ValueError as exc:
            profiles.append(_fleet_error(
                "invalid_profile_settings",
                str(exc),
                profile_id=profile_id,
            ))
            continue

        provider = str(item.get("provider") or "ollama").strip().lower()
        model = str(item.get("model") or "").strip()
        base_url = str(item.get("base_url") or "http://127.0.0.1:11434").strip()
        profile = {
            "id": profile_id,
            "provider": provider,
            "model": model[:160] or None,
            "base_url": base_url[:512],
            "roles": roles,
            "priority": priority,
            "timeout": timeout,
            "max_output_tokens": max_output_tokens,
            "enabled": enabled,
            "status": "configured" if enabled else "disabled",
            "tool_authority": False,
            "secret_access": False,
        }
        if provider not in {"ollama", "openai_compatible"}:
            profile.update(status="configuration_error", error_category="invalid_provider")
            profiles.append(profile)
            continue
        if not model or len(model) > 160 or any(char in model for char in "\r\n\x00"):
            profile.update(status="configuration_error", error_category="invalid_model")
            profiles.append(profile)
            continue
        if len(base_url) > 512:
            profile.update(status="configuration_error", error_category="invalid_base_url")
            profiles.append(profile)
            continue
        try:
            validate_local_provider_url(base_url, allow_private)
        except ValueError:
            profile.update(status="configuration_error", error_category="unsafe_provider_url")
            profiles.append(profile)
            continue

        if check_health and enabled:
            settings = LocalAISettings(
                enabled=True,
                provider=provider,
                base_url=base_url,
                model=model,
                timeout=timeout,
                allow_private_network=allow_private,
            )
            try:
                health = create_local_ai_provider(settings).health_check().to_dict()
                profile["runtime"] = health
                profile["status"] = health.get("status") or profile["status"]
            except Exception:
                profile["runtime"] = {
                    "status": "unavailable",
                    "error_category": "provider_error",
                    "message": "Auxiliary local model health check failed closed.",
                }
                profile["status"] = "unavailable"
        profiles.append(profile)
    return profiles


def _model_role_for_intent(intent: str) -> str | None:
    return {
        "global_source_research": "research_synthesis",
        "official_public_data_refresh": "operations_analysis",
        "reliability_incident": "operations_analysis",
        "model_runtime": "operations_analysis",
        "interoperability": "research_synthesis",
        "release_control": "operations_analysis",
        "platform_coordination": "summarization",
    }.get(intent)


def _route_local_fleet_advisory(command: str, intent: str) -> dict:
    role = _model_role_for_intent(intent)
    profiles = _auxiliary_model_profiles(check_health=False)
    candidates = sorted(
        (
            profile for profile in profiles
            if role
            and profile.get("status") == "configured"
            and profile.get("enabled") is True
            and role in profile.get("roles", [])
        ),
        key=lambda profile: (int(profile.get("priority", 50)), str(profile.get("id") or "")),
    )
    attempts = []
    for profile in candidates[:MAX_AUXILIARY_ATTEMPTS]:
        settings = LocalAISettings(
            enabled=True,
            provider=profile["provider"],
            base_url=profile["base_url"],
            model=profile["model"],
            timeout=profile["timeout"],
            allow_private_network=bool(
                next(
                    (
                        item.get("allow_private_network", False)
                        for item in json.loads(str(os.environ.get("ZENDOC_LOCAL_MODEL_FLEET_JSON") or "[]"))
                        if isinstance(item, dict) and str(item.get("id") or "").strip() == profile["id"]
                    ),
                    False,
                )
            ),
        )
        try:
            result = create_local_ai_provider(settings).infer(
                LocalInferenceRequest(
                    prompt=command,
                    task_type="owner_operational_summary",
                    privacy_class=PrivacyClass.INTERNAL,
                    system_prompt=(
                        f"You are the role-scoped {role} auxiliary for ZENDOC. "
                        "Provide advisory analysis only. Never request tools, secrets, permission changes, "
                        "clinical authority, payment execution, emergency dispatch or production deployment."
                    ),
                    max_output_tokens=profile["max_output_tokens"],
                )
            )
            attempts.append({
                "profile_id": profile["id"],
                "role": role,
                "provider": result.provider,
                "model": result.model,
                "success": bool(result.success),
                "error_category": result.error_category,
                "latency_ms": max(0, int(result.latency_ms or 0)),
            })
            if result.success:
                return {
                    "success": True,
                    "provider": result.provider,
                    "model": result.model,
                    "routing_reason": "local_auxiliary_role",
                    "fallback_used": False,
                    "text": str(result.output.get("text") or ""),
                    "selected_profile_id": profile["id"],
                    "selected_role": role,
                    "attempts": attempts,
                }
        except Exception:
            attempts.append({
                "profile_id": profile["id"],
                "role": role,
                "provider": f"local_{profile['provider']}",
                "model": profile["model"],
                "success": False,
                "error_category": "provider_error",
                "latency_ms": 0,
            })

    primary = ModelRouter().route(
        command,
        intent="owner_platform_control",
        task_type="owner_operational_summary",
        allow_cloud=False,
        cloud_consent=False,
        privacy_class=PrivacyClass.INTERNAL,
        risk_class=RiskClass.READ_ONLY,
        structured_output_required=True,
    )
    return {
        "success": primary.success,
        "provider": primary.provider,
        "model": primary.model,
        "routing_reason": primary.routing_reason,
        "fallback_used": bool(attempts) or primary.fallback_used,
        "text": primary.text,
        "selected_profile_id": None,
        "selected_role": role,
        "attempts": attempts,
        "fleet_configuration_errors": [
            {
                "id": profile.get("id"),
                "error_category": profile.get("error_category"),
            }
            for profile in profiles
            if profile.get("status") == "configuration_error"
        ],
    }


def local_model_fleet_snapshot(*, check_health: bool = False) -> dict:
    router = ModelRouter()
    primary = router.slm.status(check_health=check_health)
    return {
        "version": "local-model-fleet-v1",
        "primary": {
            **primary,
            "controller_role": "primary_local_language_and_reasoning_model",
            "tool_authority": False,
            "secret_access": False,
        },
        "auxiliary_models": _auxiliary_model_profiles(check_health=check_health),
        "resource_limits": {
            "max_auxiliary_models": MAX_AUXILIARY_MODELS,
            "max_auxiliary_attempts_per_command": MAX_AUXILIARY_ATTEMPTS,
            "max_timeout_seconds_per_auxiliary": MAX_AUXILIARY_TIMEOUT_SECONDS,
            "max_output_tokens_per_auxiliary": MAX_AUXILIARY_OUTPUT_TOKENS,
        },
        "selection_rule": (
            "Deterministic safety, authorization and intent classification run first. "
            "A matching role-scoped auxiliary may provide advisory analysis within hard resource limits; "
            "the primary local model is the bounded fallback, followed by deterministic fallback. "
            "No model receives direct tool authority."
        ),
        "cloud_rule": (
            "Cloud inference is separate, explicit and privacy-gated. HEALTH_SENSITIVE and "
            "HIGH_RISK content is not routed to cloud by the Model Router."
        ),
    }


def local_controller_snapshot(actor: Any, *, check_health: bool = False) -> dict:
    assert_owner(actor)
    coverage = feature_agent_coverage_snapshot()
    source_gaps = global_source_gap_report()
    return {
        "version": "zendoc-local-controller-v1",
        "status": "working",
        "local_model_fleet": local_model_fleet_snapshot(check_health=check_health),
        "personal_agents": {
            "role_count": len(personal_agent_manifest()["roles"]),
            "roles": sorted(personal_agent_manifest()["roles"]),
        },
        "specialist_coverage": {
            "complete": coverage["complete"],
            "covered_count": coverage["covered_count"],
            "capability_count": coverage["capability_count"],
        },
        "ai_workforce": {
            "agent_count": len(WORKFORCE),
            "manifest_version": workforce_manifest()["version"],
            "production_approval_required": True,
        },
        "global_health_data": {
            "country_count": source_gaps["country_count"],
            "source_registered_country_count": source_gaps["source_registered_country_count"],
            "source_gap_count": source_gaps["source_gap_count"],
            "research_automation": "bounded_official_source_discovery",
            "private_data_collection": False,
        },
        "public_data_refresh": public_refresh_snapshot(),
        "interoperability": interoperability_readiness_snapshot(),
        "authority": {
            "read_only_analysis": True,
            "bounded_public_source_research": True,
            "bounded_official_public_data_refresh": True,
            "incident_intake": True,
            "direct_production_deploy": False,
            "arbitrary_code_execution": False,
            "shell_or_sql_execution": False,
            "secret_access": False,
            "permission_expansion": False,
            "payment_execution": False,
            "clinical_authority": False,
            "emergency_dispatch_authority": False,
        },
    }


def _classify_controller_intent(command: str) -> str:
    text = command.lower()
    if any(marker in text for marker in ("collect official data", "refresh public data", "refresh official data", "ingest public data")):
        return "official_public_data_refresh"
    if any(marker in text for marker in ("global source", "find official source", "research source", "country data gap", "global healthcare data")):
        return "global_source_research"
    if any(marker in text for marker in ("incident", "bug", "regression", "self heal", "self-heal", "root cause", "repair failure")):
        return "reliability_incident"
    if any(marker in text for marker in ("ollama", "local model", "model fleet", "slm", "llm", "model router", "model evaluation")):
        return "model_runtime"
    if any(marker in text for marker in ("fhir", "abha", "abdm", "epic", "oracle health", "healthlake", "azure health", "tefca", "ehds", "interoperability")):
        return "interoperability"
    if any(marker in text for marker in ("release", "deployment", "vercel", "oci", "health endpoint", "ready endpoint")):
        return "release_control"
    return "platform_coordination"


def _delegation_for_intent(intent: str) -> dict:
    return {
        "global_source_research": {
            "specialist": "OperationsAgent",
            "workforce": ["ResearchAgent", "DataAgent", "ManagerAgent"],
            "safe_execution": "enqueue bounded source-discovery batch",
        },
        "official_public_data_refresh": {
            "specialist": "OperationsAgent",
            "workforce": ["DataAgent", "IntegrationAgent"],
            "safe_execution": "refresh only reviewed non-personal allowlisted public connectors",
        },
        "reliability_incident": {
            "specialist": "OperationsAgent",
            "workforce": ["IncidentAgent", "EngineeringAgent", "RootCauseAgent", "RepairAgent", "SecurityAgent", "TestAgent", "QAAgent", "ReleaseAgent"],
            "safe_execution": "open evidence-gated incident case; production remains owner-gated",
        },
        "model_runtime": {
            "specialist": "ModelImprovementAgent",
            "workforce": ["InfrastructureAgent", "TestAgent", "ResearchAgent", "ManagerAgent"],
            "safe_execution": "read-only model status and advisory evaluation",
        },
        "interoperability": {
            "specialist": "InteroperabilityAgent",
            "workforce": ["IntegrationAgent", "SecurityAgent"],
            "safe_execution": "readiness/exchange planning only unless external authorization exists",
        },
        "release_control": {
            "specialist": "OperationsAgent",
            "workforce": ["InfrastructureAgent", "QAAgent", "ReleaseAgent"],
            "safe_execution": "assemble/inspect evidence only; no direct production promotion",
        },
        "platform_coordination": {
            "specialist": "OperationsAgent",
            "workforce": ["ManagerAgent", "ProductAgent", "IntegrationAgent"],
            "safe_execution": "read-only coordination/status",
        },
    }[intent]


def preview_local_controller_command(actor: Any, command: str, *, context: dict | None = None) -> dict:
    assert_owner(actor)
    clean = _clean_command(command)
    if not clean:
        raise ValueError("Controller command is required.")
    lower = clean.lower()
    forbidden = next((marker for marker in FORBIDDEN_COMMAND_MARKERS if marker in lower), None)
    if forbidden:
        return {
            "status": "blocked",
            "intent": "critical_blocked",
            "blocked_reason": forbidden,
            "model_called": False,
            "production_changes_executed": 0,
            "authority": {
                "payment_execution": False,
                "clinical_authority": False,
                "emergency_dispatch_authority": False,
                "secret_access": False,
                "arbitrary_code_execution": False,
                "production_self_modification": False,
            },
        }

    intent = _classify_controller_intent(clean)
    delegation = _delegation_for_intent(intent)
    advisory = _route_local_fleet_advisory(clean, intent)
    return {
        "status": "preview",
        "intent": intent,
        "delegation": delegation,
        "model_advisory": advisory,
        "context_keys": sorted(str(key) for key in (context or {}).keys())[:30],
        "production_changes_executed": 0,
        "truth": {
            "model_output_is_advisory": True,
            "tools_recheck_permissions": True,
            "global_source_research_requires_authoritative_evidence": True,
            "external_connectivity_not_inferred": True,
        },
    }


def execute_safe_local_controller_command(actor: Any, command: str, *, context: dict | None = None) -> dict:
    assert_owner(actor)
    context = context if isinstance(context, dict) else {}
    preview = preview_local_controller_command(actor, command, context=context)
    if preview["status"] == "blocked":
        return preview

    intent = preview["intent"]
    action = None
    if intent == "global_source_research":
        action = enqueue_source_research_batch(
            actor,
            max_countries=max(1, min(int(context.get("max_countries") or 12), 25)),
        )
    elif intent == "official_public_data_refresh":
        apply_requested = bool(context.get("apply"))
        if apply_requested and not _env_bool("ZENDOC_OPS_PUBLIC_DATA_AUTO_APPLY", False):
            raise PermissionError(
                "Applying official public-data refresh requires ZENDOC_OPS_PUBLIC_DATA_AUTO_APPLY=true. "
                "Preview refresh remains available."
            )
        action = refresh_official_public_data(
            actor,
            apply=apply_requested,
            page_limit=max(1, min(int(context.get("page_limit") or 200), 500)),
            max_sources=max(1, min(int(context.get("max_sources") or 1), 3)),
        )
    elif intent == "reliability_incident":
        severity = str(context.get("severity") or "medium").strip().lower()
        action = enqueue_incident_case(
            actor,
            _clean_command(command),
            severity=severity,
            source_type="local_controller",
        )
    elif intent == "model_runtime":
        action = local_model_fleet_snapshot(check_health=bool(context.get("check_health")))
    elif intent == "interoperability":
        action = interoperability_readiness_snapshot()
    elif intent == "release_control":
        action = {
            "status": "evidence_only",
            "message": (
                "The local controller may inspect/assemble release evidence but cannot promote "
                "or deploy production. Live health/ready proof must come from the authorized deployment."
            ),
            "production_promotion_executed": False,
        }
    else:
        action = local_controller_snapshot(actor, check_health=False)

    return {
        **preview,
        "status": "completed_safe_scope",
        "action_result": action,
        "production_changes_executed": 0,
        "direct_production_deploy": False,
    }
