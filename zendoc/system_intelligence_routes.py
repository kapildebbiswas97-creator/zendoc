"""Owner-only read APIs for inspecting ZENDOC's automation architecture."""
from __future__ import annotations

from flask import Blueprint, jsonify

from .agent_fleet import automation_manifest, list_fleet_agents
from .benefit_sources import list_sources
from .model_portfolio import list_model_roles
from .capability_registry import get_capability_registry
from .no_capital_status import no_capital_completion_report
from .regulated_domains import list_regulated_domains
from .security import owner_required


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
        "capabilities": get_capability_registry(),
        "no_capital_progress": no_capital_completion_report(),
    })
