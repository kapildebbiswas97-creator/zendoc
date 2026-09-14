"""Web surface for ZENDOC Universal Healthcare Search."""
from __future__ import annotations

from flask import Blueprint, g, redirect, render_template, request, session, url_for

from .db import get_db
from .provider_service import SPECIALTIES
from .universal_health_search import GROUP_LABELS, SEARCH_CATEGORIES, universal_search


bp = Blueprint("universal_search", __name__)


def _active_user():
    user = getattr(g, "user", None)
    if user is None and session.get("user_id"):
        user = get_db().execute(
            "SELECT * FROM users WHERE id=? AND active=1",
            (int(session["user_id"]),),
        ).fetchone()
    return dict(user) if user is not None else None


@bp.route("/universal-search", methods=("GET", "POST"))
def search_home():
    user = _active_user()
    if user is None:
        return redirect(url_for("main.login", role="patient"))

    text = request.values.get("q", "")
    category = request.values.get("category", "all")
    latitude = request.values.get("latitude")
    longitude = request.values.get("longitude")
    radius_km = request.values.get("radius_km", 10)

    result = None
    if str(text or "").strip() or (latitude not in (None, "") and longitude not in (None, "")):
        result = universal_search(
            text=text,
            category=category,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
        )

    universal_query = {
        "text": str(text or "").strip(),
        "category": str(category or "all").strip().lower(),
        "latitude": latitude,
        "longitude": longitude,
        "radius_km": radius_km,
    }
    legacy_query = {
        "category": "doctor",
        "specialty": "",
        "location": "",
        "latitude": latitude,
        "longitude": longitude,
        "radius_km": radius_km,
    }
    return render_template(
        "finder.html",
        result=result,
        query=legacy_query,
        universal_query=universal_query,
        universal_mode=True,
        universal_categories=SEARCH_CATEGORIES,
        group_labels=GROUP_LABELS,
        specialties=SPECIALTIES,
        search_event_id=None,
        current_user=user,
    )
