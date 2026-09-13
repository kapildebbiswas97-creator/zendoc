"""Patient-authorized Care Action Graph and Outcome Ledger.

This layer tracks accountable care actions and outcomes. It never diagnoses,
prescribes, pays, dispatches emergency care, or controls medical devices.
ZENDOC-internal integrations may synchronize an already-authorized operational
record without implying that an external hospital/partner API was called.
"""
from __future__ import annotations

import json
import uuid

from .care_action_integration_truth import linked_internal_service
from .context_engine import verify_context_authorization
from .db import get_db, now_iso


ALLOWED_TRANSITIONS = {
    "PROPOSED": {"STAGED", "BLOCKED", "CANCELLED"},
    "STAGED": {"CONFIRMED", "BLOCKED", "CANCELLED"},
    "CONFIRMED": {"IN_PROGRESS", "COMPLETED", "BLOCKED", "CANCELLED"},
    "IN_PROGRESS": {"COMPLETED", "BLOCKED", "CANCELLED"},
    "COMPLETED": set(),
    "BLOCKED": set(),
    "CANCELLED": set(),
}

APPOINTMENT_STATUS_TO_ACTION = {
    "requested": "STAGED",
    "confirmed": "CONFIRMED",
    "completed": "COMPLETED",
    "cancelled": "CANCELLED",
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
        CREATE INDEX IF NOT EXISTS idx_care_actions_journey ON care_actions(journey_id,id);
        CREATE INDEX IF NOT EXISTS idx_care_actions_patient ON care_actions(patient_id,status,updated_at);
        CREATE INDEX IF NOT EXISTS idx_care_actions_service_ref ON care_actions(service_ref,patient_id);

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
        CREATE INDEX IF NOT EXISTS idx_care_action_events_action ON care_action_events(action_id,id);

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
        CREATE INDEX IF NOT EXISTS idx_care_outcomes_action ON care_outcomes(action_id,id);
        CREATE INDEX IF NOT EXISTS idx_care_outcomes_patient ON care_outcomes(patient_id,observed_at,id);
        """
    )


def create_action(actor, journey_id, data):
    ensure_care_action_ledger_schema()
    journey = _journey(actor, journey_id)
    status = str(data.get("status") or "PROPOSED").strip().upper()
    if status not in {"PROPOSED", "STAGED"}:
        raise ValueError("New care actions may start only as PROPOSED or STAGED.")
    if status == "STAGED" and str(data.get("human_confirmation_required", True)).lower() in {"0", "false", "no"}:
        raise ValueError("A staged care action must keep an explicit human confirmation gate.")
    cost = data.get("estimated_cost")
    cost = None if cost in (None, "") else float(cost)
    if cost is not None and cost < 0:
        raise ValueError("estimated_cost cannot be negative.")
    now = now_iso()
    uid = f"care_action_{uuid.uuid4().hex}"
    actor_id = _actor_id(actor)
    provenance = data.get("provenance") if isinstance(data.get("provenance"), dict) else {}
    evidence = data.get("evidence") if isinstance(data.get("evidence"), dict) else {}
    cursor = get_db().execute(
        """
        INSERT INTO care_actions
        (action_uid,journey_id,patient_id,action_type,title,rationale,status,owner_type,owner_id,
         provider_name,service_ref,estimated_cost,currency,due_at,evidence_json,provenance_json,
         created_by,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            uid,
            int(journey_id),
            int(journey["patient_id"]),
            _slug(data.get("action_type") or "other", 80),
            _text(data.get("title"), "title", 200, True),
            _text(data.get("rationale"), "rationale", 1000),
            status,
            _slug(data.get("owner_type") or "patient", 40),
            int(data["owner_id"]) if data.get("owner_id") else None,
            _text(data.get("provider_name"), "provider_name", 200),
            _text(data.get("service_ref"), "service_ref", 500),
            cost,
            str(data.get("currency") or "INR").strip().upper()[:8],
            _text(data.get("due_at"), "due_at", 80),
            _dump(evidence),
            _dump(provenance),
            actor_id,
            now,
            now,
        ),
    )
    action_id = int(cursor.lastrowid)
    _event(
        action_id,
        None,
        status,
        "CREATED",
        "Tracking record created; no external healthcare action executed.",
        actor_id,
        provenance,
    )
    get_db().commit()
    return get_action(actor, action_id)


def transition_action(actor, action_id, target_status, note=None, provenance=None):
    ensure_care_action_ledger_schema()
    row = _action(actor, action_id)
    current = row["status"]
    target = str(target_status or "").strip().upper()
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"Invalid care action transition: {current} -> {target}.")
    if target == "COMPLETED" and not str(note or "").strip():
        raise ValueError("Completing a care action requires a completion note/evidence reference.")
    now = now_iso()
    p = provenance if isinstance(provenance, dict) else {}
    get_db().execute("UPDATE care_actions SET status=?,updated_at=? WHERE id=?", (target, now, int(action_id)))
    _event(int(action_id), current, target, "STATUS_CHANGED", _text(note, "note", 1000), _actor_id(actor), p)
    get_db().commit()
    return get_action(actor, action_id)


