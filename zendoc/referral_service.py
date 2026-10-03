"""Consent-bound referral and waiting-list lifecycle integrated with CareLoop.

This is ZENDOC's internal referral coordination record. It never implies that an
external specialist/EHR received a referral unless a verified external adapter
records that evidence separately.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from .care_action_ledger import ALLOWED_TRANSITIONS as CARE_ACTION_TRANSITIONS, ensure_care_action_ledger_schema
from .context_engine import get_active_consent_grant, verify_context_authorization
from .db import get_db, now_iso


REFERRAL_TRANSITIONS = {
    "CREATED": {"PACKET_PREPARED"},
    "PACKET_PREPARED": {"CONSENTED"},
    "CONSENTED": {"SENT"},
    "SENT": {"RECEIVED"},
    "RECEIVED": {"TRIAGED"},
    "TRIAGED": {"ACCEPTED", "REJECTED"},
    "ACCEPTED": {"WAITING_LIST", "SCHEDULED"},
    "WAITING_LIST": {"SCHEDULED"},
    "SCHEDULED": {"CONSULTATION"},
    "CONSULTATION": {"REPORT_RECEIVED"},
    "REPORT_RECEIVED": {"FOLLOW_UP"},
    "FOLLOW_UP": {"RETURNED_TO_PRIMARY"},
    "REJECTED": set(),
    "RETURNED_TO_PRIMARY": set(),
}

DESTINATION_VISIBLE_STATES = {
    "SENT", "RECEIVED", "TRIAGED", "ACCEPTED", "REJECTED", "WAITING_LIST",
    "SCHEDULED", "CONSULTATION", "REPORT_RECEIVED", "FOLLOW_UP", "RETURNED_TO_PRIMARY",
}

DESTINATION_TRANSITIONS = {
    "RECEIVED", "TRIAGED", "ACCEPTED", "REJECTED", "WAITING_LIST", "SCHEDULED",
    "CONSULTATION", "REPORT_RECEIVED", "FOLLOW_UP", "RETURNED_TO_PRIMARY",
}

PRIORITIES = {"routine", "urgent"}

CARE_ACTION_BY_REFERRAL_STATE = {
    "CONSENTED": "STAGED",
    "ACCEPTED": "CONFIRMED",
    "REJECTED": "CANCELLED",
    "CONSULTATION": "IN_PROGRESS",
    "RETURNED_TO_PRIMARY": "COMPLETED",
}


def ensure_referral_schema():
    ensure_care_action_ledger_schema()
    get_db().executescript(
        """
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referral_uid TEXT NOT NULL UNIQUE,
            journey_id INTEGER NOT NULL REFERENCES care_journeys(id) ON DELETE CASCADE,
            care_action_id INTEGER REFERENCES care_actions(id) ON DELETE SET NULL,
            patient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            referring_provider_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            destination_provider_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            reason TEXT NOT NULL,
            specialty TEXT,
            priority TEXT NOT NULL DEFAULT 'routine',
            status TEXT NOT NULL DEFAULT 'CREATED',
            packet_json TEXT NOT NULL DEFAULT '{}',
            provenance_json TEXT NOT NULL DEFAULT '{}',
            waiting_since TEXT,
            scheduled_for TEXT,
            specialist_opinion TEXT,
            outcome TEXT,
            consented_at TEXT,
            sent_at TEXT,
            received_at TEXT,
            triaged_at TEXT,
            accepted_at TEXT,
            rejected_at TEXT,
            consulted_at TEXT,
            report_received_at TEXT,
            follow_up_at TEXT,
            returned_at TEXT,
            created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_referrals_patient ON referrals(patient_id,status,updated_at);
        CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referring_provider_id,status,updated_at);
        CREATE INDEX IF NOT EXISTS idx_referrals_destination ON referrals(destination_provider_id,status,updated_at);
        CREATE INDEX IF NOT EXISTS idx_referrals_journey ON referrals(journey_id,id);

        CREATE TABLE IF NOT EXISTS referral_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referral_id INTEGER NOT NULL REFERENCES referrals(id) ON DELETE CASCADE,
            previous_status TEXT,
            status TEXT NOT NULL,
            event_type TEXT NOT NULL,
            actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            note TEXT,
            provenance_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_referral_events_referral ON referral_events(referral_id,id);
        """
    )


def _value(actor: Any, key: str, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    return actor.get(key, default) if isinstance(actor, dict) else default


def _actor_id(actor: Any) -> int:
    return int(_value(actor, "id", 0) or 0)


def _role(actor: Any) -> str:
    return str(_value(actor, "role", "") or "").strip().lower()


def _clean(value, label, limit, required=False):
    text = "" if value is None else " ".join(str(value).split())
    if required and not text:
        raise ValueError(f"{label} is required.")
    if len(text) > limit:
        raise ValueError(f"{label} must be at most {limit} characters.")
    return text or None


def _json(value):
    try:
        decoded = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        decoded = {}
    return decoded if isinstance(decoded, dict) else {}


def _verified_provider(user_id: int):
    return get_db().execute(
        """
        SELECT u.id,u.role,u.name,u.active,p.id AS provider_profile_id,p.provider_type,
               p.specialty,p.organization,p.verification_status
        FROM users u
        JOIN provider_profiles p ON p.user_id=u.id
        WHERE u.id=? AND u.active=1
        """,
        (int(user_id),),
    ).fetchone()


def _require_verified_clinical_provider(actor: Any):
    if _role(actor) not in {"doctor", "hospital"}:
        raise PermissionError("Only a verified doctor or hospital account may create a formal referral.")
    row = _verified_provider(_actor_id(actor))
    if not row or str(row["verification_status"] or "").lower() != "verified":
        raise PermissionError("Verified provider status is required for formal referrals.")
    return row


def _require_destination(destination_provider_id: int):
    row = _verified_provider(destination_provider_id)
    if not row or str(row["verification_status"] or "").lower() != "verified":
        raise LookupError("Destination specialist/provider must be an active ZENDOC-verified provider.")
    if str(row["role"]) not in {"doctor", "hospital"}:
        raise ValueError("Destination referral provider must be a doctor or hospital.")
    return row


def _validate_record_refs(actor: Any, patient_id: int, record_ids) -> list[int]:
    values = []
    for raw in (record_ids or []):
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("Referral record references must be integer record IDs.") from exc
        if value not in values:
            values.append(value)
    if len(values) > 10:
        raise ValueError("A referral packet may reference at most 10 medical records.")
    if not values:
        return values

    if _actor_id(actor) != int(patient_id):
        grant = get_active_consent_grant(int(patient_id), _actor_id(actor), "referral")
        if not grant or "reports" not in set(grant.get("scopes") or []):
            raise PermissionError("Referral packet record attachments require explicit reports scope.")

    db = get_db()
    for record_id in values:
        row = db.execute(
            "SELECT id FROM medical_records WHERE id=? AND owner_id=?",
            (record_id, int(patient_id)),
        ).fetchone()
        if not row:
            raise LookupError(f"Medical record #{record_id} is not available for this patient.")
    return values


def _can_view(actor: Any, row) -> bool:
    actor_id = _actor_id(actor)
    if not actor_id:
        return False
    if actor_id == int(row["patient_id"]) or actor_id == int(row["referring_provider_id"]):
        return True
    return (
        actor_id == int(row["destination_provider_id"])
        and str(row["status"]) in DESTINATION_VISIBLE_STATES
    )


def _referral_row(referral_id: int):
    row = get_db().execute("SELECT * FROM referrals WHERE id=?", (int(referral_id),)).fetchone()
    if not row:
        raise LookupError("Referral not found.")
    return row


def _serialize(row, actor: Any) -> dict:
    if not _can_view(actor, row):
        raise PermissionError("This referral is outside the actor's authorized referral relationship.")
    result = dict(row)
    result["packet"] = _json(result.pop("packet_json"))
    result["provenance"] = _json(result.pop("provenance_json"))
    events = get_db().execute(
        "SELECT * FROM referral_events WHERE referral_id=? ORDER BY id",
        (int(row["id"]),),
    ).fetchall()
    result["history"] = []
    for event in events:
        item = dict(event)
        item["provenance"] = _json(item.pop("provenance_json"))
        result["history"].append(item)
    result["terminal"] = result["status"] in {"REJECTED", "RETURNED_TO_PRIMARY"}
    result["external_exchange_confirmed"] = False
    result["truth_notice"] = (
        "This status is a ZENDOC internal referral workflow state. It does not prove delivery to an "
        "external EHR/HIE or non-ZENDOC provider unless separate verified integration evidence exists."
    )
    return result


def _event(referral_id: int, previous: str | None, status: str, event_type: str, actor: Any, note=None, provenance=None):
    get_db().execute(
        """
        INSERT INTO referral_events
        (referral_id,previous_status,status,event_type,actor_id,note,provenance_json,created_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            int(referral_id), previous, status, event_type, _actor_id(actor) or None,
            _clean(note, "note", 1000),
            json.dumps(provenance if isinstance(provenance, dict) else {}, sort_keys=True, separators=(",", ":")),
            now_iso(),
        ),
    )


