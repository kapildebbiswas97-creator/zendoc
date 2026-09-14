"""India interoperability readiness for ABDM/ABHA, UHI and NHCX.

This module intentionally separates local product readiness from external
government-network connectivity.  Configuration alone never means a real
transaction occurred, and production connectivity is only reported when an
operator explicitly attests that the integration has been verified.
"""
from __future__ import annotations

import os
from typing import Iterable

from flask import Blueprint, abort, g, jsonify, redirect, render_template, session, url_for

from .db import get_db


bp = Blueprint("india_care_rail", __name__)


_RAILS = (
    {
        "id": "abdm",
        "name": "ABDM / ABHA",
        "purpose": "ABHA identity, consented health-record exchange and future HIP/HIU interoperability.",
        "mode_env": "ZENDOC_ABDM_MODE",
        "credential_envs": ("ZENDOC_ABDM_CLIENT_ID", "ZENDOC_ABDM_CLIENT_SECRET"),
        "verified_env": "ZENDOC_ABDM_PRODUCTION_VERIFIED",
        "capabilities": (
            "ABHA-aware identity workflows",
            "HIP/HIU consent and health-information exchange",
            "FHIR-aligned record portability",
        ),
    },
    {
        "id": "uhi",
        "name": "Unified Health Interface (UHI)",
        "purpose": "Open-network discovery and transactions for interoperable digital health services.",
        "mode_env": "ZENDOC_UHI_MODE",
        "credential_envs": ("ZENDOC_UHI_PARTICIPANT_ID", "ZENDOC_UHI_CREDENTIALS_CONFIGURED"),
        "verified_env": "ZENDOC_UHI_PRODUCTION_VERIFIED",
        "capabilities": (
            "Provider and service discovery",
            "Appointment and tele-consultation interoperability",
            "Future diagnostics, pharmacy and other network services",
        ),
    },
    {
        "id": "nhcx",
        "name": "National Health Claims Exchange (NHCX)",
        "purpose": "Standards-based health-claims interoperability when ZENDOC is formally onboarded.",
        "mode_env": "ZENDOC_NHCX_MODE",
        "credential_envs": ("ZENDOC_NHCX_PARTICIPANT_ID", "ZENDOC_NHCX_CREDENTIALS_CONFIGURED"),
        "verified_env": "ZENDOC_NHCX_PRODUCTION_VERIFIED",
        "capabilities": (
            "Claims exchange readiness",
            "Payer/provider workflow interoperability",
            "Future status and adjudication tracking",
        ),
    },
)


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "verified"}


def _configured(values: Iterable[str]) -> bool:
    for key in values:
        value = os.environ.get(key)
        if key.endswith("_CONFIGURED"):
            if not _truthy(value):
                return False
        elif not str(value or "").strip():
            return False
    return True


def _rail_state(definition: dict) -> dict:
    mode = str(os.environ.get(definition["mode_env"], "off") or "off").strip().lower()
    credentials_ready = _configured(definition["credential_envs"])
    production_verified = _truthy(os.environ.get(definition["verified_env"]))

    if mode in {"", "off", "disabled", "none"}:
        code = "NOT_CONNECTED"
        label = "Not connected"
        notice = "No external government-network connection is configured."
    elif mode == "sandbox":
        if credentials_ready:
            code = "SANDBOX_CONFIGURED"
            label = "Sandbox configured"
            notice = "Sandbox configuration is present; this does not mean production connectivity."
        else:
            code = "SANDBOX_MISSING_CREDENTIALS"
            label = "Sandbox incomplete"
            notice = "Sandbox mode is selected but required configuration is incomplete."
    elif mode == "production":
        if not credentials_ready:
            code = "PRODUCTION_MISSING_CREDENTIALS"
            label = "Production incomplete"
            notice = "Production mode is selected but required integration configuration is incomplete."
        elif production_verified:
            code = "PRODUCTION_VERIFIED"
            label = "Production verified"
            notice = "Production connectivity has been explicitly operator-verified."
        else:
            code = "PRODUCTION_UNVERIFIED"
            label = "Production not verified"
            notice = "Production configuration is present, but ZENDOC will not claim the integration is live until verification is recorded."
    else:
        code = "MISCONFIGURED"
        label = "Configuration error"
        notice = f"Unsupported integration mode: {mode}."

    external_live = code == "PRODUCTION_VERIFIED"
    return {
        "id": definition["id"],
        "name": definition["name"],
        "purpose": definition["purpose"],
        "capabilities": list(definition["capabilities"]),
        "status": code,
        "status_label": label,
        "notice": notice,
        "mode": mode or "off",
        "credentials_configured": credentials_ready,
        "production_verified": production_verified,
        "external_live": external_live,
        "external_execution": False,
    }


def get_india_care_rail_status() -> dict:
    rails = [_rail_state(item) for item in _RAILS]
    verified_count = sum(1 for item in rails if item["external_live"])
    return {
        "rails": rails,
        "verified_count": verified_count,
        "total": len(rails),
        "any_external_live": verified_count > 0,
        "all_production_verified": verified_count == len(rails),
        "truth_boundary": (
            "ZENDOC only marks an India Care Rail as live after explicit production verification. "
            "Configured code, sandbox credentials or local workflows do not prove an external transaction occurred."
        ),
    }


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


@bp.get("/india-care-rail")
def india_care_rail_page():
    user = _patient_user()
    if user is None:
        return redirect(url_for("main.login", role="patient"))
    return render_template(
        "india_care_rail.html",
        user=user,
        rail_status=get_india_care_rail_status(),
    )


@bp.get("/api/v1/india-care-rail/status")
def india_care_rail_status_api():
    user = _patient_user()
    if user is None:
        return jsonify({"error": "authentication_required"}), 401
    return jsonify(get_india_care_rail_status())
