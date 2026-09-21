"""Owner integration readiness dashboard."""
from flask import Blueprint,render_template

from .integration_readiness import integration_readiness_snapshot
from .security import owner_required

bp=Blueprint("integration_readiness",__name__)


@bp.get("/admin/integrations")
@owner_required
def integration_center():
    return render_template("integration_center.html",snapshot=integration_readiness_snapshot())