def _create_careloop_action(referral_id: int, *, actor: Any, journey_id: int, patient_id: int, destination, reason: str, priority: str):
    now = now_iso()
    uid = f"care_action_{uuid.uuid4().hex}"
    cursor = get_db().execute(
        """
        INSERT INTO care_actions
        (action_uid,journey_id,patient_id,action_type,title,rationale,status,owner_type,owner_id,
         provider_name,service_ref,estimated_cost,currency,due_at,evidence_json,provenance_json,
         created_by,created_at,updated_at)
        VALUES (?,?,?,?,?,?,'PROPOSED','patient',?,?,?,?, 'INR',NULL,?,?,?, ?,?)
        """,
        (
            uid,
            int(journey_id),
            int(patient_id),
            "referral",
            f"Referral to {destination['organization'] or destination['name']}",
            reason,
            int(patient_id),
            destination["organization"] or destination["name"],
            f"zendoc_referral:{int(referral_id)}",
            None,
            json.dumps({"source_type": "zendoc_referral", "priority": priority}, sort_keys=True, separators=(",", ":")),
            json.dumps({"source": "zendoc_referral_os", "referral_id": int(referral_id)}, sort_keys=True, separators=(",", ":")),
            _actor_id(actor),
            now,
            now,
        ),
    )
    action_id = int(cursor.lastrowid)
    get_db().execute(
        """
        INSERT INTO care_action_events
        (action_id,previous_status,status,event_type,note,actor_id,provenance_json,created_at)
        VALUES (?,NULL,'PROPOSED','REFERRAL_CREATED',?,?,?,?)
        """,
        (
            action_id,
            "Formal referral created; patient consent is still required before sending.",
            _actor_id(actor),
            json.dumps({"source": "zendoc_referral_os", "referral_id": int(referral_id)}, sort_keys=True, separators=(",", ":")),
            now,
        ),
    )
    return action_id