def sync_registered_appointment_status(actor, appointment_id, target_appointment_status):
    """Synchronize an already-authorized registered-provider appointment."""
    ensure_care_action_ledger_schema()
    db = get_db()
    appointment = db.execute(
        "SELECT id,patient_id,provider_id,status FROM appointments WHERE id=?",
        (int(appointment_id),),
    ).fetchone()
    if not appointment:
        raise LookupError("Linked appointment not found.")
    if not appointment["provider_id"]:
        raise PermissionError("Only a registered ZENDOC provider appointment can synchronize CareLoop execution.")

    actor_id = _actor_id(actor)
    from .security import is_owner

    if actor_id != int(appointment["provider_id"]) and not is_owner(actor):
        raise PermissionError("Only the linked provider or ZENDOC owner can synchronize this appointment action.")

    appointment_status = str(target_appointment_status or "").strip().lower()
    target = APPOINTMENT_STATUS_TO_ACTION.get(appointment_status)
    if not target:
        raise ValueError("Unsupported appointment status for CareLoop synchronization.")

    service_ref = f"zendoc_appointment:{int(appointment_id)}"
    action = db.execute(
        "SELECT * FROM care_actions WHERE service_ref=? AND patient_id=? ORDER BY id DESC LIMIT 1",
        (service_ref, int(appointment["patient_id"])),
    ).fetchone()
    if not action:
        return None

    current = str(action["status"])
    if current == target:
        return dict(action)
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"Linked care action cannot transition {current} -> {target}.")

    provenance = {
        "source": "zendoc_registered_provider_appointment",
        "appointment_id": int(appointment_id),
        "provider_id": int(appointment["provider_id"]),
        "appointment_status": appointment_status,
    }
    note = {
        "CONFIRMED": "Registered ZENDOC provider confirmed the linked appointment.",
        "COMPLETED": "Registered ZENDOC provider marked the linked appointment completed.",
        "CANCELLED": "Linked ZENDOC appointment was cancelled.",
        "STAGED": "Linked ZENDOC appointment request is awaiting provider confirmation.",
    }[target]
    now = now_iso()
    db.execute("UPDATE care_actions SET status=?,updated_at=? WHERE id=?", (target, now, int(action["id"])))
    _event(int(action["id"]), current, target, "INTERNAL_APPOINTMENT_SYNC", note, actor_id, provenance)
    db.commit()
    return db.execute("SELECT * FROM care_actions WHERE id=?", (int(action["id"]),)).fetchone()


