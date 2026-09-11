"""Truthful integration bridge from working ZENDOC operations into CareLoop.

Only ZENDOC-owned workflows with a real persisted operational record are linked
here. This module must never label a free-text/external provider as integrated.
"""
from __future__ import annotations

import re

from flask import current_app, g, request

from .care_action_ledger import create_action, ensure_care_action_ledger_schema, sync_registered_appointment_status
from .care_journey_store import create_persisted_journey
from .db import get_db


_APPOINTMENT_STATUS_PATH = re.compile(r"^/appointments/(\d+)/status$")


def finish_careloop_request(response):
    """Mirror successful internal appointment operations into CareLoop.

    This runs after the existing route authorization and persistence logic. A
    bridge failure is logged and does not rewrite the already-committed source
    appointment; reconciliation can safely be retried because linking is
    idempotent by service_ref.
    """
    try:
        if request.method != "POST" or int(response.status_code) >= 400:
            return response
        actor = g.get("user")
        if not actor:
            return response

        if request.path == "/appointments":
            location = str(response.headers.get("Location") or "")
            if "requested=1" in location and str(actor["role"]) == "patient":
                _link_latest_registered_appointment(actor)
            return response

        match = _APPOINTMENT_STATUS_PATH.match(request.path)
        if match and int(response.status_code) < 400:
            appointment_id = int(match.group(1))
            row = get_db().execute(
                "SELECT id,provider_id,status FROM appointments WHERE id=?",
                (appointment_id,),
            ).fetchone()
            if row and row["provider_id"]:
                sync_registered_appointment_status(actor, appointment_id, row["status"])
    except Exception:
        current_app.logger.exception("CareLoop appointment integration bridge failed safely.")
    return response


def _link_latest_registered_appointment(patient):
    ensure_care_action_ledger_schema()
    db = get_db()
    appointment = db.execute(
        """
        SELECT id,patient_id,provider_id,provider_name,provider_profile_id,specialty,
               scheduled_for,reason,status,created_at
        FROM appointments
        WHERE patient_id=? AND provider_id IS NOT NULL
        ORDER BY id DESC LIMIT 1
        """,
        (int(patient["id"]),),
    ).fetchone()
    if not appointment:
        return None

    service_ref = f"zendoc_appointment:{int(appointment['id'])}"
    existing = db.execute(
        "SELECT id FROM care_actions WHERE service_ref=? AND patient_id=? ORDER BY id DESC LIMIT 1",
        (service_ref, int(patient["id"])),
    ).fetchone()
    if existing:
        return int(existing["id"])

    provider = db.execute(
        """
        SELECT u.id,u.active,p.verification_status
        FROM users u LEFT JOIN provider_profiles p ON p.user_id=u.id
        WHERE u.id=? AND u.role IN ('doctor','hospital','pharmacy')
        """,
        (int(appointment["provider_id"]),),
    ).fetchone()
    if not provider or not bool(provider["active"]):
        return None

    journey = create_persisted_journey(
        patient,
        provenance={
            "source": "zendoc_registered_provider_appointment",
            "appointment_id": int(appointment["id"]),
            "provider_id": int(appointment["provider_id"]),
        },
    )
    action = create_action(
        patient,
        int(journey["id"]),
        {
            "action_type": "appointment",
            "title": f"Appointment with {appointment['provider_name']}",
            "rationale": appointment["reason"] or "Patient requested this appointment through ZENDOC.",
            "status": "STAGED",
            "human_confirmation_required": True,
            "owner_type": "patient",
            "owner_id": int(patient["id"]),
            "provider_name": appointment["provider_name"],
            "service_ref": service_ref,
            "due_at": appointment["scheduled_for"],
            "evidence": {
                "source_type": "zendoc_appointment_record",
                "appointment_id": int(appointment["id"]),
            },
            "provenance": {
                "source": "zendoc_registered_provider_appointment",
                "appointment_id": int(appointment["id"]),
                "provider_id": int(appointment["provider_id"]),
                "provider_profile_id": appointment["provider_profile_id"],
                "provider_verification_status": provider["verification_status"],
            },
        },
    )
    return int(action["id"])
