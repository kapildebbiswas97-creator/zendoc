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
from typing import Any

from .agent_feature_coverage import feature_agent_coverage_snapshot
from .ai_workforce import WORKFORCE, enqueue_incident_case, workforce_manifest
from .global_source_research import enqueue_source_research_batch, global_source_gap_report
from .interoperability_gateway import interoperability_readiness_snapshot
from .local_ai_provider import LocalAISettings, create_local_ai_provider, validate_local_provider_url
from .model_router import ModelRouter, PrivacyClass, RiskClass
from .personal_agents import personal_agent_manifest
from .public_data_refresh import public_refresh_snapshot, refresh_official_public_data
from .security import assert_owner


MAX_AUXILIARY_MODELS = 8
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


def _safe_roles(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    roles = []
    for item in raw[:12]:
        role = str(item or "").strip().lower()
        if role in ALLOWED_MODEL_ROLES and role not in roles:
            roles.append(role)
    return roles


def _auxiliary_model_profiles(*, check_health: bool = False) -> list[dict]:
    raw = str(os.environ.get("ZENDOC_LOCAL_MODEL_FLEET_JSON") or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return [{
            "id": "fleet-config",
            "status": "configuration_error",
            "error_category": "invalid_json",
            "message": "ZENDOC_LOCAL_MODEL_FLEET_JSON must be valid JSON.",
        }]
    if not isinstance(data, list):
        return [{
            "id": "fleet-config",
            "status": "configuration_error",
            "error_category": "invalid_shape",
            "message": "ZENDOC_LOCAL_MODEL_FLEET_JSON must be a JSON list.",
        }]

    profiles = []
    seen = set()
    for index, item in enumerate(data[:MAX_AUXILIARY_MODELS]):
        if not isinstance(item, dict):
            profiles.append({
                "id": f"aux-{index + 1}",
                "status": "configuration_error",
                "error_category": "invalid_profile",
            })
            continue
        profile_id = str(item.get("id") or f"aux-{index + 1}").strip()[:80]
        if not profile_id or profile_id in seen:
            profiles.append({
                "id": profile_id or f"aux-{index + 1}",
                "status": "configuration_error",
                "error_category": "duplicate_or_missing_id",
            })
            continue
        seen.add(profile_id)
        provider = str(item.get("provider") or "ollama").strip().lower()
        model = str(item.get("model") or "").strip()[:160]
        base_url = str(item.get("base_url") or "http://127.0.0.1:11434").strip()
        allow_private = bool(item.get("allow_private_network", False))
        roles = _safe_roles(item.get("roles"))

        profile = {
            "id": profile_id,
            "provider": provider,
            "model": model or None,
            "base_url": base_url,
            "roles": roles,
            "status": "configured",
            "tool_authority": False,
            "secret_access": False,
        }
        if provider not in {"ollama", "openai_compatible"}:
            profile.update(status="configuration_error", error_category="invalid_provider")
            profiles.append(profile)
            continue
        if not model:
            profile.update(status="integration_required", error_category="model_not_configured")
            profiles.append(profile)
            continue
        try:
            validate_local_provider_url(base_url, allow_private)
        except ValueError:
            profile.update(status="configuration_error", error_category="unsafe_provider_url")
            profiles.append(profile)
            continue

        if check_health:
            settings = LocalAISettings(
                enabled=True,
                provider=provider,
                base_url=base_url,
                model=model,
                timeout=max(1, min(int(item.get("timeout") or 10), 120)),
                allow_private_network=allow_private,
            )
            health = create_local_ai_provider(settings).health_check().to_dict()
            profile["runtime"] = health
            profile["status"] = health.get("status") or profile["status"]
        profiles.append(profile)
    return profiles


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
        "selection_rule": (
            "Deterministic safety and authorization run first. The configured primary local "
            "model is preferred for allowed advisory work; auxiliary models are role-scoped "
            "and never receive direct tool authority."
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
    router = ModelRouter()
    advisory = router.route(
        clean,
        intent="owner_platform_control",
        task_type="owner_operational_summary",
        allow_cloud=False,
        cloud_consent=False,
        privacy_class=PrivacyClass.INTERNAL,
        risk_class=RiskClass.READ_ONLY,
        structured_output_required=True,
    )
    return {
        "status": "preview",
        "intent": intent,
        "delegation": delegation,
        "model_advisory": {
            "success": advisory.success,
            "provider": advisory.provider,
            "model": advisory.model,
            "routing_reason": advisory.routing_reason,
            "fallback_used": advisory.fallback_used,
            "text": advisory.text,
        },
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