def record_outcome(actor, action_id, data):
    ensure_care_action_ledger_schema()
    action = _action(actor, action_id)
    if action["status"] != "COMPLETED":
        raise ValueError("An outcome can be recorded only after the linked care action is completed.")
    status = str(data.get("status") or "REPORTED").strip().upper()
    if status not in {"REPORTED", "VERIFIED"}:
        raise ValueError("Outcome status must be REPORTED or VERIFIED.")
    role = str(_value(actor, "role", "") or "")
    if status == "VERIFIED" and role not in {"doctor", "hospital", "admin"}:
        raise PermissionError("Only an authorized provider/owner role may mark an outcome VERIFIED.")
    now = now_iso()
    provenance = data.get("provenance") if isinstance(data.get("provenance"), dict) else {}
    cursor = get_db().execute(
        """
        INSERT INTO care_outcomes
        (outcome_uid,action_id,journey_id,patient_id,outcome_type,summary,value_text,numeric_value,unit,status,
         source_type,source_ref,observed_at,reviewer_id,provenance_json,created_by,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            f"care_outcome_{uuid.uuid4().hex}",
            int(action_id),
            int(action["journey_id"]),
            int(action["patient_id"]),
            _slug(data.get("outcome_type") or "other", 80),
            _text(data.get("summary"), "summary", 1000, True),
            _text(data.get("value_text"), "value_text", 500),
            float(data["numeric_value"]) if data.get("numeric_value") not in (None, "") else None,
            _text(data.get("unit"), "unit", 80),
            status,
            _slug(data.get("source_type") or ("provider" if status == "VERIFIED" else "patient"), 60),
            _text(data.get("source_ref"), "source_ref", 500),
            _text(data.get("observed_at"), "observed_at", 80),
            _actor_id(actor) if status == "VERIFIED" else None,
            _dump(provenance),
            _actor_id(actor),
            now,
            now,
        ),
    )
    get_db().commit()
    return get_outcome(actor, int(cursor.lastrowid))


def list_actions(actor, journey_id):
    ensure_care_action_ledger_schema()
    _journey(actor, journey_id)
    rows = get_db().execute("SELECT id FROM care_actions WHERE journey_id=? ORDER BY id", (int(journey_id),)).fetchall()
    return [get_action(actor, int(row["id"])) for row in rows]


def get_action(actor, action_id):
    ensure_care_action_ledger_schema()
    row = _action(actor, action_id)
    result = dict(row)
    result["evidence"] = _load(result.pop("evidence_json"))
    result["provenance"] = _load(result.pop("provenance_json"))
    events = get_db().execute("SELECT * FROM care_action_events WHERE action_id=? ORDER BY id", (int(action_id),)).fetchall()
    outcomes = get_db().execute("SELECT * FROM care_outcomes WHERE action_id=? ORDER BY id", (int(action_id),)).fetchall()
    result["events"] = [_serialize_event(item) for item in events]
    result["outcomes"] = [_serialize_outcome(item) for item in outcomes]

    integration = linked_internal_service(result)
    if integration:
        result["integration_status"] = "ACTUALLY_INTEGRATED"
        result["execution_scope"] = integration["execution_scope"]
        result["actual_execution_recorded"] = True
        result["external_execution"] = False
        result["integration_source_type"] = integration["source_type"]
        result["integration_source_id"] = integration["source_id"]
        result["notice"] = integration["notice"]
    else:
        result["integration_status"] = "TRACKING_ONLY"
        result["execution_scope"] = "ledger_only"
        result["actual_execution_recorded"] = False
        result["external_execution"] = False
        result["notice"] = "Ledger state only. External healthcare execution requires a real integrated provider/service and confirmation."
    return result


def get_outcome(actor, outcome_id):
    ensure_care_action_ledger_schema()
    row = get_db().execute("SELECT * FROM care_outcomes WHERE id=?", (int(outcome_id),)).fetchone()
    if not row:
        raise LookupError("Care outcome not found.")
    verify_context_authorization(actor, int(row["patient_id"]), "care_journey")
    return _serialize_outcome(row)


def _linked_registered_appointment(action):
    """Backward-compatible helper retained for callers outside get_action."""
    service_ref = str(action.get("service_ref") or "")
    if not service_ref.startswith("zendoc_appointment:"):
        return None
    try:
        appointment_id = int(service_ref.split(":", 1)[1])
    except (TypeError, ValueError):
        return None
    row = get_db().execute(
        "SELECT id,patient_id,provider_id,status FROM appointments WHERE id=? AND patient_id=?",
        (appointment_id, int(action["patient_id"])),
    ).fetchone()
    return row if row and row["provider_id"] else None


def _journey(actor, journey_id):
    row = get_db().execute("SELECT * FROM care_journeys WHERE id=?", (int(journey_id),)).fetchone()
    if not row:
        raise LookupError("Care journey not found.")
    verify_context_authorization(actor, int(row["patient_id"]), "care_journey")
    return row


def _action(actor, action_id):
    row = get_db().execute("SELECT * FROM care_actions WHERE id=?", (int(action_id),)).fetchone()
    if not row:
        raise LookupError("Care action not found.")
    verify_context_authorization(actor, int(row["patient_id"]), "care_journey")
    return row


def _event(action_id, previous, status, event_type, note, actor_id, provenance):
    get_db().execute(
        """
        INSERT INTO care_action_events
        (action_id,previous_status,status,event_type,note,actor_id,provenance_json,created_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (action_id, previous, status, event_type, note, actor_id, _dump(provenance), now_iso()),
    )


def _serialize_event(row):
    item = dict(row)
    item["provenance"] = _load(item.pop("provenance_json"))
    return item


def _serialize_outcome(row):
    item = dict(row)
    item["provenance"] = _load(item.pop("provenance_json"))
    item["clinical_claim_verified"] = item["status"] == "VERIFIED"
    return item


def _dump(value):
    return json.dumps(value if isinstance(value, dict) else {}, sort_keys=True, separators=(",", ":"))


def _load(value):
    try:
        decoded = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        decoded = {}
    return decoded if isinstance(decoded, dict) else {}


def _slug(value, limit):
    text = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if not text:
        raise ValueError("A non-empty value is required.")
    return text[:limit]


def _text(value, label, limit, required=False):
    text = "" if value is None else " ".join(str(value).split())
    if required and not text:
        raise ValueError(f"{label} is required.")
    if len(text) > limit:
        raise ValueError(f"{label} must be at most {limit} characters.")
    return text or None


def _actor_id(actor):
    return int(_value(actor, "id", 0) or 0)


def _value(actor, key, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    return actor.get(key, default) if isinstance(actor, dict) else default
