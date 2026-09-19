"""Dedicated, visible Mental Wellness & Awareness surface.

The existing AI page retains its deterministic mental-health check-in. This
blueprint gives the feature a stable first-class route so navigation changes
cannot accidentally hide it again.
"""
from flask import Blueprint, render_template

from .security import login_required, role_required

bp = Blueprint("mental_wellness", __name__)


@bp.get("/mental-wellness")
@login_required
@role_required("patient")
def mental_wellness_page():
    return render_template("mental_wellness.html")
