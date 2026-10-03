"""Owner integration readiness dashboard."""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .integration_probes import integration_probe_snapshot, run_integration_probe
from .integration_readiness import integration_readiness_snapshot
from .security import owner_required


bp = Blueprint("integration_readiness", __name__)


@bp.get("/admin/integrations")
@owner_required
def integration_center():
    return render_template(
        "integration_center.html",
        snapshot=integration_readiness_snapshot(),
        probes=integration_probe_snapshot(),
    )


@bp.post("/admin/integrations/probe/<integration_key>")
@owner_required
def integration_probe(integration_key):
    try:
        result = run_integration_probe(g.user, integration_key)
        if result["status"] == "working":
            flash(
                f"{result['label']} runtime probe passed ({result['evidence_code']}).",
                "success",
            )
        elif result["status"] == "integration_required":
            flash(
                f"{result['label']} still requires configuration ({result['evidence_code']}).",
                "warning",
            )
        else:
            flash(
                f"{result['label']} runtime probe is {result['status']} ({result['evidence_code']}).",
                "warning",
            )
    except LookupError:
        flash("Unsupported integration probe.", "error")
    return redirect(url_for("integration_readiness.integration_center"))