def _sync_careloop_action(referral_row, referral_status: str, actor: Any, note=None):
    target = CARE_ACTION_BY_REFERRAL_STATE.get(referral_status)
    action_id = referral_row["care_action_id"]
    if not target or not action_id:
        return
    row = get_db().execute("SELECT status FROM care_actions WHERE id=?", (int(action_id),)).fetchone()
    if not row:
        return
    current = str(row["status"])
    if current == target:
        return
    if target not in CARE_ACTION_TRANSITIONS.get(current, set()):
        raise ValueError(f"Referral-linked CareLoop action cannot transition {current} -> {target}.")
    stamp = now_iso()
    get_db().execute(
        "UPDATE care_actions SET status=?,updated_at=? WHERE id=?",
        (target, stamp, int(action_id)),
    )
    get_db().execute(
        """
        INSERT INTO care_action_events
        (action_id,previous_status,status,event_type,note,actor_id,provenance_json,created_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            int(action_id), current, target, "REFERRAL_SYNC",
            _clean(note, "note", 1000) or f"Referral lifecycle advanced to {referral_status}.",
            _actor_id(actor),
            json.dumps({"source": "zendoc_referral_os", "referral_id": int(referral_row["id"]), "referral_status": referral_status}, sort_keys=True, separators=(",", ":")),
            stamp,
        ),
    )


def create_referral(
    actor: Any,
    *,
    patient_id: int,
    destination_provider_id: int,
    journey_id: int,
    reason: str,
    specialty: str | None = None,
    priority: str = "routine",
    packet_summary: str | None = None,
    record_ids=None,
    provenance: dict | None = None,
) -> dict:
    ensure_referral_schema()
    referrer = _require_verified_clinical_provider(actor)
    patient_id = int(patient_id)
    destination_provider_id = int(destination_provider_id)
    if destination_provider_id == _actor_id(actor):
        raise ValueError("Referring and destination providers must be different.")
    verify_context_authorization(actor, patient_id, "referral")
    patient = get_db().execute("SELECT id,active FROM users WHERE id=? AND role='patient'", (patient_id,)).fetchone()
    if not patient or not bool(patient["active"]):
        raise LookupError("Referral patient must be an active patient account.")
    journey = get_db().execute("SELECT id,patient_id FROM care_journeys WHERE id=?", (int(journey_id),)).fetchone()
    if not journey or int(journey["patient_id"]) != patient_id:
        raise LookupError("Referral must link to this patient's existing CareLoop journey.")
    destination = _require_destination(destination_provider_id)

    priority = str(priority or "routine").strip().lower()
    if priority not in PRIORITIES:
        raise ValueError("Referral priority must be routine or urgent; emergency care must use the emergency pathway.")
    reason = _clean(reason, "reason", 1000, True)
    record_refs = _validate_record_refs(actor, patient_id, record_ids)
    now = now_iso()
    packet = {
        "summary": _clean(packet_summary, "packet_summary", 2000),
        "record_ids": record_refs,
        "attachment_count": len(record_refs),
        "prepared": False,
        "patient_consented": False,
    }
    prov = {
        "source": "zendoc_referral_os",
        "referring_provider_id": _actor_id(actor),
        **(provenance if isinstance(provenance, dict) else {}),
    }
    cursor = get_db().execute(
        """
        INSERT INTO referrals
        (referral_uid,journey_id,patient_id,referring_provider_id,destination_provider_id,
         reason,specialty,priority,status,packet_json,provenance_json,created_by,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?, 'CREATED',?,?,?,?,?)
        """,
        (
            f"referral_{uuid.uuid4().hex}",
            int(journey_id),
            patient_id,
            _actor_id(actor),
            destination_provider_id,
            reason,
            _clean(specialty or destination["specialty"], "specialty", 160),
            priority,
            json.dumps(packet, sort_keys=True, separators=(",", ":")),
            json.dumps(prov, sort_keys=True, separators=(",", ":")),
            _actor_id(actor),
            now,
            now,
        ),
    )
    referral_id = int(cursor.lastrowid)
    action_id = _create_careloop_action(
        referral_id,
        actor=actor,
        journey_id=int(journey_id),
        patient_id=patient_id,
        destination=destination,
        reason=reason,
        priority=priority,
    )
    get_db().execute("UPDATE referrals SET care_action_id=? WHERE id=?", (action_id, referral_id))
    _event(referral_id, None, "CREATED", "CREATED", actor, "Formal internal referral record created.", prov)
    get_db().commit()
    return get_referral(actor, referral_id)


def get_referral(actor: Any, referral_id: int) -> dict:
    ensure_referral_schema()
    return _serialize(_referral_row(referral_id), actor)


def list_referrals(actor: Any, *, patient_id: int | None = None, limit: int = 50) -> list[dict]:
    ensure_referral_schema()
    actor_id = _actor_id(actor)
    role = _role(actor)
    if not actor_id or role not in {"patient", "doctor", "hospital"}:
        raise PermissionError("Referral access requires a patient, doctor or hospital account.")
    limit = max(1, min(int(limit or 50), 100))
    db = get_db()
    if role == "patient":
        target = int(patient_id or actor_id)
        if target != actor_id:
            raise PermissionError("Patients may list only their own referrals.")
        rows = db.execute(
            "SELECT * FROM referrals WHERE patient_id=? ORDER BY updated_at DESC LIMIT ?",
            (target, limit),
        ).fetchall()
    else:
        if patient_id not in (None, ""):
            target = int(patient_id)
            verify_context_authorization(actor, target, "referral")
            rows = db.execute(
                """
                SELECT * FROM referrals
                WHERE patient_id=? AND (referring_provider_id=? OR destination_provider_id=?)
                ORDER BY updated_at DESC LIMIT ?
                """,
                (target, actor_id, actor_id, limit),
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT * FROM referrals
                WHERE referring_provider_id=?
                   OR (destination_provider_id=? AND status IN ('SENT','RECEIVED','TRIAGED','ACCEPTED','REJECTED','WAITING_LIST','SCHEDULED','CONSULTATION','REPORT_RECEIVED','FOLLOW_UP','RETURNED_TO_PRIMARY'))
                ORDER BY updated_at DESC LIMIT ?
                """,
                (actor_id, actor_id, limit),
            ).fetchall()
    return [_serialize(row, actor) for row in rows]


