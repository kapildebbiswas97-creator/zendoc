"""Privacy-minimizing identity verification and external eKYC callback boundary."""
from __future__ import annotations

import hashlib
import hmac
import os
import uuid

from .db import get_db, now_iso
from .security import is_owner

PURPOSES={"account_identity","provider_identity","carefin_identity"}
IDENTIFIER_TYPES={
    "aadhaar_last4","pan_last4","passport_last4","driving_license_last4",
    "provider_license_last4","other_last4",
}


def ensure_identity_verification_schema():
    get_db().executescript(
        """
        CREATE TABLE IF NOT EXISTS identity_verification_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_uid TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            purpose TEXT NOT NULL,
            identifier_type TEXT NOT NULL,
            identifier_last4 TEXT NOT NULL,
            provider TEXT NOT NULL,
            status TEXT NOT NULL,
            consent_scope TEXT NOT NULL,
            consent_at TEXT NOT NULL,
            provider_reference TEXT,
            evidence_reference TEXT,
            reviewer_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            review_note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            verified_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_identity_cases_user
            ON identity_verification_cases(user_id,updated_at,id);
        CREATE INDEX IF NOT EXISTS idx_identity_cases_status
            ON identity_verification_cases(status,updated_at,id);

        CREATE TABLE IF NOT EXISTS identity_verification_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL REFERENCES identity_verification_cases(id) ON DELETE CASCADE,
            actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            event_type TEXT NOT NULL,
            status TEXT NOT NULL,
            provider_event_id TEXT UNIQUE,
            reference TEXT,
            note TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_identity_events_case
            ON identity_verification_events(case_id,created_at,id);
        """
    )


def _uid(actor):
    if actor is None:
        raise PermissionError("Authentication required.")
    if hasattr(actor,"keys") and "id" in actor.keys():
        return int(actor["id"])
    return int(actor.get("id") or 0)


def identity_provider_status():
    provider=str(os.environ.get("ZENDOC_EKYC_PROVIDER") or "none").strip().lower()
    secret=str(os.environ.get("ZENDOC_EKYC_WEBHOOK_SECRET") or "")
    verified=str(os.environ.get("ZENDOC_EKYC_VERIFIED") or "").strip().lower() in {"1","true","yes","on"}
    configured=provider not in {"","none","manual"} and bool(secret)
    return {
        "provider":provider,
        "configured":configured,
        "operator_verified":bool(configured and verified),
        "status":"working" if configured and verified else "configured_unverified" if configured else "integration_required",
        "truth_notice":(
            "External eKYC is operator-verified; each user result still requires a signed provider callback."
            if configured and verified else
            "External eKYC configuration exists but is not operator-verified."
            if configured else
            "No authorized external eKYC provider is connected. Manual evidence review is available but is not eKYC."
        ),
    }


def _last4(value):
    clean="".join(ch for ch in str(value or "").strip().upper() if ch.isalnum())
    if not 2 <= len(clean) <= 4:
        raise ValueError("Enter only the last 2–4 characters of the identifier, never the full ID.")
    return clean


def _event(case_id,event_type,status,*,actor=None,provider_event_id=None,reference=None,note=None):
    get_db().execute(
        """
        INSERT INTO identity_verification_events
        (case_id,actor_id,event_type,status,provider_event_id,reference,note,created_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            int(case_id),_uid(actor) if actor is not None else None,
            str(event_type)[:80],str(status)[:40],
            str(provider_event_id or "").strip()[:200] or None,
            str(reference or "").strip()[:300] or None,
            str(note or "").strip()[:1000] or None,now_iso(),
        ),
    )


def create_identity_case(actor,data):
    ensure_identity_verification_schema()
    purpose=str(data.get("purpose") or "account_identity").strip().lower()
    id_type=str(data.get("identifier_type") or "other_last4").strip().lower()
    if purpose not in PURPOSES:
        raise ValueError("Unsupported identity-verification purpose.")
    if id_type not in IDENTIFIER_TYPES:
        raise ValueError("Unsupported identifier type.")
    if str(data.get("consent") or "").strip().lower() not in {"1","true","yes","on"}:
        raise PermissionError("Explicit consent is required before starting identity verification.")
    provider_status=identity_provider_status()
    provider=provider_status["provider"] if provider_status["operator_verified"] else "manual_evidence_review"
    status="pending_external" if provider_status["operator_verified"] else "manual_review_required"
    now=now_iso()
    cursor=get_db().execute(
        """
        INSERT INTO identity_verification_cases
        (case_uid,user_id,purpose,identifier_type,identifier_last4,provider,status,
         consent_scope,consent_at,evidence_reference,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            f"idv_{uuid.uuid4().hex}",_uid(actor),purpose,id_type,_last4(data.get("identifier_last4")),
            provider,status,"identity_verification_only",now,
            str(data.get("evidence_reference") or "").strip()[:300] or None,now,now,
        ),
    )
    case_id=int(cursor.lastrowid)
    _event(case_id,"created",status,actor=actor,reference=data.get("evidence_reference"))
    get_db().commit()
    return get_identity_case(actor,case_id)


def _row(*,case_id=None,case_uid=None):
    row=(get_db().execute("SELECT * FROM identity_verification_cases WHERE id=?",(int(case_id),)).fetchone()
         if case_id is not None else
         get_db().execute("SELECT * FROM identity_verification_cases WHERE case_uid=?",(str(case_uid),)).fetchone())
    if not row:
        raise LookupError("Identity verification case not found.")
    return dict(row)


