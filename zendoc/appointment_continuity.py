"""Provider-authoritative appointment continuity for the ZENDOC Agent OS.

This bridge reacts only to appointment state already persisted by an authorized
provider/owner workflow. It never accepts a model assertion as provider truth.
It keeps provider-recorded, owner-recorded and patient-reported provenance
separate while advancing an existing appointment Care Journey when one exists.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from .care_action_ledger import ensure_care_action_ledger_schema, sync_registered_appointment_status
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


def _sync_linked_agent_task(provenance: dict, patient_id: int, provider_status: str) -> dict | None:
    """Resolve the exact persisted booking task from authoritative provider state."""
    try:
        task_id = int((provenance or {}).get("workflow_task_id") or 0)
    except (TypeError, ValueError):
        task_id = 0
    if not task_id:
        return None

    status = str(provider_status or "").strip().lower()
    if status not in _SYNC_STATUSES:
        return None
    target_status = "cancelled" if status == "cancelled" else "completed"
    summary = {
        "confirmed": "Authorized provider confirmed the connected appointment request.",
        "cancelled": "Authorized provider cancelled the connected appointment request.",
        "completed": "Authorized provider recorded the connected appointment as completed.",
    }[status]
    stamp = now_iso()
    db = get_db()
    db.execute(
        """
        UPDATE agent_tasks
        SET status=?,result_summary=?,completed_at=?,updated_at=?
        WHERE id=? AND requested_by=?
          AND task_type='specialist_workflow:appointment_booking'
          AND status='waiting_provider'
        """,
        (target_status, summary, stamp, stamp, task_id, int(patient_id)),
    )
    db.commit()
    row = db.execute(
        """
        SELECT id,status,assigned_agent,task_type
        FROM agent_tasks
        WHERE id=? AND requested_by=?
        """,
        (task_id, int(patient_id)),
    ).fetchone()
    return dict(row) if row else None


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
    persisted_status = "completed" if advanced.state == "COMPLETED" else "blocked" if advanced.state == "BLOCKED" else "active"
    updated = db.execute(
        """
        UPDATE care_journeys
        SET state=?,next_safe_action=?,blocked_reason=?,required_actor=?,required_consent=?,
            provenance_json=?,status=?,updated_at=?
        WHERE id=? AND state=?
        """,
        (
            advanced.state,
            advanced.next_safe_action,
            advanced.blocked_reason,
            advanced.required_actor,
            advanced.required_consent,
            json.dumps(advanced.provenance, sort_keys=True, separators=(",", ":")),
            persisted_status,
            stamp,
            int(row["id"]),
            row["state"],
        ),
    )
    if updated.rowcount != 1:
        db.rollback()
        raise ValueError("Care Journey changed concurrently; reconciliation must retry.")
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
    refreshed = db.execute("SELECT * FROM care_journeys WHERE id=?", (int(row["id"]),)).fetchone()
    return refreshed, _decode(refreshed["provenance_json"])


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


def _linked_care_action(appointment_id: int, patient_id: int):
    ensure_care_action_ledger_schema()
    return get_db().execute(
        """
        SELECT * FROM care_actions
        WHERE service_ref=? AND patient_id=?
        ORDER BY id DESC LIMIT 1
        """,
        (f"zendoc_appointment:{int(appointment_id)}", int(patient_id)),
    ).fetchone()


def _record_completion_outcome(actor: Any, appointment, *, provider_authoritative: bool) -> dict | None:
    """Create one verified operational outcome from a real provider completion.

    This proves that the connected visit was marked completed. It intentionally
    does not infer a diagnosis, prescription, treatment response or clinical
    finding from the appointment status.
    """
    ensure_care_action_ledger_schema()
    action = _linked_care_action(int(appointment["id"]), int(appointment["patient_id"]))
    if not action:
        return None
    if str(action["status"]) != "COMPLETED":
        synced = sync_registered_appointment_status(actor, int(appointment["id"]), "completed")
        if not synced:
            return None
        action = _linked_care_action(int(appointment["id"]), int(appointment["patient_id"]))
    if not action or str(action["status"]) != "COMPLETED":
        return None

    source_ref = f"appointment:{int(appointment['id'])}:completed"
    existing = get_db().execute(
        """
        SELECT * FROM care_outcomes
        WHERE action_id=? AND outcome_type='appointment_completion' AND source_ref=?
        ORDER BY id DESC LIMIT 1
        """,
        (int(action["id"]), source_ref),
    ).fetchone()
    if existing:
        item = dict(existing)
        item["provenance"] = _decode(item.pop("provenance_json"))
        return item

    actor_id = _actor_id(actor)
    source_type = "provider_appointment_status" if provider_authoritative else "owner_override_appointment_status"
    provenance = {
        "source": "zendoc_registered_provider_appointment",
        "appointment_id": int(appointment["id"]),
        "provider_id": int(appointment["provider_id"] or 0) or None,
        "evidence_type": "persisted_appointment_status",
        "appointment_status": "completed",
        "clinical_findings_inferred": False,
    }
    now = now_iso()
    cursor = get_db().execute(
        """
        INSERT INTO care_outcomes
        (outcome_uid,action_id,journey_id,patient_id,outcome_type,summary,value_text,numeric_value,unit,status,
         source_type,source_ref,observed_at,reviewer_id,provenance_json,created_by,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            f"care_outcome_{uuid.uuid4().hex}",
            int(action["id"]),
            int(action["journey_id"]),
            int(action["patient_id"]),
            "appointment_completion",
            "Authorized provider recorded that the connected visit was completed. No diagnosis, prescription, treatment response or clinical finding is inferred from this status.",
            "completed",
            None,
            None,
            "VERIFIED",
            source_type,
            source_ref,
            appointment["updated_at"] or now,
            actor_id,
            json.dumps(provenance, sort_keys=True, separators=(",", ":")),
            actor_id,
            now,
            now,
        ),
    )
    get_db().commit()
    row = get_db().execute("SELECT * FROM care_outcomes WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    item = dict(row)
    item["provenance"] = _decode(item.pop("provenance_json"))
    return item


def _outcome_timeline_event(appointment, outcome: dict, source: str, actor_id: int) -> int:
    source_ref = f"care_outcome:{int(outcome['id'])}"
    existing = get_db().execute(
        """
        SELECT id FROM health_timeline_events
        WHERE patient_id=? AND event_type='provider_outcome' AND source=? AND source_ref=?
        LIMIT 1
        """,
        (int(appointment["patient_id"]), source, source_ref),
    ).fetchone()
    if existing:
        return int(existing["id"])
    return add_timeline_event(
        int(appointment["patient_id"]),
        "provider_outcome",
        "Provider-recorded visit completion evidence",
        event_at=outcome.get("observed_at") or now_iso(),
        summary=(
            "A verified CareLoop outcome records that the connected visit was completed. "
            "This is operational completion evidence only; no diagnosis or treatment result is inferred."
        ),
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
        SELECT id,patient_id,provider_id,provider_profile_id,provider_name,scheduled_for,status,updated_at
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

    # CareLoop action mirrors only the already-persisted appointment status.
    care_action = sync_registered_appointment_status(actor, int(appointment_id), status)
    timeline_event_id = _timeline_event(appointment, status, source, actor_id)

    row, provenance = _find_linked_journey(int(appointment["patient_id"]), int(appointment_id))
    if not row:
        return {
            "appointment_id": int(appointment_id),
            "status": status,
            "synchronized": True,
            "timeline_event_id": timeline_event_id,
            "care_action_id": int(care_action["id"]) if care_action else None,
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

    outcome = None
    outcome_memory_event_id = None
    state = str(row["state"])
    if status == "confirmed" and state == "WAITING_PROVIDER":
        row, provenance = _persist_transition(
            row,
            provenance,
            target_state="WAITING_VISIT",
            reason="Authorized provider confirmed the connected appointment; the visit has not occurred yet.",
            actor_type="provider" if provider_authoritative else "owner_override",
            actor_id=actor_id,
            next_safe_action="attend_confirmed_appointment",
            required_actor="patient",
            transition_provenance=common,
        )

    elif status == "cancelled" and state in {"WAITING_PROVIDER", "WAITING_VISIT", "WAITING_HUMAN"}:
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

    elif status == "completed" and state in {"WAITING_PROVIDER", "WAITING_VISIT", "WAITING_HUMAN", "CONSULTATION"}:
        outcome = _record_completion_outcome(
            actor,
            appointment,
            provider_authoritative=provider_authoritative,
        )
        if outcome:
            outcome_memory_event_id = _outcome_timeline_event(
                appointment,
                outcome,
                source,
                actor_id,
            )
            common = {
                **common,
                "care_outcome_id": int(outcome["id"]),
                "health_memory_event_id": int(outcome_memory_event_id),
                "outcome_status": "VERIFIED",
            }

        if state in {"WAITING_PROVIDER", "WAITING_HUMAN"}:
            row, provenance = _persist_transition(
                row,
                provenance,
                target_state="WAITING_VISIT",
                reason="Provider-authoritative completion reconciled the visit gate before post-visit continuity.",
                actor_type="provider" if provider_authoritative else "owner_override",
                actor_id=actor_id,
                next_safe_action="reconcile_completed_visit",
                required_actor="patient",
                transition_provenance=common,
            )
            state = "WAITING_VISIT"
        if state == "WAITING_VISIT":
            row, provenance = _persist_transition(
                row,
                provenance,
                target_state="CONSULTATION",
                reason="A provider-authoritative completed appointment established that the scheduled visit occurred.",
                actor_type="provider" if provider_authoritative else "owner_override",
                actor_id=actor_id,
                next_safe_action="record_verified_post_visit_evidence",
                required_actor=None,
                transition_provenance=common,
            )
            state = "CONSULTATION"
        if state == "CONSULTATION" and outcome and outcome_memory_event_id:
            row, provenance = _persist_transition(
                row,
                provenance,
                target_state="FOLLOW_UP",
                reason="Verified appointment-completion evidence was recorded in CareLoop and Health Memory before follow-up generation.",
                actor_type="system",
                actor_id=actor_id,
                next_safe_action="review_post_visit_follow_up",
                transition_provenance=common,
            )

    workflow_task = _sync_linked_agent_task(
        provenance,
        int(appointment["patient_id"]),
        status,
    )

    return {
        "appointment_id": int(appointment_id),
        "status": status,
        "synchronized": True,
        "timeline_event_id": timeline_event_id,
        "care_action_id": int(care_action["id"]) if care_action else None,
        "care_outcome_id": int(outcome["id"]) if outcome else None,
        "health_memory_outcome_event_id": outcome_memory_event_id,
        "care_journey_id": int(row["id"]),
        "care_journey_state": str(row["state"]),
        "next_safe_action": row["next_safe_action"],
        "provider_authoritative": provider_authoritative,
        "provenance_class": source,
        "follow_up_ready": str(row["state"]) == "FOLLOW_UP",
        "workflow_task_id": int(workflow_task["id"]) if workflow_task else None,
        "workflow_task_status": workflow_task["status"] if workflow_task else None,
    }


def complete_follow_up(actor: Any, journey_id: int, *, user_confirmed: bool) -> dict:
    """Complete a post-visit journey only from the patient's explicit attestation.

    Provider-recorded visit evidence remains provider-recorded. This completion
    event is separately stored as USER_REPORTED and never upgrades patient input
    into provider truth.
    """
    actor_id = _actor_id(actor)
    if not actor_id or _actor_role(actor) != "patient" or not bool(_value(actor, "active", 0)):
        raise PermissionError("Only the active patient may complete post-visit follow-up.")
    if user_confirmed is not True:
        raise PermissionError("Fresh explicit patient confirmation is required to complete follow-up.")

    row = get_db().execute(
        "SELECT * FROM care_journeys WHERE id=? AND patient_id=?",
        (int(journey_id), actor_id),
    ).fetchone()
    if not row:
        raise LookupError("Care Journey not found for this patient.")
    provenance = _decode(row["provenance_json"])
    if row["state"] == "COMPLETED" and provenance.get("follow_up_completion_state") == "patient_reported":
        return {
            "care_journey_id": int(row["id"]),
            "care_journey_state": "COMPLETED",
            "next_safe_action": "none",
            "follow_up_completion_state": "patient_reported",
            "idempotent": True,
        }
    if row["state"] != "FOLLOW_UP":
        raise ValueError("Care Journey is not waiting for post-visit follow-up completion.")

    try:
        appointment_id = int(provenance.get("appointment_id") or 0)
        outcome_id = int(provenance.get("care_outcome_id") or 0)
    except (TypeError, ValueError):
        appointment_id = 0
        outcome_id = 0
    if not appointment_id or not outcome_id:
        raise ValueError("Verified provider outcome evidence is required before follow-up completion.")
    outcome = get_db().execute(
        """
        SELECT id,status,patient_id,source_ref FROM care_outcomes
        WHERE id=? AND patient_id=? AND status='VERIFIED'
        """,
        (outcome_id, actor_id),
    ).fetchone()
    if not outcome or outcome["source_ref"] != f"appointment:{appointment_id}:completed":
        raise ValueError("Verified appointment-completion evidence is missing or does not match this journey.")

    source_ref = f"care_journey:{int(row['id'])}:follow_up_completed"
    existing = get_db().execute(
        """
        SELECT id FROM health_timeline_events
        WHERE patient_id=? AND event_type='follow_up_completed' AND source='USER_REPORTED' AND source_ref=?
        LIMIT 1
        """,
        (actor_id, source_ref),
    ).fetchone()
    if existing:
        memory_event_id = int(existing["id"])
    else:
        memory_event_id = add_timeline_event(
            actor_id,
            "follow_up_completed",
            "Post-visit follow-up completed",
            event_at=now_iso(),
            summary=(
                "Patient explicitly confirmed completion of the non-clinical post-visit follow-up step. "
                "This patient-reported completion does not change provider-recorded clinical evidence."
            ),
            source="USER_REPORTED",
            source_ref=source_ref,
            created_by=actor_id,
        )

    row, provenance = _persist_transition(
        row,
        provenance,
        target_state="COMPLETED",
        reason="Patient explicitly confirmed the post-visit follow-up step was completed after verified provider visit evidence existed.",
        actor_type="user",
        actor_id=actor_id,
        next_safe_action="none",
        required_actor=None,
        transition_provenance={
            "source": "patient_follow_up_confirmation",
            "follow_up_completion_state": "patient_reported",
            "care_outcome_id": outcome_id,
            "follow_up_memory_event_id": memory_event_id,
            "provider_recorded_outcome_preserved": True,
        },
    )
    return {
        "care_journey_id": int(row["id"]),
        "care_journey_state": str(row["state"]),
        "next_safe_action": row["next_safe_action"],
        "care_outcome_id": outcome_id,
        "follow_up_memory_event_id": memory_event_id,
        "follow_up_completion_state": "patient_reported",
        "idempotent": False,
    }
