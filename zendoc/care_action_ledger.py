"""Care Action Graph and Outcome & Accountability Ledger.

This module tracks real-world care actions and outcomes. It does not execute
bookings, orders, payments, clinical decisions, emergency dispatch, or medical
device actions. External execution stays behind explicit human/provider gates.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from .context_engine import verify_context_authorization
from .db import get_db, now_iso


ACTION_STATUSES = {"PROPOSED", "STAGED", "CONFIRMED", "IN_PROGRESS", "COMPLETED", "BLOCKED", "CANCELLED"}
OUTCOME_STATUSES = {"REPORTED", "VERIFIED"}
_ALLOWED = {
    "PROPOSED": {"STAGED", "CANCELLED", "BLOCKED"},
    "STAGED": {"CONFIRMED", "CANCELLED", "BLOCKED"},
    "CONFIRMED": {"IN_PROGRESS", "COMPLETED", "CANCELLED", "BLOCKED"},
    "IN_PROGRESS": {"COMPLETED", "BLOCKED", "CANCELLED"},
    "COMPLETED": set(),
    "BLOCKED": set(),
    "CANCELLED": set(),
}


def ensure_care_action_ledger_schema():
    get_db().executescript(
        """
        CREATE TABLE IF NOT EXISTS care_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_uid TEXT NOT NULL UNIQUE,
            journey_id INTEGER NOT NULL REFERENCES care_journeys(id) ON DELETE CASCADE,
            patient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            action_type TEXT NOT NULL,
            title TEXT NOT NULL,
            rationale TEXT,
            status TEXT NOT NULL DEFAULT 'PROPOSED',
            owner_type TEXT NOT NULL DEFAULT 'patient',
            owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            provider_name TEXT,
            service_ref TEXT,
            estimated_cost REAL,
            currency TEXT NOT NULL DEFAULT 'INR',
            due_at TEXT,
            evidence_json TEXT NOT NULL DEFAULT '{}',
            provenance_json TEXT NOT NULL DEFAULT '{}',
            created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_care_actions_journey ON care_actions(journey_id, id);
        CREATE INDEX IF NOT EXISTS idx_care_actions_patient ON care_actions(patient_id, status, updated_at);

        CREATE TABLE IF NOT EXISTS care_action_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_id INTEGER NOT NULL REFERENCES care_actions(id) ON DELETE CASCADE,
            previous_status TEXT,
            status TEXT NOT NULL,
            event_type TEXT NOT NULL,
            note TEXT,
            actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            provenance_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_care_action_events_action ON care_action_events(action_id, id);

        CREATE TABLE IF NOT EXISTS care_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            outcome_uid TEXT NOT NULL UNIQUE,
            action_id INTEGER NOT NULL REFERENCES care_actions(id) ON DELETE CASCADE,
            journey_id INTEGER NOT NULL REFERENCES care_journeys(id) ON DELETE CASCADE,
            patient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            outcome_type TEXT NOT NULL,
            summary TEXT NOT NULL,
            value_text TEXT,
            numeric_value REAL,
            unit TEXT,
            status TEXT NOT NULL DEFAULT 'REPORTED',
            source_type TEXT NOT NULL,
            source_ref TEXT,
            observed_at TEXT,
            reviewer_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            provenance_json TEXT NOT NULL DEFAULT '{}',
            created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_care_outcomes_action ON care_outcomes(action_id, id);
        CREATE INDEX IF NOT EXISTS idx_care_outcomes_patient ON care_outcomes(patient_id, observed_at, id);
        """
    )


def create_care_action(actor: Any, journey_id: int, data: dict) -> dict:
    ensure_care_action_ledger_schema()
    journey = _authorized_journey(actor, journey_id)
    title = _text(data.get("title"), "title", 200, required=True)
    action_type = _slug(data.get("action_type") or "other", 80)
    status = str(data.get("status") or "PROPOSED").strip().upper()
    if status not in {"PROPOSED", "STAGED"}:
        raise ValueError("New care actions may start only as PROPOSED or STAGED.")
    if status == "STAGED" and not _truthy(data.get("human_confirmation_required", True)):
        raise ValueError("A staged care action must keep an explicit human confirmation gate.")
    estimated_cost = data.get("estimated_cost")
    if estimated_cost in (None, ""):
        estimated_cost = None
    else:
        estimated_cost = float(estimated_cost)
        if estimated_cost < 0:
            raise ValueError("estimated_cost cannot be negative.")
    evidence = data.get("evidence") if isinstance(data.get("evidence"), dict) else {}
    provenance = data.get("provenance") if isinstance(data.get("provenance"), dict) else {}
    now = now_iso()
    uid = f"care_action_{uuid.uuid4().hex}"
    actor_id = _user_id(actor)
    cursor = get_db().execute(
        """
        INSERT INTO care_actions
        (action_uid,journey_id,patient_id,action_type,title,rationale,status,owner_type,owner_id,
         provider_name,service_ref,estimated_cost,currency,due_at,evidence_json,provenance_json,
         created_by,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            uid, int(journey_id), int(journey["patient_id"]), action_type, title,
            _text(data.get("rationale"), "rationale", 1000), status,
            _slug(data.get("owner_type") or "patient", 40),
            int(data["owner_id"]) if data.get("owner_id") else None,
            _text(data.get("provider_name"), "provider_name", 200),
            _text(data.get("service_ref"), "service_ref", 500), estimated_cost,
            str(data.get("currency") or "INR").strip().upper()[:8],
            _text(data.get("due_at"), "due_at", 80), _dump(evidence), _dump(provenance),
            actor_id, now, now,
        ),
    )
    get_db().execute(
        """INSERT INTO care_action_events
        (action_id,previous_status,status,event_type,note,actor_id,provenance_json,created_at)
        VALUES (?,NULL,?,'CREATED',?,?,?,?)""",
        (int(cursor.lastrowid), status, "Care action created for tracking; no external action executed.", actor_id, _dump(provenance), now),
    )
    get_db().commit()
    return get_care_action(actor, int(cursor.lastrowid))


