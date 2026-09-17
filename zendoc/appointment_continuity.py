"""Provider-authoritative appointment continuity for the ZENDOC Agent OS.

This bridge reacts only to appointment state already persisted by an authorized
provider/owner workflow. It never accepts a model assertion as provider truth.
It keeps provider-recorded, owner-recorded and patient-reported provenance
separate while advancing an existing appointment Care Journey when one exists.
"""
from __future__ import annotations

import json
from typing import Any

from .care_journey import CareJourney, transition_journey
from .db import get_db, now_iso
from .health_timeline import add_timeline_event
from .security import is_owner


_PROVIDER_ROLES = {"doctor", "hospital"}
_SYNC_STATUSES = {"confirmed", "cancelled", "completed"}


def _value(actor: Any, key: str, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    return actor.get(key, default) if isinstance(actor, dict) else default


def _actor_id(actor: Any) -> int:
    return int(_value(actor, "id", 0) or 0)


def _actor_role(actor: Any) -> str:
    return str(_value(actor, "role", "") or "").strip().lower()


def _decode(value: Any) -> dict:
    try:
        decoded = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _find_linked_journey(patient_id: int, appointment_id: int):
    rows = get_db().execute(
        """
        SELECT * FROM care_journeys
        WHERE patient_id=? AND status='active'
        ORDER BY updated_at DESC, id DESC
        LIMIT 50
        """,
        (int(patient_id),),
    ).fetchall()
    for row in rows:
        provenance = _decode(row["provenance_json"])
        try:
            linked_id = int(provenance.get("appointment_id") or 0)
        except (TypeError, ValueError):
            linked_id = 0
        if linked_id == int(appointment_id):
            return row, provenance
    return None, None


def _persist_transition(row, provenance: dict, *, target_state: str, reason: str,
                        actor_type: str, actor_id: int, next_safe_action: str,
                        required_actor: str | None = None,
                        required_consent: str | None = None,
                        transition_provenance: dict | None = None):
    current = CareJourney(
        journey_id=row["journey_uid"],
        patient_id=int(row["patient_id"]),
        state=row["state"],
        next_safe_action=row["next_safe_action"],
        blocked_reason=row["blocked_reason"],
        required_actor=row["required_actor"],
        required_consent=row["required_consent"],
        provenance=dict(provenance or {}),
        history=(),
    )
    advanced = transition_journey(
        current,
        target_state=target_state,
        reason=reason,
        actor_type=actor_type,
        next_safe_action=next_safe_action,
        required_actor=required_actor,
        required_consent=required_consent,
        provenance=transition_provenance or {},
    )
    event = advanced.history[-1]
    db = get_db()
    stamp = now_iso()
    db.execute(
        """
        UPDATE care_journeys
        SET state=?,next_safe_action=?,blocked_reason=?,required_actor=?,required_consent=?,
            provenance_json=?,status='active',updated_at=?
        WHERE id=? AND state=?
        """,
        (
            advanced.state,
            advanced.next_safe_action,
            advanced.blocked_reason,
            advanced.required_actor,
            advanced.required_consent,
            json.dumps(advanced.provenance, sort_keys=True, separators=(",", ":")),
            stamp,
            int(row["id"]),
            row["state"],
        ),
    )
    db.execute(
        """
        INSERT INTO care_journey_events
        (journey_id,previous_state,state,reason,actor_type,actor_id,provenance_json,created_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            int(row["id"]),
            event.previous_state,
            event.state,
            event.reason,
            event.actor_type,
            int(actor_id),
            json.dumps(event.provenance, sort_keys=True, separators=(",", ":")),
            event.occurred_at,
        ),
    )
    db.commit()
    updated = db.execute("SELECT * FROM care_journeys WHERE id=?", (int(row["id"]),)).fetchone()
    return updated, _decode(updated["provenance_json"])


def _timeline_event(appointment, status: str, source: str, actor_id: int) -> int | None:
    event_type = f"appointment_{status}"
    source_ref = f"appointment:{int(appointment['id'])}:{status}"
    existing = get_db().execute(
        """
        SELECT id FROM health_timeline_events
        WHERE patient_id=? AND event_type=? AND source=? AND source_ref=?
        LIMIT 1
        """,
        (int(appointment["patient_id"]), event_type, source, source_ref),
    ).fetchone()
    if existing:
        return int(existing["id"])
    label = {
        "confirmed": "Appointment confirmed",
        "cancelled": "Appointment cancelled",
        "completed": "Appointment completed",
    }[status]
    return add_timeline_event(
        int(appointment["patient_id"]),
        event_type,
        label,
        event_at=now_iso(),
        summary=f"Appointment #{int(appointment['id'])} status changed to {status} by an authorized care operator.",
        provider_name=appointment["provider_name"],
        source=source,
        source_ref=source_ref,
        created_by=int(actor_id),
    )


def sync_provider_appointment_status(actor: Any, appointment_id: int) -> dict:
    """Synchronize a persisted provider-side appointment outcome.

    The caller cannot choose the status here. The status is re-read from the
    appointment row after the authorized status-transition workflow commits it.
    """
    actor_id = _actor_id(actor)
    role = _actor_role(actor)
    if not actor_id or (role not in _PROVIDER_ROLES and not is_owner(actor)):
        raise PermissionError("Only the assigned provider or ZENDOC owner may synchronize appointment continuity.")

    appointment = get_db().execute(
        """
        SELECT id,patient_id,provider_id,provider_profile_id,provider_name,scheduled_for,status
        FROM appointments WHERE id=?
        """,
        (int(appointment_id),),
    ).fetchone()
    if not appointment:
        raise LookupError("Appointment not found.")
    if role in _PROVIDER_ROLES and int(appointment["provider_id"] or 0) != actor_id:
        raise PermissionError("Only the assigned provider may synchronize this appointment.")

    status = str(appointment["status"] or "").strip().lower()
    if status not in _SYNC_STATUSES:
        return {"appointment_id": int(appointment_id), "status": status, "synchronized": False}

    provider_authoritative = role in _PROVIDER_ROLES and int(appointment["provider_id"] or 0) == actor_id
    source = "PROVIDER_RECORDED" if provider_authoritative else "OWNER_RECORDED"
    confirmation_state = (
        f"{status}_by_provider" if provider_authoritative else f"{status}_by_owner_override"
    )
    timeline_event_id = _timeline_event(appointment, status, source, actor_id)

    row, provenance = _find_linked_journey(int(appointment["patient_id"]), int(appointment_id))
    if not row:
        return {
            "appointment_id": int(appointment_id),
            "status": status,
            "synchronized": True,
            "timeline_event_id": timeline_event_id,
            "care_journey_id": None,
            "provider_authoritative": provider_authoritative,
        }

    common = {
        "source": "appointment_status_sync",
        "appointment_id": int(appointment_id),
        "provider_profile_id": int(appointment["provider_profile_id"] or 0) or None,
        "provider_confirmation_state": confirmation_state,
        "provenance_class": source,
    }

    state = str(row["state"])
    if status == "confirmed" and state == "WAITING_PROVIDER":
        row, provenance = _persist_transition(
            row,
            provenance,
            target_state="WAITING_HUMAN",
            reason="Authorized provider confirmed the connected appointment.",
            actor_type="provider" if provider_authoritative else "owner_override",
            actor_id=actor_id,
            next_safe_action="attend_confirmed_appointment",
            required_actor="patient",
            transition_provenance=common,
        )

    elif status == "cancelled" and state in {"WAITING_PROVIDER", "WAITING_HUMAN"}:
        if state == "WAITING_PROVIDER":
            row, provenance = _persist_transition(
                row,
                provenance,
                target_state="WAITING_HUMAN",
                reason="The connected appointment was cancelled before provider confirmation completed.",
                actor_type="provider" if provider_authoritative else "owner_override",
                actor_id=actor_id,
                next_safe_action="refine_provider_search",
                required_actor="patient",
                transition_provenance=common,
            )
        row, provenance = _persist_transition(
            row,
            provenance,
            target_state="PROVIDER_SEARCH",
            reason="The cancelled appointment returned to truthful provider discovery.",
            actor_type="system",
            actor_id=actor_id,
            next_safe_action="search_verified_and_external_providers",
            required_actor=None,
            transition_provenance=common,
        )

    elif status == "completed" and state in {"WAITING_PROVIDER", "WAITING_HUMAN", "CONSULTATION"}:
        if state == "WAITING_PROVIDER":
            row, provenance = _persist_transition(
                row,
                provenance,
                target_state="WAITING_HUMAN",
                reason="Completed appointment reconciled a previously pending provider response.",
                actor_type="system",
                actor_id=actor_id,
                next_safe_action="reconcile_completed_visit",
                required_actor="patient",
                transition_provenance=common,
            )
            state = "WAITING_HUMAN"
        if state == "WAITING_HUMAN":
            row, provenance = _persist_transition(
                row,
                provenance,
                target_state="CONSULTATION",
                reason="A provider-authoritative completed appointment established that the scheduled visit occurred.",
                actor_type="provider" if provider_authoritative else "owner_override",
                actor_id=actor_id,
                next_safe_action="coordinate_post_visit_continuity",
                transition_provenance=common,
            )
            state = "CONSULTATION"
        if state == "CONSULTATION":
            row, provenance = _persist_transition(
                row,
                provenance,
                target_state="FOLLOW_UP",
                reason="Completed visit moved the care journey to non-clinical follow-through.",
                actor_type="system",
                actor_id=actor_id,
                next_safe_action="schedule_safe_follow_up",
                transition_provenance=common,
            )

    return {
        "appointment_id": int(appointment_id),
        "status": status,
        "synchronized": True,
        "timeline_event_id": timeline_event_id,
        "care_journey_id": int(row["id"]),
        "care_journey_state": str(row["state"]),
        "provider_authoritative": provider_authoritative,
        "provenance_class": source,
    }
