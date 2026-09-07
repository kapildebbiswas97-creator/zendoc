"""Owner-only read APIs for inspecting ZENDOC's automation architecture."""
from __future__ import annotations

from flask import Blueprint, jsonify

from .agent_fleet import automation_manifest, list_fleet_agents
from .benefit_sources import list_sources
from .model_portfolio import list_model_roles
from .capability_registry import get_capability_registry
from .no_capital_status import no_capital_completion_report
from .regulated_domains import list_regulated_domains
from .public_source_registry import list_public_ingestion_sources
from .pilot_analytics import pilot_scorecard
from .security import owner_required
from .database_reliability import backup_readiness, create_sqlite_backup, readiness_report
from .observability import incident_summary, list_runbooks, request_metrics, agent_metrics, emergency_metrics
from .launch_readiness import first50_launch_readiness


bp = Blueprint("system_intelligence", __name__)


@bp.get("/owner/intelligence-manifest")
@owner_required
def intelligence_manifest():
    return jsonify({
        "status": "ok",
        "automation": automation_manifest(),
        "agents": list_fleet_agents(),
        "model_roles": list_model_roles(),
        "benefit_sources": list_sources(),
        "regulated_domains": list_regulated_domains(),
        "public_ingestion_sources": list_public_ingestion_sources(),
        "pilot_scorecard": pilot_scorecard(),
        "capabilities": get_capability_registry(),
        "no_capital_progress": no_capital_completion_report(),
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
