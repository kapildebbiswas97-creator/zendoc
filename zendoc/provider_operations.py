"""Provider-scoped operational metrics for ZENDOC provider workspaces."""
from __future__ import annotations

from typing import Any

from .db import get_db, now_iso


PROVIDER_ROLES = {"doctor", "hospital", "pharmacy"}


def provider_operational_metrics(user: Any) -> dict:
    if not user or user["role"] not in PROVIDER_ROLES or not bool(user["active"]):
        raise PermissionError("Only active provider accounts may view provider operations.")

    db = get_db()
    profile = db.execute(
        "SELECT id,verification_status FROM provider_profiles WHERE user_id=?",
        (int(user["id"]),),
    ).fetchone()
    if not profile:
        return {
            "provider_profile_id": None,
            "verification_status": None,
            "active_schedules": 0,
            "active_slot_holds": 0,
            "handoff_status_counts": {},
            "appointment_status_counts": {},
            "truth_notice": "Create a provider profile before operational metrics are available.",
        }

    profile_id = int(profile["id"])
    schedules = int(
        db.execute(
            "SELECT COUNT(*) c FROM provider_schedules WHERE provider_profile_id=? AND active=1",
            (profile_id,),
        ).fetchone()["c"] or 0
    )
    holds = int(
        db.execute(
            """
            SELECT COUNT(*) c FROM partner_slot_holds
            WHERE provider_profile_id=? AND status='active' AND expires_at>?
            """,
            (profile_id, now_iso()),
        ).fetchone()["c"] or 0
    )

    handoff_rows = db.execute(
        """
        SELECT status,COUNT(*) c
        FROM partner_booking_handoffs
        WHERE provider_profile_id=?
        GROUP BY status
        """,
        (profile_id,),
    ).fetchall()
    handoffs = {str(row["status"]): int(row["c"] or 0) for row in handoff_rows}

    appointment_rows = db.execute(
        """
        SELECT status,COUNT(*) c
        FROM appointments
        WHERE provider_id=?
        GROUP BY status
        """,
        (int(user["id"]),),
    ).fetchall()
    appointments = {str(row["status"]): int(row["c"] or 0) for row in appointment_rows}

    return {
        "provider_profile_id": profile_id,
        "verification_status": profile["verification_status"],
        "active_schedules": schedules,
        "active_slot_holds": holds,
        "handoff_status_counts": handoffs,
        "handoff_total": sum(handoffs.values()),
        "appointment_status_counts": appointments,
        "appointment_total": sum(appointments.values()),
        "truth_notice": (
            "These metrics are scoped to this provider profile. Partner handoffs are coordination requests, "
            "not confirmed patient appointments, and no clinical content is included."
        ),
    }
