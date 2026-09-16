"""Patient-facing care continuity, handoff, and evidence passport surfaces."""
from __future__ import annotations

from flask import Blueprint, abort, g, jsonify, render_template, request

from .care_action_ledger import list_actions
from .care_journey_store import list_patient_journeys
from .clinician_handoff import build_clinician_handoff_packet
from .db import get_db
from .evidence_passport import get_evidence_passport, list_evidence_passports
from .routes import audit
from .security import login_required

bp = Blueprint("care_continuity", __name__)


def _patient_only():
    if not g.user or g.user["role"] != "patient":
        abort(403)


def _journey_cards(user):
    cards = []
    for journey in list_patient_journeys(user, limit=12):
        actions = list_actions(user, journey["id"])
        cards.append({
            "journey": journey,
            "open_actions": [a for a in actions if a.get("status") not in {"COMPLETED", "BLOCKED", "CANCELLED"}],
            "completed_actions": [a for a in actions if a.get("status") == "COMPLETED"],
            "outcome_count": sum(len(a.get("outcomes") or []) for a in actions),
        })
    return cards


@bp.route("/care-continuity", methods=("GET", "POST"))
@login_required
def care_continuity_page():
    _patient_only()
    packet = build_clinician_handoff_packet(
        g.user,
        reason_for_visit=request.form.get("reason_for_visit", "") if request.method == "POST" else "",
        questions=request.form.get("questions", "") if request.method == "POST" else "",
    )
    audit("view", "care_continuity", str(g.user["id"]))
    get_db().commit()
    return render_template(
        "care_continuity.html",
        handoff=packet,
        passports=list_evidence_passports(g.user, 12),
        journey_cards=_journey_cards(g.user),
        prepared=request.method == "POST",
    )


@bp.get("/api/v1/clinician-handoff")
@login_required
def api_clinician_handoff():
    _patient_only()
    packet = build_clinician_handoff_packet(
        g.user,
        reason_for_visit=request.args.get("reason_for_visit"),
        questions=request.args.getlist("question") or request.args.get("questions"),
    )
    audit("export", "clinician_handoff", str(g.user["id"]))
    get_db().commit()
    return jsonify({"handoff_packet": packet})


@bp.get("/api/v1/ai-evidence-passports")
@login_required
def api_ai_evidence_passports():
    _patient_only()
    return jsonify({"passports": list_evidence_passports(g.user, request.args.get("limit", 25))})


@bp.get("/api/v1/ai-evidence-passports/<int:interaction_id>")
@login_required
def api_ai_evidence_passport(interaction_id):
    _patient_only()
    try:
        passport = get_evidence_passport(g.user, interaction_id)
    except LookupError:
        abort(404)
    return jsonify({"passport": passport})
