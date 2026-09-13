"""Owner-only read APIs for inspecting ZENDOC's automation architecture."""
from __future__ import annotations

from collections import Counter

from flask import Blueprint, jsonify

from .agent_fleet import automation_manifest, list_fleet_agents
from .benefit_sources import list_sources
from .model_portfolio import list_model_roles
from .model_router import get_model_router
from .capability_registry import get_capability_registry
from .medical_knowledge_registry import list_medical_knowledge_sources
from .no_capital_status import no_capital_completion_report
from .regulated_domains import list_regulated_domains
from .public_source_registry import list_public_ingestion_sources
from .pilot_analytics import pilot_scorecard
from .security import owner_required
from .database_reliability import backup_readiness, create_sqlite_backup, readiness_report
from .observability import incident_summary, list_runbooks, request_metrics, agent_metrics, emergency_metrics
from .launch_readiness import first50_launch_readiness
from .scale_readiness import scale_readiness_report
from .tool_registry import CRITICAL_BLOCKED, TOOL_REGISTRY


bp = Blueprint("system_intelligence", __name__)


def _tool_governance_summary() -> dict:
    """Return metadata-only tool governance facts without executing any tool."""
    risk_counts = Counter(tool.risk_class for tool in TOOL_REGISTRY.values())
    approval_gated = [
        tool.name
        for tool in TOOL_REGISTRY.values()
        if tool.requires_consent or tool.requires_owner_approval or tool.requires_doctor_approval
    ]
    blocked = [
        tool.name for tool in TOOL_REGISTRY.values() if tool.risk_class == CRITICAL_BLOCKED
    ]
    return {
        "registered_tools": len(TOOL_REGISTRY),
        "risk_class_counts": dict(sorted(risk_counts.items())),
        "approval_gated_tools": sorted(approval_gated),
        "critical_blocked_tools": sorted(blocked),
        "model_output_can_execute_tools": False,
        "execution_boundary": (
            "Models may propose structured actions only. Server-side policy, role, consent, "
            "approval, idempotency and audit checks decide whether a registered tool may run."
        ),
    }


def _ai_runtime_summary() -> dict:
    """Expose configuration/runtime truth without making external health-check calls."""
    runtime = get_model_router().status(check_health=False)
    return {
        "routing_mode": runtime.get("routing_mode"),
        "deterministic_safety": runtime.get("deterministic_safety", {}),
        "local_ai": runtime.get("local_ai", {}),
        "cloud_llm": runtime.get("cloud_llm", {}),
        "local_fallback": runtime.get("local_fallback", {}),
        "routing_policy": runtime.get("routing_policy", {}),
        "stats": runtime.get("stats", {}),
        "provider_errors": runtime.get("provider_errors", []),
        "fallback_reasons": runtime.get("fallback_reasons", []),
        "truth_boundary": (
            "Configured does not mean externally reachable. Live provider readiness requires "
            "an explicit owner health check; deterministic safety and fallback remain available."
        ),
    }


@bp.get("/owner/intelligence-manifest")
@owner_required
def intelligence_manifest():
    return jsonify({
        "status": "ok",
        "automation": automation_manifest(),
        "agents": list_fleet_agents(),
        "model_roles": list_model_roles(),
        "ai_runtime": _ai_runtime_summary(),
        "tool_governance": _tool_governance_summary(),
        "benefit_sources": list_sources(),
        "regulated_domains": list_regulated_domains(),
        "public_ingestion_sources": list_public_ingestion_sources(),
        "medical_knowledge_sources": list_medical_knowledge_sources(),
        "pilot_scorecard": pilot_scorecard(),
        "capabilities": get_capability_registry(),
        "no_capital_progress": no_capital_completion_report(),
    })


@bp.get("/owner/ai-runtime")
@owner_required
def owner_ai_runtime():
    """Metadata-only AI runtime view; does not contact configured external providers."""
    return jsonify({
        "status": "ok",
        "ai_runtime": _ai_runtime_summary(),
        "tool_governance": _tool_governance_summary(),
    })


@bp.get("/owner/medical-knowledge-sources")
@owner_required
def owner_medical_knowledge_sources():
    return jsonify({
        "status": "ok",
        "sources": list_medical_knowledge_sources(),
        "notice": (
            "These source families are approved for discovery and document-level review only. "
            "No source is automatically approved for bulk ingestion or patient-facing answers."
        ),
    })


@bp.get("/owner/pilot-scorecard")
@owner_required
def owner_pilot_scorecard():
    return jsonify(pilot_scorecard())


@bp.get("/owner/database-readiness")
@owner_required
def owner_database_readiness():
    return jsonify({
        "readiness": readiness_report(),
        "backup": backup_readiness(),
    })


@bp.post("/owner/database-backup")
@owner_required
def owner_database_backup():
    result = create_sqlite_backup()
    status = 201 if result.get("status") == "created" else 409
    return jsonify(result), status


@bp.get("/owner/scale-readiness")
@owner_required
def owner_scale_readiness():
    return jsonify(scale_readiness_report())


@bp.get("/owner/first50-readiness")
@owner_required
def owner_first50_readiness():
    return jsonify(first50_launch_readiness())


@bp.get("/owner/observability")
@owner_required
def owner_observability():
    pilot = pilot_scorecard()
    return jsonify({
        "incident": incident_summary(60),
        "requests_15m": request_metrics(15),
        "requests_60m": request_metrics(60),
        "agents_60m": agent_metrics(60),
        "emergency_60m": emergency_metrics(60),
        "pilot_signals": pilot.get("signals", []),
        "provider_responsiveness": pilot.get("provider_responsiveness", {}),
        "data_freshness": pilot.get("data_freshness", {}),
        "engagement": pilot.get("engagement", {}),
    })


@bp.get("/owner/incident-runbooks")
@owner_required
def owner_incident_runbooks():
    return jsonify({"runbooks": list_runbooks()})