def transition_care_action(actor: Any, action_id: int, target_status: str, *, note=None, provenance=None) -> dict:
    ensure_care_action_ledger_schema()
    action = _authorized_action(actor, action_id)
    current = action["status"]
    target = str(target_status or "").strip().upper()
    if target not in ACTION_STATUSES:
        raise ValueError("Unknown care action status.")
    if target not in _ALLOWED[current]:
        raise ValueError(f"Invalid care action transition: {current} -> {target}.")
    if target == "COMPLETED" and not str(note or "").strip():
        raise ValueError("Completing a care action requires a completion note/evidence reference.")
    now = now_iso()
    p = provenance if isinstance(provenance, dict) else {}
    get_db().execute("UPDATE care_actions SET status=?, updated_at=? WHERE id=?", (target, now, int(action_id)))
    get_db().execute(
        """INSERT INTO care_action_events
        (action_id,previous_status,status,event_type,note,actor_id,provenance_json,created_at)
        VALUES (?,?,?,?,?,?,?,?)""",
        (int(action_id), current, target, "STATUS_CHANGED", _text(note, "note", 1000), _user_id(actor), _dump(p), now),
    )
    get_db().commit()
    return get_care_action(actor, action_id)


def record_care_outcome(actor: Any, action_id: int, data: dict) -> dict:
    ensure_care_action_ledger_schema()
    action = _authorized_action(actor, action_id)
    if action["status"] != "COMPLETED":
        raise ValueError("An outcome can be recorded only after the linked care action is completed.")
    role = str(_value(actor, "role", ""))
    requested = str(data.get("status") or "REPORTED").strip().upper()
    if requested == "VERIFIED" and role not in {"doctor", "hospital", "admin"}:
        raise PermissionError("Only an authorized provider/owner role may mark an outcome VERIFIED.")
    if requested not in OUTCOME_STATUSES:
        raise ValueError("Outcome status must be REPORTED or VERIFIED.")
    source_type = _slug(data.get("source_type") or ("provider" if requested == "VERIFIED" else "patient"), 60)
    now = now_iso()
    outcome_uid = f"care_outcome_{uuid.uuid4().hex}"
    cursor = get_db().execute(
        """
        INSERT INTO care_outcomes
        (outcome_uid,action_id,journey_id,patient_id,outcome_type,summary,value_text,numeric_value,
         unit,status,source_type,source_ref,observed_at,reviewer_id,provenance_json,created_by,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            outcome_uid, int(action_id), int(action["journey_id"]), int(action["patient_id"]),
            _slug(data.get("outcome_type") or "other", 80), _text(data.get("summary"), "summary", 1000, required=True),
            _text(data.get("value_text"), "value_text", 500),
            float(data["numeric_value"]) if data.get("numeric_value") not in (None, "") else None,
            _text(data.get("unit"), "unit", 80), requested, source_type,
            _text(data.get("source_ref"), "source_ref", 500), _text(data.get("observed_at"), "observed_at", 80),
            _user_id(actor) if requested == "VERIFIED" else None,
            _dump(data.get("provenance") if isinstance(data.get("provenance"), dict) else {}),
            _user_id(actor), now, now,
        ),
    )
    get_db().commit()
    return get_care_outcome(actor, int(cursor.lastrowid))


def list_journey_actions(actor: Any, journey_id: int) -> list[dict]:
    ensure_care_action_ledger_schema()
    _authorized_journey(actor, journey_id)
    rows = get_db().execute("SELECT id FROM care_actions WHERE journey_id=? ORDER BY id ASC", (int(journey_id),)).fetchall()
    return [get_care_action(actor, int(r["id"])) for r in rows]


def get_care_action(actor: Any, action_id: int) -> dict:
    ensure_care_action_ledger_schema()
    action = _authorized_action(actor, action_id)
    events = get_db().execute("SELECT * FROM care_action_events WHERE action_id=? ORDER BY id ASC", (int(action_id),)).fetchall()
    outcomes = get_db().execute("SELECT * FROM care_outcomes WHERE action_id=? ORDER BY id ASC", (int(action_id),)).fetchall()
    result = dict(action)
    result["evidence"] = _json(result.pop("evidence_json"))
    result["provenance"] = _json(result.pop("provenance_json"))
    result["events"] = [_serialize_event(x) for x in events]
    result["outcomes"] = [_serialize_outcome(x) for x in outcomes]
    result["external_execution"] = False
    result["notice"] = "Ledger state only. External healthcare execution must be confirmed through a real integrated provider/service."
    return result


def get_care_outcome(actor: Any, outcome_id: int) -> dict:
    ensure_care_action_ledger_schema()
    row = get_db().execute("SELECT * FROM care_outcomes WHERE id=?", (int(outcome_id),)).fetchone()
    if not row:
        raise LookupError("Care outcome not found.")
    verify_context_authorization(actor, int(row["patient_id"]), "care_journey")
    return _serialize_outcome(row)


def _authorized_journey(actor: Any, journey_id: int):
    row = get_db().execute("SELECT * FROM care_journeys WHERE id=?", (int(journey_id),)).fetchone()
    if not row:
        raise LookupError("Care journey not found.")
    verify_context_authorization(actor, int(row["patient_id"]), "care_journey")
    return row


def _authorized_action(actor: Any, action_id: int):
    row = get_db().execute("SELECT * FROM care_actions WHERE id=?", (int(action_id),)).fetchone()
    if not row:
        raise LookupError("Care action not found.")
    verify_context_authorization(actor, int(row["patient_id"]), "care_journey")
    return row


def _serialize_event(row):
    item = dict(row)
    item["provenance"] = _json(item.pop("provenance_json"))
    return item


def _serialize_outcome(row):
    item = dict(row)
    item["provenance"] = _json(item.pop("provenance_json"))
    item["clinical_claim_verified"] = item["status"] == "VERIFIED"
    return item


def _dump(value):
    return json.dumps(value if isinstance(value, dict) else {}, sort_keys=True, separators=(",", ":"))


def _json(value):
    try:
        decoded = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _slug(value, limit):
    text = str(value or "").strip().lower().replace(" ", "_").replace("-", "_\")
    if not text:
        raise ValueError("A non-empty value is required.")
    return text[:limit]


def _text(value, label, limit, required=False):
    if value is None:
        text = ""
    else:
        text = " ".join(str(value).split())
    if required and not text:
        raise ValueError(f"{label} is required.")
    if len(text) > limit:
        raise ValueError(f"{label} must be at most {limit} characters.")
    return text or None


def _truthy(value):
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _user_id(actor: Any) -> int:
    return int(_value(actor, "id", 0) or 0)


def _value(actor: Any, key: str, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    return actor.get(key, default) if isinstance(actor, dict) else default
