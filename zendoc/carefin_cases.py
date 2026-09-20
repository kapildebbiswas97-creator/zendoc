"""Durable, truth-preserving CareFin benefit/insurance case tracking."""
from __future__ import annotations

import hashlib
import hmac
import json
import os

from .benefit_sources import get_source
from .carefin_engine import (
    APPROVED,
    AUTHORITATIVE_EVIDENCE_TYPES,
    CONFIRMED,
    DISCOVERED,
    EVIDENCE_RECEIVED,
    PAID,
    POTENTIALLY_ELIGIBLE,
    VERIFICATION_REQUIRED,
    transition_coverage_state,
)
from .db import get_db, now_iso
from .security import is_owner


USER_EVIDENCE_TYPES = {
    "USER_DOCUMENT_REFERENCE",
    "POLICY_REFERENCE",
    "BENEFICIARY_REFERENCE",
    "APPLICATION_REFERENCE",
    "HOSPITAL_ESTIMATE_REFERENCE",
    "OTHER_SUPPORTING_REFERENCE",
}


def ensure_carefin_case_schema():
    get_db().executescript(
        """
        CREATE TABLE IF NOT EXISTS carefin_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source_id TEXT NOT NULL,
            source_name TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'DISCOVERED',
            user_note TEXT,
            latest_evidence_type TEXT,
            latest_evidence_reference TEXT,
            authoritative_confirmation INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_carefin_cases_user
            ON carefin_cases(user_id,updated_at,id);
        CREATE INDEX IF NOT EXISTS idx_carefin_cases_source
            ON carefin_cases(source_id,state,updated_at);

        CREATE TABLE IF NOT EXISTS carefin_case_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL REFERENCES carefin_cases(id) ON DELETE CASCADE,
            actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            event_type TEXT NOT NULL,
            previous_state TEXT,
            state TEXT NOT NULL,
            evidence_type TEXT,
            evidence_reference TEXT,
            note TEXT,
            authoritative_confirmation INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_carefin_case_events_case
            ON carefin_case_events(case_id,created_at,id);

        CREATE TABLE IF NOT EXISTS carefin_partner_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_event_id TEXT NOT NULL UNIQUE,
            case_id INTEGER NOT NULL REFERENCES carefin_cases(id) ON DELETE CASCADE,
            partner_name TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_carefin_partner_events_case
            ON carefin_partner_events(case_id,created_at,id);
        """
    )


def _uid(actor) -> int:
    if actor is None:
        raise PermissionError("Authentication required.")
    if hasattr(actor, "keys") and "id" in actor.keys():
        return int(actor["id"])
    return int(actor.get("id") or 0)


def _clean(value, limit: int):
    return " ".join(str(value or "").strip().split())[:limit] or None


