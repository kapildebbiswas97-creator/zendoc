"""Unified patient-facing Care OS view.

This module composes existing ZENDOC capabilities into one read-only control
surface.  It does not create a second care engine and it never turns tracking
records into claims of external clinical execution.
"""
from __future__ import annotations

from flask import Blueprint, abort, current_app, g, redirect, render_template, session, url_for

from .care_action_ledger import list_actions
from .care_journey_store import list_patient_journeys
from .db import get_db
from .family_care import list_family_access_grants, list_family_members
from .health_access import list_access_grants
from .health_analytics import get_personal_health_baseline
from .health_memory_continuity import determine_next_safe_actions, get_health_memory_provenance_summary


bp = Blueprint("care_os", __name__)


def _patient_user():
    user = getattr(g, "user", None)
    if user is None and session.get("user_id"):
        user = get_db().execute(
            "SELECT * FROM users WHERE id=? AND active=1",
            (int(session["user_id"]),),
        ).fetchone()
    if user is None:
        return None
    item = dict(user)
    if item.get("role") != "patient":
        abort(403)
    return item


def _safe(label, loader, default):
    try:
        return loader()
    except Exception as error:  # The overview must not fail because an optional panel is unavailable.
        current_app.logger.warning("Care OS panel %s unavailable: %s", label, error)
        return default


def _baseline_summaries(user):
    rows = get_db().execute(
        """
        SELECT metric_type, MAX(recorded_at) AS latest
        FROM health_metrics
        WHERE user_id=?
        GROUP BY metric_type
        ORDER BY latest DESC
        LIMIT 4
        """,
        (int(user["id"]),),
    ).fetchall()
    summaries = []
    for row in rows:
        try:
            summaries.append(
                get_personal_health_baseline(
                    user,
                    row["metric_type"],
                    patient_id=int(user["id"]),
                    baseline_days=90,
                    recent_days=7,
                )
            )
        except (LookupError, PermissionError, ValueError) as error:
            current_app.logger.info("Care OS baseline skipped for %s: %s", row["metric_type"], error)
    return summaries


def _evidence_passport(actions):
    passport = []
    for action in actions:
        evidence = action.get("evidence") if isinstance(action.get("evidence"), dict) else {}
        provenance = action.get("provenance") if isinstance(action.get("provenance"), dict) else {}
        outcomes = action.get("outcomes") if isinstance(action.get("outcomes"), list) else []
        source = (
            provenance.get("source")
            or evidence.get("source")
            or action.get("integration_source_type")
            or "ledger_record"
        )
        confidence = evidence.get("confidence") or provenance.get("confidence")
        verified = any(str(item.get("status") or "").upper() == "VERIFIED" for item in outcomes)
        passport.append(
            {
                "action_id": action.get("id"),
                "title": action.get("title") or "Care action",
                "source": str(source),
                "confidence": confidence,
                "review_state": "VERIFIED" if verified else ("REPORTED" if outcomes else "UNREVIEWED"),
                "integration_status": action.get("integration_status") or "TRACKING_ONLY",
                "external_execution": bool(action.get("external_execution")),
                "updated_at": action.get("updated_at"),
            }
        )
    return passport


@bp.get("/care-os")
def care_os_home():
    user = _patient_user()
    if user is None:
        return redirect(url_for("main.login", role="patient"))

    patient_id = int(user["id"])
    journeys = _safe(
        "journeys",
        lambda: list_patient_journeys(user, patient_id=patient_id, limit=25),
        [],
    )

    action_total = 0
    active_action_total = 0
    integrated_action_total = 0
    all_actions = []
    enriched_journeys = []
    for raw_journey in journeys:
        journey = dict(raw_journey)
        actions = _safe(
            f"journey-{journey.get('id')}-actions",
            lambda journey_id=journey.get("id"): list_actions(user, journey_id),
            [],
        )
        journey["actions"] = actions
        journey["action_count"] = len(actions)
        journey["outcome_count"] = sum(len(action.get("outcomes") or []) for action in actions)
        enriched_journeys.append(journey)
        all_actions.extend(actions)

    action_total = len(all_actions)
    active_action_total = sum(
        1 for item in all_actions if str(item.get("status") or "").upper() not in {"COMPLETED", "CANCELLED", "BLOCKED"}
    )
    integrated_action_total = sum(
        1 for item in all_actions if item.get("integration_status") == "ACTUALLY_INTEGRATED"
    )

    provenance = _safe(
        "health-memory-provenance",
        lambda: get_health_memory_provenance_summary(user, actor=user),
        {"total_events": 0, "by_provenance": {}, "recent_events": []},
    )
    next_actions = _safe(
        "next-safe-actions",
        lambda: determine_next_safe_actions(user, actor=user),
        [],
    )
    provider_grants = _safe("provider-consent", lambda: list_access_grants(patient_id), [])
    family_given = _safe("family-consent-given", lambda: list_family_access_grants(user, "given"), [])
    family_received = _safe("family-consent-received", lambda: list_family_access_grants(user, "received"), [])
    family_members = _safe("family-members", lambda: list_family_members(user), [])
    baselines = _safe("personal-baselines", lambda: _baseline_summaries(user), [])
    evidence_passport = _evidence_passport(all_actions)

    active_provider_grants = sum(1 for item in provider_grants if item.get("active"))
    active_family_grants = sum(1 for item in family_given + family_received if item.get("active"))
    outcome_total = sum(len(item.get("outcomes") or []) for item in all_actions)

    return render_template(
        "care_os.html",
        user=user,
        journeys=enriched_journeys,
        next_actions=next_actions,
        provenance=provenance,
        provider_grants=provider_grants,
        family_given=family_given,
        family_received=family_received,
        family_members=family_members,
        baselines=baselines,
        evidence_passport=evidence_passport,
        action_total=action_total,
        active_action_total=active_action_total,
        integrated_action_total=integrated_action_total,
        outcome_total=outcome_total,
        active_provider_grants=active_provider_grants,
        active_family_grants=active_family_grants,
    )