def get_identity_case(actor,case_id):
    ensure_identity_verification_schema()
    item=_row(case_id=case_id)
    if not is_owner(actor) and int(item["user_id"]) != _uid(actor):
        raise PermissionError("You cannot access this identity verification case.")
    events=get_db().execute(
        """
        SELECT e.*,u.name actor_name FROM identity_verification_events e
        LEFT JOIN users u ON u.id=e.actor_id
        WHERE e.case_id=? ORDER BY e.created_at ASC,e.id ASC
        """,(int(case_id),)
    ).fetchall()
    item["events"]=[dict(row) for row in events]
    item["external_ekyc_verified"]=item["status"]=="verified_external"
    item["manual_identity_reviewed"]=item["status"]=="verified_manual"
    return item


def list_identity_cases(actor,*,limit=100):
    ensure_identity_verification_schema()
    limit=max(1,min(int(limit or 100),500))
    if is_owner(actor):
        rows=get_db().execute(
            """
            SELECT c.*,u.name user_name,u.email user_email FROM identity_verification_cases c
            JOIN users u ON u.id=c.user_id ORDER BY c.updated_at DESC,c.id DESC LIMIT ?
            """,(limit,)
        ).fetchall()
    else:
        rows=get_db().execute(
            """
            SELECT c.*,u.name user_name,u.email user_email FROM identity_verification_cases c
            JOIN users u ON u.id=c.user_id WHERE c.user_id=?
            ORDER BY c.updated_at DESC,c.id DESC LIMIT ?
            """,(_uid(actor),limit)
        ).fetchall()
    return [dict(row) for row in rows]


def owner_review_identity_case(actor,case_id,*,decision,evidence_reference=None,note=None):
    ensure_identity_verification_schema()
    if not is_owner(actor):
        raise PermissionError("Only the ZENDOC owner can review manual identity evidence.")
    item=_row(case_id=case_id)
    choice=str(decision or "").strip().lower()
    if choice not in {"verified_manual","rejected","cancelled"}:
        raise ValueError("Owner review can record verified_manual, rejected, or cancelled only.")
    reference=str(evidence_reference or item.get("evidence_reference") or "").strip()[:300] or None
    if choice=="verified_manual" and not reference:
        raise ValueError("Manual identity review requires an evidence reference.")
    now=now_iso()
    get_db().execute(
        """
        UPDATE identity_verification_cases
        SET status=?,evidence_reference=COALESCE(?,evidence_reference),reviewer_id=?,
            review_note=?,updated_at=?,verified_at=?
        WHERE id=?
        """,
        (choice,reference,_uid(actor),str(note or "").strip()[:1000] or None,
         now,now if choice=="verified_manual" else None,int(case_id)),
    )
    _event(case_id,"owner_review",choice,actor=actor,reference=reference,note=note)
    get_db().commit()
    return get_identity_case(actor,case_id)


def apply_external_result(payload,raw_body,signature):
    ensure_identity_verification_schema()
    provider_status=identity_provider_status()
    secret=str(os.environ.get("ZENDOC_EKYC_WEBHOOK_SECRET") or "")
    if not provider_status["operator_verified"] or not secret:
        raise PermissionError("External eKYC provider is not configured and operator-verified.")
    supplied=str(signature or "").strip()
    if supplied.lower().startswith("sha256="):
        supplied=supplied.split("=",1)[1]
    expected=hmac.new(secret.encode("utf-8"),raw_body,hashlib.sha256).hexdigest()
    if not supplied or not hmac.compare_digest(supplied,expected):
        raise PermissionError("Invalid eKYC webhook signature.")
    case=_row(case_uid=payload.get("case_uid"))
    if case["provider"] != provider_status["provider"]:
        raise PermissionError("eKYC provider does not match the case provider.")
    event_id=str(payload.get("event_id") or "").strip()[:200]
    if not event_id:
        raise ValueError("Provider event_id is required for idempotency.")
    existing=get_db().execute(
        "SELECT id FROM identity_verification_events WHERE provider_event_id=?",(event_id,)
    ).fetchone()
    if existing:
        return _row(case_id=case["id"])
    result=str(payload.get("status") or "").strip().lower()
    if result not in {"verified","rejected"}:
        raise ValueError("External eKYC status must be verified or rejected.")
    provider_reference=str(payload.get("provider_reference") or "").strip()[:300]
    if result=="verified" and not provider_reference:
        raise ValueError("Verified eKYC callback requires provider_reference.")
    state="verified_external" if result=="verified" else "rejected"
    now=now_iso()
    get_db().execute(
        """
        UPDATE identity_verification_cases
        SET status=?,provider_reference=?,updated_at=?,verified_at=?
        WHERE id=?
        """,
        (state,provider_reference or None,now,now if state=="verified_external" else None,int(case["id"])),
    )
    _event(case["id"],"external_provider_result",state,provider_event_id=event_id,
           reference=provider_reference,note=str(payload.get("note") or "")[:1000])
    get_db().commit()
    return _row(case_id=case["id"])


def identity_case_options():
    return {"purposes":sorted(PURPOSES),"identifier_types":sorted(IDENTIFIER_TYPES),
            "provider_status":identity_provider_status()}