def transition_referral(
    actor: Any,
    referral_id: int,
    target_status: str,
    *,
    note: str | None = None,
    scheduled_for: str | None = None,
    specialist_opinion: str | None = None,
    outcome: str | None = None,
    provenance: dict | None = None,
) -> dict:
    ensure_referral_schema()
    row = _referral_row(referral_id)
    current = str(row["status"])
    target = str(target_status or "").strip().upper()
    if target not in REFERRAL_TRANSITIONS.get(current, set()):
        raise ValueError(f"Invalid referral transition: {current} -> {target}.")

    actor_id = _actor_id(actor)
    if not actor_id:
        raise PermissionError("Authentication required.")
    if target == "CONSENTED":
        if actor_id != int(row["patient_id"]) or _role(actor) != "patient":
            raise PermissionError("Only the patient can consent to sending this referral.")
    elif target in {"PACKET_PREPARED", "SENT"}:
        if actor_id != int(row["referring_provider_id"]):
            raise PermissionError("Only the referring provider may prepare/send this referral.")
    elif target in DESTINATION_TRANSITIONS:
        if actor_id != int(row["destination_provider_id"]):
            raise PermissionError("Only the destination provider may advance this specialist referral state.")

    if target in {"TRIAGED", "REJECTED"} and not _clean(note, "note", 1000):
        raise ValueError(f"{target} requires a note.")
    if target == "SCHEDULED" and not _clean(scheduled_for, "scheduled_for", 80):
        raise ValueError("SCHEDULED requires scheduled_for.")
    if target == "REPORT_RECEIVED" and not (_clean(specialist_opinion, "specialist_opinion", 4000) or _clean(note, "note", 1000)):
        raise ValueError("REPORT_RECEIVED requires a specialist opinion or report note.")
    if target == "RETURNED_TO_PRIMARY" and not _clean(outcome, "outcome", 4000):
        raise ValueError("RETURNED_TO_PRIMARY requires an outcome summary.")

    now = now_iso()
    packet = _json(row["packet_json"])
    updates = {"updated_at": now}
    if target == "PACKET_PREPARED":
        packet["prepared"] = True
        updates["packet_json"] = json.dumps(packet, sort_keys=True, separators=(",", ":"))
    elif target == "CONSENTED":
        packet["patient_consented"] = True
        updates["packet_json"] = json.dumps(packet, sort_keys=True, separators=(",", ":"))
        updates["consented_at"] = now
    elif target == "SENT":
        updates["sent_at"] = now
    elif target == "RECEIVED":
        updates["received_at"] = now
    elif target == "TRIAGED":
        updates["triaged_at"] = now
    elif target == "ACCEPTED":
        updates["accepted_at"] = now
    elif target == "REJECTED":
        updates["rejected_at"] = now
    elif target == "WAITING_LIST":
        updates["waiting_since"] = now
    elif target == "SCHEDULED":
        updates["scheduled_for"] = _clean(scheduled_for, "scheduled_for", 80, True)
    elif target == "CONSULTATION":
        updates["consulted_at"] = now
    elif target == "REPORT_RECEIVED":
        updates["report_received_at"] = now
        updates["specialist_opinion"] = _clean(specialist_opinion or note, "specialist_opinion", 4000, True)
    elif target == "FOLLOW_UP":
        updates["follow_up_at"] = now
    elif target == "RETURNED_TO_PRIMARY":
        updates["returned_at"] = now
        updates["outcome"] = _clean(outcome, "outcome", 4000, True)

    assignments = ["status=?"]
    values = [target]
    for key, value in updates.items():
        assignments.append(f"{key}=?")
        values.append(value)
    values.append(int(referral_id))
    get_db().execute(
        f"UPDATE referrals SET {','.join(assignments)} WHERE id=?",
        tuple(values),
    )
    refreshed = _referral_row(referral_id)
    _sync_careloop_action(refreshed, target, actor, note=note or outcome)
    _event(
        int(referral_id),
        current,
        target,
        "STATUS_CHANGED",
        actor,
        note=note or outcome,
        provenance=provenance,
    )
    get_db().commit()
    return get_referral(actor, referral_id)



