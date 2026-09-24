"""Dedicated, private Mental Wellness & Awareness surface."""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .ai import mental_health_support
from .mental_wellness import (
    create_journal_entry,
    delete_checkin,
    delete_journal_entry,
    list_checkins,
    list_journal_entries,
    record_checkin,
    wellness_summary,
)
from .routes import audit
from .security import login_required, role_required

bp = Blueprint("mental_wellness", __name__)


@bp.get("/mental-lounge")
@login_required
def mental_lounge_legacy_redirect():
    """Keep pre-restoration Mental Lounge links from becoming 404s."""
    return redirect(url_for("mental_wellness.mental_wellness_page"))


@bp.route("/mental-wellness", methods=("GET", "POST"))
@login_required
@role_required("patient")
def mental_wellness_page():
    guidance_result = None
    if request.method == "POST":
        action = str(request.form.get("action") or "").strip()
        try:
            if action == "checkin":
                item = record_checkin(g.user, request.form)
                audit("create", "mental_wellness_checkin", str(item["id"]), actor=g.user)
                flash("Private wellbeing check-in saved.", "success")
            elif action == "journal":
                item = create_journal_entry(g.user, request.form)
                audit("create", "mental_wellness_journal", str(item["id"]), actor=g.user)
                flash("Private journal entry saved.", "success")
            elif action == "guidance":
                guidance_result = mental_health_support(
                    request.form.get("age_group", "adult"),
                    request.form.get("context", ""),
                    request.form.get("stress_level", 0),
                )
                audit("use", "mental_wellness_guidance", action, actor=g.user)
            elif action == "delete_checkin":
                checkin_id = int(request.form.get("checkin_id") or 0)
                delete_checkin(g.user, checkin_id)
                audit("delete", "mental_wellness_checkin", str(checkin_id), actor=g.user)
                flash("Private wellbeing check-in deleted.", "success")
            elif action == "delete_journal":
                entry_id = int(request.form.get("entry_id") or 0)
                delete_journal_entry(g.user, entry_id)
                audit("delete", "mental_wellness_journal", str(entry_id), actor=g.user)
                flash("Private journal entry deleted.", "success")
            else:
                raise ValueError("Unsupported Mental Wellness action.")
        except (TypeError, ValueError, LookupError, PermissionError) as exc:
            flash(str(exc), "error")

        if action != "guidance" or guidance_result is None:
            return redirect(url_for("mental_wellness.mental_wellness_page"))

    return render_template(
        "mental_wellness.html",
        checkins=list_checkins(g.user),
        journal_entries=list_journal_entries(g.user),
        wellness_summary=wellness_summary(g.user),
        guidance_result=guidance_result,
    )
