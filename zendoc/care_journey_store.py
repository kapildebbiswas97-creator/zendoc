"""Durable persistence adapter for the pure Care Journey coordinator."""
from __future__ import annotations

import json
import uuid
from typing import Any

from .care_journey import CareJourney, JourneyEvent, start_journey, transition_journey
from .context_engine import verify_context_authorization
from .db import get_db, now_iso


def create_persisted_journey(
    actor: Any,
    *,
    patient_id: int | None = None,
    provenance: dict | None = None,
) -> dict:
    actor_id = _user_id(actor)
    if not actor_id:
        raise PermissionError("Authentication required.")
    target = int(patient_id or actor_id)
    verify_context_authorization(actor, target, "care_journey")
    journey = start_journey(
        patient_id=target,
        journey_id=f"journey_{uuid.uuid4().hex[:20]}",
        provenance=provenance or {},
    )
    db = get_db()
    now = now_iso()
    cursor = db.execute(
        """
        INSERT INTO care_journeys
        (journey_uid,patient_id,created_by,state,next_safe_action,blocked_reason,required_actor,
         required_consent,provenance_json,status,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,'active',?,?)
        """,
        (
            journey.journey_id,
            journey.patient_id,
            actor_id,
            journey.state,
            journey.next_safe_action,
            journey.blocked_reason,
            journey.required_actor,
            journey.required_consent,
            json.dumps(journey.provenance, sort_keys=True, separators=(",", ":")),
            now,
            now,
        ),
    )
    db.commit()
    return get_persisted_journey(cursor.lastrowid, actor)


def get_persisted_journey(journey_id: int, actor: Any) -> dict:
    row = get_db().execute("SELECT * FROM care_journeys WHERE id=?", (int(journey_id),)).fetchone()
    if not row:
        raise LookupError(f"Care journey #{journey_id} not found.")
    verify_context_authorization(actor, row["patient_id"], "care_journey")
    events = get_db().execute(
        "SELECT * FROM care_journey_events WHERE journey_id=? ORDER BY id ASC",
        (int(journey_id),),
    ).fetchall()
    result = dict(row)
    result["provenance"] = _json(result.pop("provenance_json"))
    result["history"] = [
        {
            **dict(event),
            "provenance": _json(event["provenance_json"]),
        }
        for event in events
    ]
    for event in result["history"]:
        event.pop("provenance_json", None)
    result["terminal"] = result["status"] in {"completed", "blocked"}
    return result


def advance_persisted_journey(
    actor: Any,
    journey_id: int,
    *,
    target_state: str,
    reason: str,
    actor_type: str = "user",
    next_safe_action: str | None = None,
    required_actor: str | None = None,
    required_consent: str | None = None,
    blocked_reason: str | None = None,
    provenance: dict | None = None,
) -> dict:
    current = get_persisted_journey(journey_id, actor)
    journey = _to_care_journey(current)
    advanced = transition_journey(
        journey,
        target_state=target_state,
        reason=reason,
        actor_type=actor_type,
        next_safe_action=next_safe_action,
        required_actor=required_actor,
        required_consent=required_consent,
        blocked_reason=blocked_reason,
        provenance=provenance,
    )
    event = advanced.history[-1]
    db = get_db()
    now = now_iso()
    status = "completed" if advanced.state == "COMPLETED" else "blocked" if advanced.state == "BLOCKED" else "active"
    db.execute(
        """
        UPDATE care_journeys
        SET state=?,next_safe_action=?,blocked_reason=?,required_actor=?,required_consent=?,
            provenance_json=?,status=?,updated_at=?
        WHERE id=?
        """,
        (
            advanced.state,
            advanced.next_safe_action,
            advanced.blocked_reason,
            advanced.required_actor,
            advanced.required_consent,
            json.dumps(advanced.provenance, sort_keys=True, separators=(",", ":")),
            status,
            now,
            int(journey_id),
        ),
    )
    db.execute(
        """
        INSERT INTO care_journey_events
        (journey_id,previous_state,state,reason,actor_type,actor_id,provenance_json,created_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            int(journey_id),
            event.previous_state,
            event.state,
            event.reason,
            event.actor_type,
            _user_id(actor) or None,
            json.dumps(event.provenance, sort_keys=True, separators=(",", ":")),
            event.occurred_at,
        ),
    )
    db.commit()
    return get_persisted_journey(journey_id, actor)


def list_patient_journeys(actor: Any, *, patient_id: int | None = None, limit: int = 25) -> list[dict]:
    actor_id = _user_id(actor)
    target = int(patient_id or actor_id)
    verify_context_authorization(actor, target, "care_journey")
    limit = max(1, min(int(limit or 25), 100))
    rows = get_db().execute(
        "SELECT id FROM care_journeys WHERE patient_id=? ORDER BY updated_at DESC LIMIT ?",
        (target, limit),
    ).fetchall()
    return [get_persisted_journey(row["id"], actor) for row in rows]


def _to_care_journey(data: dict) -> CareJourney:
    events = tuple(
        JourneyEvent(
            previous_state=event["previous_state"],
            state=event["state"],
            reason=event["reason"],
            actor_type=event["actor_type"],
            provenance=dict(event.get("provenance") or {}),
            occurred_at=event["created_at"],
        )
        for event in data.get("history", [])
    )
    return CareJourney(
        journey_id=data["journey_uid"],
        patient_id=int(data["patient_id"]),
        state=data["state"],
        next_safe_action=data["next_safe_action"],
        blocked_reason=data.get("blocked_reason"),
        required_actor=data.get("required_actor"),
        required_consent=data.get("required_consent"),
        provenance=dict(data.get("provenance") or {}),
        history=events,
    )


def _json(value: Any) -> dict:
    try:
        decoded = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _user_id(actor: Any) -> int:
    if actor is None:
        return 0
    if isinstance(actor, dict):
        return int(actor.get("id") or 0)
    try:
        return int(actor["id"])
    except Exception:
        return 0