def referral_creation_options(actor: Any) -> dict:
    """Return only patients who explicitly granted referral coordination plus verified destinations."""
    ensure_referral_schema()
    _require_verified_clinical_provider(actor)
    actor_id = _actor_id(actor)
    now = now_iso()
    db = get_db()
    grants = db.execute(
        """
        SELECT cg.subject_id,cg.scopes_json,u.name,u.email
        FROM consent_grants cg
        JOIN users u ON u.id=cg.subject_id
        WHERE cg.grantee_id=? AND cg.purpose='referral' AND cg.status='active'
          AND cg.revoked_at IS NULL AND (cg.expires_at IS NULL OR cg.expires_at>?)
          AND u.role='patient' AND u.active=1
        ORDER BY u.name,u.id
        """,
        (actor_id, now),
    ).fetchall()
    patients = []
    for grant in grants:
        try:
            scopes = set(json.loads(grant["scopes_json"] or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            scopes = set()
        if "timeline" not in scopes:
            continue
        journeys = db.execute(
            """
            SELECT id,state,status,updated_at
            FROM care_journeys
            WHERE patient_id=? AND status='active'
            ORDER BY updated_at DESC,id DESC
            LIMIT 20
            """,
            (int(grant["subject_id"]),),
        ).fetchall()
        patients.append({
            "id": int(grant["subject_id"]),
            "name": grant["name"],
            "email": grant["email"],
            "scopes": sorted(scopes),
            "can_attach_reports": "reports" in scopes,
            "journeys": [dict(item) for item in journeys],
        })

    destinations = db.execute(
        """
        SELECT u.id,u.name,p.specialty,p.organization,p.provider_type,p.city,p.state
        FROM users u
        JOIN provider_profiles p ON p.user_id=u.id
        WHERE u.active=1 AND u.role IN ('doctor','hospital')
          AND p.verification_status='verified' AND u.id<>?
        ORDER BY COALESCE(p.specialty,''),COALESCE(p.organization,''),u.name
        LIMIT 250
        """,
        (actor_id,),
    ).fetchall()
    return {
        "patients": patients,
        "destinations": [dict(item) for item in destinations],
        "truth_notice": (
            "Only patients with an active referral-purpose consent grant are offered. "
            "Record references require the separate reports scope."
        ),
    }


def get_referral_record(actor: Any, referral_id: int, record_id: int) -> dict:
    """Authorize one referral-scoped record without granting general Health Memory access."""
    referral = get_referral(actor, referral_id)
    record_id = int(record_id)
    allowed_refs = {int(item) for item in referral.get("packet", {}).get("record_ids", [])}
    if record_id not in allowed_refs:
        raise PermissionError("This record is not part of the consented referral packet.")
    if referral["status"] in {"CREATED", "PACKET_PREPARED"} and _actor_id(actor) == int(referral["destination_provider_id"]):
        raise PermissionError("Destination access begins only after patient consent and referral send.")
    row = get_db().execute(
        "SELECT * FROM medical_records WHERE id=? AND owner_id=?",
        (record_id, int(referral["patient_id"])),
    ).fetchone()
    if not row:
        raise LookupError("Referral record not found.")
    result = dict(row)
    result["access_scope"] = "referral_packet_only"
    result["referral_id"] = int(referral_id)
    return result



def referral_summary(actor: Any) -> dict:
    referrals = list_referrals(actor, limit=100)
    counts = {}
    for item in referrals:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return {
        "status": "OK",
        "total": len(referrals),
        "by_status": counts,
        "items": [
            {
                "id": item["id"],
                "referral_uid": item["referral_uid"],
                "status": item["status"],
                "priority": item["priority"],
                "specialty": item["specialty"],
                "scheduled_for": item["scheduled_for"],
                "waiting_since": item["waiting_since"],
                "journey_id": item["journey_id"],
            }
            for item in referrals
        ],
        "truth_notice": "Referral states reflect ZENDOC workflow evidence only; no external delivery or appointment is inferred.",
    }