def _event(case_id, actor, event_type, *, previous_state, state, evidence_type=None,
           evidence_reference=None, note=None, authoritative_confirmation=False):
    get_db().execute(
        """
        INSERT INTO carefin_case_events
        (case_id,actor_id,event_type,previous_state,state,evidence_type,evidence_reference,
         note,authoritative_confirmation,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            int(case_id),
            _uid(actor) if actor is not None else None,
            str(event_type)[:80],
            previous_state,
            state,
            evidence_type,
            evidence_reference,
            _clean(note, 1200),
            1 if authoritative_confirmation else 0,
            now_iso(),
        ),
    )


def create_carefin_case(actor, source_id: str, *, note=None, initial_state=DISCOVERED) -> dict:
    ensure_carefin_case_schema()
    source = get_source(str(source_id or "").strip())
    if not source:
        raise LookupError("Unknown CareFin support source.")
    state = str(initial_state or DISCOVERED).strip().upper()
    if state not in {DISCOVERED, POTENTIALLY_ELIGIBLE}:
        state = DISCOVERED
    now = now_iso()
    cursor = get_db().execute(
        """
        INSERT INTO carefin_cases
        (user_id,source_id,source_name,state,user_note,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (_uid(actor), source["source_id"], source["name"], state, _clean(note, 1200), now, now),
    )
    case_id = int(cursor.lastrowid)
    _event(case_id, actor, "created", previous_state=None, state=state, note=note)
    get_db().commit()
    return get_carefin_case(actor, case_id)


def _case_row(case_id: int):
    row = get_db().execute("SELECT * FROM carefin_cases WHERE id=?", (int(case_id),)).fetchone()
    if not row:
        raise LookupError("CareFin case not found.")
    return dict(row)


def get_carefin_case(actor, case_id: int) -> dict:
    ensure_carefin_case_schema()
    item = _case_row(case_id)
    if not is_owner(actor) and int(item["user_id"]) != _uid(actor):
        raise PermissionError("You cannot access this CareFin case.")
    events = get_db().execute(
        """
        SELECT e.*,u.name actor_name
        FROM carefin_case_events e
        LEFT JOIN users u ON u.id=e.actor_id
        WHERE e.case_id=?
        ORDER BY e.created_at ASC,e.id ASC
        """,
        (int(case_id),),
    ).fetchall()
    item["events"] = [dict(row) for row in events]
    item["truth_notice"] = (
        "A ZENDOC CareFin case tracks discovery and evidence. CONFIRMED, APPROVED and PAID "
        "require an authoritative insurer, government, employer, trust, CSR or hospital response."
    )
    return item


def list_carefin_cases(actor, *, limit=100) -> list[dict]:
    ensure_carefin_case_schema()
    limit = max(1, min(int(limit or 100), 500))
    if is_owner(actor):
        rows = get_db().execute(
            """
            SELECT c.*,u.name user_name,u.email user_email
            FROM carefin_cases c JOIN users u ON u.id=c.user_id
            ORDER BY c.updated_at DESC,c.id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    else:
        rows = get_db().execute(
            """
            SELECT c.*,u.name user_name,u.email user_email
            FROM carefin_cases c JOIN users u ON u.id=c.user_id
            WHERE c.user_id=?
            ORDER BY c.updated_at DESC,c.id DESC LIMIT ?
            """,
            (_uid(actor), limit),
        ).fetchall()
    return [dict(row) for row in rows]


def submit_case_evidence(actor, case_id: int, *, evidence_type, evidence_reference, note=None) -> dict:
    ensure_carefin_case_schema()
    item = get_carefin_case(actor, case_id)
    if is_owner(actor) and int(item["user_id"]) != _uid(actor):
        # Owners may review cases but user-supplied evidence should stay attributable
        # to the case owner. Owner authoritative transitions use the dedicated method.
        raise PermissionError("Use owner review to record authoritative evidence.")
    evidence = str(evidence_type or "OTHER_SUPPORTING_REFERENCE").strip().upper()
    if evidence not in USER_EVIDENCE_TYPES:
        raise ValueError("Unsupported user evidence type.")
    reference = _clean(evidence_reference, 300)
    if not reference:
        raise ValueError("Enter a non-secret evidence or application reference.")
    current = str(item["state"])
    target = current
    if current in {DISCOVERED, POTENTIALLY_ELIGIBLE}:
        transition = transition_coverage_state(
            source_id=item["source_id"],
            current_state=current,
            target_state=EVIDENCE_RECEIVED,
            evidence_type=evidence,
            evidence_reference=reference,
        )
        target = transition["state"]
    elif current not in {EVIDENCE_RECEIVED, VERIFICATION_REQUIRED}:
        raise ValueError("This CareFin case no longer accepts user evidence updates.")

    now = now_iso()
    get_db().execute(
        """
        UPDATE carefin_cases
        SET state=?,latest_evidence_type=?,latest_evidence_reference=?,
            user_note=COALESCE(?,user_note),updated_at=?
        WHERE id=?
        """,
        (target, evidence, reference, _clean(note, 1200), now, int(case_id)),
    )
    _event(
        case_id, actor, "evidence_submitted", previous_state=current, state=target,
        evidence_type=evidence, evidence_reference=reference, note=note,
    )
    get_db().commit()
    return get_carefin_case(actor, case_id)


def request_case_verification(actor, case_id: int) -> dict:
    ensure_carefin_case_schema()
    item = get_carefin_case(actor, case_id)
    if is_owner(actor) and int(item["user_id"]) != _uid(actor):
        raise PermissionError("The case owner must request verification.")
    current = str(item["state"])
    if current != EVIDENCE_RECEIVED:
        raise ValueError("Submit supporting evidence before requesting verification.")
    transition = transition_coverage_state(
        source_id=item["source_id"],
        current_state=current,
        target_state=VERIFICATION_REQUIRED,
        evidence_type=item.get("latest_evidence_type"),
        evidence_reference=item.get("latest_evidence_reference"),
    )
    now = now_iso()
    get_db().execute(
        "UPDATE carefin_cases SET state=?,updated_at=? WHERE id=?",
        (transition["state"], now, int(case_id)),
    )
    _event(
        case_id, actor, "verification_requested", previous_state=current,
        state=transition["state"],
        evidence_type=item.get("latest_evidence_type"),
        evidence_reference=item.get("latest_evidence_reference"),
    )
    get_db().commit()
    return get_carefin_case(actor, case_id)


def owner_transition_case(actor, case_id: int, *, target_state, evidence_type=None,
                          evidence_reference=None, note=None) -> dict:
    ensure_carefin_case_schema()
    if not is_owner(actor):
        raise PermissionError("Only the ZENDOC owner can record authoritative CareFin responses.")
    item = get_carefin_case(actor, case_id)
    current = str(item["state"])
    target = str(target_state or "").strip().upper()
    authoritative = target in {CONFIRMED, APPROVED, PAID}
    transition = transition_coverage_state(
        source_id=item["source_id"],
        current_state=current,
        target_state=target,
        evidence_type=evidence_type,
        evidence_reference=evidence_reference,
        authoritative_confirmation=authoritative,
    )
    now = now_iso()
    get_db().execute(
        """
        UPDATE carefin_cases
        SET state=?,latest_evidence_type=COALESCE(?,latest_evidence_type),
            latest_evidence_reference=COALESCE(?,latest_evidence_reference),
            authoritative_confirmation=?,updated_at=?
        WHERE id=?
        """,
        (
            transition["state"],
            transition.get("evidence_type"),
            transition.get("evidence_reference"),
            1 if authoritative else 0,
            now,
            int(case_id),
        ),
    )
    _event(
        case_id, actor, "owner_state_transition", previous_state=current,
        state=transition["state"], evidence_type=transition.get("evidence_type"),
        evidence_reference=transition.get("evidence_reference"), note=note,
        authoritative_confirmation=authoritative,
    )
    get_db().commit()
    return get_carefin_case(actor, case_id)


def carefin_case_options() -> dict:
    return {
        "user_evidence_types": sorted(USER_EVIDENCE_TYPES),
        "authoritative_evidence_types": sorted(AUTHORITATIVE_EVIDENCE_TYPES),
        "authoritative_states": [CONFIRMED, APPROVED, PAID],
    }



def carefin_partner_status() -> dict:
    partner=str(os.environ.get("ZENDOC_CAREFIN_PARTNER_NAME") or "none").strip()
    secret=str(os.environ.get("ZENDOC_CAREFIN_WEBHOOK_SECRET") or "")
    verified=str(os.environ.get("ZENDOC_CAREFIN_PARTNER_VERIFIED") or "").strip().lower() in {"1","true","yes","on"}
    configured=partner.lower() not in {"","none"} and bool(secret)
    return {
        "partner":partner,
        "configured":configured,
        "operator_verified":bool(configured and verified),
        "status":"working" if configured and verified else "configured_unverified" if configured else "integration_required",
        "truth_notice":(
            "Signed CareFin partner callbacks are configured and operator-verified; each state change still requires a valid signed event."
            if configured and verified else
            "CareFin partner callback credentials exist but are not operator-verified."
            if configured else
            "No insurer/government/CSR CareFin webhook partner is configured. Owner evidence review remains available."
        ),
    }


def apply_carefin_partner_response(payload: dict, raw_body: bytes, signature: str) -> dict:
    ensure_carefin_case_schema()
    status=carefin_partner_status()
    secret=str(os.environ.get("ZENDOC_CAREFIN_WEBHOOK_SECRET") or "")
    if not status["configured"] or not secret:
        raise PermissionError("CareFin partner webhook is not configured.")
    supplied=str(signature or "").strip()
    if supplied.lower().startswith("sha256="):
        supplied=supplied.split("=",1)[1]
    expected=hmac.new(secret.encode("utf-8"),raw_body,hashlib.sha256).hexdigest()
    if not supplied or not hmac.compare_digest(supplied,expected):
        raise PermissionError("Invalid CareFin partner webhook signature.")

    event_id=str(payload.get("event_id") or "").strip()[:200]
    if not event_id:
        raise ValueError("Partner event_id is required for idempotency.")
    existing=get_db().execute(
        "SELECT case_id FROM carefin_partner_events WHERE provider_event_id=?",
        (event_id,),
    ).fetchone()
    if existing:
        return _case_row(int(existing["case_id"]))

    case_id=int(payload.get("case_id") or 0)
    item=_case_row(case_id)
    target=str(payload.get("target_state") or "").strip().upper()
    if target not in {"CONFIRMED","APPROVED","PAID","REJECTED","EXPIRED"}:
        raise ValueError("Partner callback target state is not allowed.")
    evidence_type=str(payload.get("evidence_type") or "").strip().upper() or None
    evidence_reference=str(payload.get("evidence_reference") or "").strip()[:300] or None
    authoritative=target in {"CONFIRMED","APPROVED","PAID"}

    transition=transition_coverage_state(
        source_id=item["source_id"],
        current_state=item["state"],
        target_state=target,
        evidence_type=evidence_type,
        evidence_reference=evidence_reference,
        authoritative_confirmation=authoritative,
    )
    now=now_iso()
    get_db().execute(
        """
        UPDATE carefin_cases
        SET state=?,latest_evidence_type=COALESCE(?,latest_evidence_type),
            latest_evidence_reference=COALESCE(?,latest_evidence_reference),
            authoritative_confirmation=?,updated_at=?
        WHERE id=?
        """,
        (
            transition["state"],transition.get("evidence_type"),transition.get("evidence_reference"),
            1 if authoritative else 0,now,case_id,
        ),
    )
    digest=hashlib.sha256(raw_body).hexdigest()
    get_db().execute(
        """
        INSERT INTO carefin_partner_events
        (provider_event_id,case_id,partner_name,payload_digest,created_at)
        VALUES (?,?,?,?,?)
        """,
        (event_id,case_id,status["partner"][:160],digest,now),
    )
    _event(
        case_id,None,"partner_state_transition",previous_state=item["state"],
        state=transition["state"],evidence_type=transition.get("evidence_type"),
        evidence_reference=transition.get("evidence_reference"),
        note=str(payload.get("note") or "")[:1200],
        authoritative_confirmation=authoritative,
    )
    get_db().commit()
    return _case_row(case_id)
