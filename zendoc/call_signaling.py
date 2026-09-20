"""Authenticated WebRTC signaling for ZENDOC voice/video calls.

ZENDOC stores bounded signaling metadata only. Media flows peer-to-peer through
the browser. TURN/STUN infrastructure is deployment configuration; no call is
claimed reliable across public networks until that infrastructure is verified.
"""
from __future__ import annotations

import json

from .communication_policy import can_call, can_video_call
from .db import get_db, now_iso
from .notification_providers import deliver_notification

CALL_TYPES = {"voice", "video"}
ACTIVE_STATUSES = {"ringing", "accepted"}


def ensure_call_schema():
    get_db().executescript(
        """
        CREATE TABLE IF NOT EXISTS connect_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            initiator_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            callee_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            call_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ringing',
            offer_json TEXT NOT NULL,
            answer_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            ended_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_connect_calls_conversation
            ON connect_calls(conversation_id,status,created_at,id);
        CREATE INDEX IF NOT EXISTS idx_connect_calls_callee
            ON connect_calls(callee_id,status,created_at,id);

        CREATE TABLE IF NOT EXISTS connect_call_ice (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_id INTEGER NOT NULL REFERENCES connect_calls(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            candidate_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_connect_call_ice
            ON connect_call_ice(call_id,id);
        """
    )


def _uid(user) -> int:
    if user is None:
        raise PermissionError("Authentication required.")
    if hasattr(user, "keys") and "id" in user.keys():
        return int(user["id"])
    return int(user.get("id") or 0)


def _actor_name(user) -> str:
    if user is None:
        return "A ZENDOC contact"
    if hasattr(user, "keys") and "name" in user.keys():
        return str(user["name"] or "A ZENDOC contact")
    if isinstance(user, dict):
        return str(user.get("name") or "A ZENDOC contact")
    return "A ZENDOC contact"


def _conversation_context(actor, conversation_id: int) -> dict:
    uid = _uid(actor)
    row = get_db().execute(
        """
        SELECT c.*
        FROM conversations c
        JOIN conversation_participants cp ON cp.conversation_id=c.id
        WHERE c.id=? AND c.status='active' AND cp.user_id=?
        """,
        (int(conversation_id), uid),
    ).fetchone()
    if not row:
        raise PermissionError("You cannot access this conversation.")
    other = get_db().execute(
        """
        SELECT cp.user_id,u.name,u.role
        FROM conversation_participants cp
        JOIN users u ON u.id=cp.user_id
        WHERE cp.conversation_id=? AND cp.user_id<>?
        ORDER BY cp.joined_at ASC LIMIT 1
        """,
        (int(conversation_id), uid),
    ).fetchone()
    if not other:
        raise LookupError("Call participant not found.")
    return {
        "conversation": dict(row),
        "other_id": int(other["user_id"]),
        "other_name": other["name"],
        "other_role": other["role"],
    }


def call_permission(actor, conversation_id: int, call_type: str) -> dict:
    kind = str(call_type or "").strip().lower()
    if kind not in CALL_TYPES:
        raise ValueError("Call type must be voice or video.")
    context = _conversation_context(actor, conversation_id)
    conversation = context["conversation"]
    policy_context = {"type": conversation["context_type"], "id": conversation["context_id"]}
    decision = (
        can_video_call(actor, context["other_id"], policy_context)
        if kind == "video"
        else can_call(actor, context["other_id"], policy_context)
    )
    return {
        **decision,
        "call_type": kind,
        "conversation_id": int(conversation_id),
        "other_id": context["other_id"],
        "other_name": context["other_name"],
        "other_role": context["other_role"],
    }


def _validated_description(value, expected_type: str) -> str:
    raw = str(value or "").strip()
    if not raw or len(raw) > 60_000:
        raise ValueError("WebRTC session description is missing or too large.")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("WebRTC session description must be valid JSON.") from exc
    if not isinstance(data, dict) or data.get("type") != expected_type or not str(data.get("sdp") or "").strip():
        raise ValueError(f"Expected a valid WebRTC {expected_type} description.")
    return json.dumps({"type": expected_type, "sdp": str(data["sdp"])[:55_000]}, separators=(",", ":"))


def _call_row(call_id: int):
    row = get_db().execute(
        """
        SELECT c.*,ui.name initiator_name,uc.name callee_name
        FROM connect_calls c
        JOIN users ui ON ui.id=c.initiator_id
        JOIN users uc ON uc.id=c.callee_id
        WHERE c.id=?
        """,
        (int(call_id),),
    ).fetchone()
    if not row:
        raise LookupError("Call session not found.")
    return dict(row)


def _assert_call_participant(actor, call_id: int) -> tuple[dict, int]:
    uid = _uid(actor)
    row = _call_row(call_id)
    if uid not in {int(row["initiator_id"]), int(row["callee_id"])}:
        raise PermissionError("You cannot access this call.")
    return row, uid


def create_call(actor, conversation_id: int, call_type: str, offer_json: str) -> dict:
    ensure_call_schema()
    permission = call_permission(actor, conversation_id, call_type)
    if not permission["allowed"]:
        raise PermissionError(permission["reason"])
    uid = _uid(actor)
    existing = get_db().execute(
        """
        SELECT id FROM connect_calls
        WHERE conversation_id=? AND status IN ('ringing','accepted')
        ORDER BY id DESC LIMIT 1
        """,
        (int(conversation_id),),
    ).fetchone()
    if existing:
        raise ValueError("A call is already active in this conversation.")
    offer = _validated_description(offer_json, "offer")
    now = now_iso()
    cursor = get_db().execute(
        """
        INSERT INTO connect_calls
        (conversation_id,initiator_id,callee_id,call_type,status,offer_json,created_at,updated_at)
        VALUES (?,?,?,?, 'ringing', ?,?,?)
        """,
        (int(conversation_id), uid, int(permission["other_id"]), permission["call_type"], offer, now, now),
    )
    call_id = int(cursor.lastrowid)
    get_db().commit()
    deliver_notification(
        int(permission["other_id"]),
        f"Incoming ZENDOC {permission['call_type']} call",
        f"{_actor_name(actor)} is calling you.",
        channel="in_app",
        template_type="connect_call",
    )
    return get_call_state(actor, call_id)


def answer_call(actor, call_id: int, *, accept: bool, answer_json: str | None = None) -> dict:
    row, uid = _assert_call_participant(actor, call_id)
    if uid != int(row["callee_id"]):
        raise PermissionError("Only the called participant can answer this call.")
    if row["status"] != "ringing":
        raise ValueError("This call is no longer waiting for an answer.")
    now = now_iso()
    if not accept:
        get_db().execute(
            "UPDATE connect_calls SET status='rejected',updated_at=?,ended_at=? WHERE id=?",
            (now, now, int(call_id)),
        )
    else:
        answer = _validated_description(answer_json, "answer")
        get_db().execute(
            "UPDATE connect_calls SET status='accepted',answer_json=?,updated_at=? WHERE id=?",
            (answer, now, int(call_id)),
        )
    get_db().commit()
    return get_call_state(actor, call_id)


def add_ice_candidate(actor, call_id: int, candidate_json: str) -> dict:
    row, uid = _assert_call_participant(actor, call_id)
    if row["status"] not in ACTIVE_STATUSES:
        raise ValueError("This call is no longer active.")
    raw = str(candidate_json or "").strip()
    if not raw or len(raw) > 8_000:
        raise ValueError("ICE candidate is missing or too large.")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("ICE candidate must be valid JSON.") from exc
    if not isinstance(data, dict) or not str(data.get("candidate") or "").strip():
        raise ValueError("ICE candidate is invalid.")
    count = get_db().execute(
        "SELECT COUNT(*) c FROM connect_call_ice WHERE call_id=? AND user_id=?",
        (int(call_id), uid),
    ).fetchone()
    if int(count["c"] or 0) >= 120:
        raise ValueError("ICE candidate limit reached for this call.")
    now = now_iso()
    cursor = get_db().execute(
        "INSERT INTO connect_call_ice (call_id,user_id,candidate_json,created_at) VALUES (?,?,?,?)",
        (int(call_id), uid, json.dumps(data, separators=(",", ":")), now),
    )
    get_db().commit()
    return {"id": int(cursor.lastrowid), "call_id": int(call_id), "created_at": now}


def get_call_state(actor, call_id: int, *, after_candidate_id: int = 0) -> dict:
    ensure_call_schema()
    row, uid = _assert_call_participant(actor, call_id)
    candidates = get_db().execute(
        """
        SELECT id,user_id,candidate_json,created_at
        FROM connect_call_ice
        WHERE call_id=? AND id>?
        ORDER BY id ASC LIMIT 200
        """,
        (int(call_id), max(0, int(after_candidate_id or 0))),
    ).fetchall()
    return {
        "id": int(row["id"]),
        "conversation_id": int(row["conversation_id"]),
        "initiator_id": int(row["initiator_id"]),
        "initiator_name": row["initiator_name"],
        "callee_id": int(row["callee_id"]),
        "callee_name": row["callee_name"],
        "call_type": row["call_type"],
        "status": row["status"],
        "offer": json.loads(row["offer_json"]) if row["offer_json"] and row["offer_json"] != "{}" else None,
        "answer": json.loads(row["answer_json"]) if row["answer_json"] else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "ended_at": row["ended_at"],
        "actor_id": uid,
        "candidates": [
            {
                "id": int(item["id"]),
                "user_id": int(item["user_id"]),
                "candidate": json.loads(item["candidate_json"]),
                "created_at": item["created_at"],
            }
            for item in candidates
        ],
    }


def end_call(actor, call_id: int) -> dict:
    row, _ = _assert_call_participant(actor, call_id)
    if row["status"] not in ACTIVE_STATUSES:
        return get_call_state(actor, call_id)
    now = now_iso()
    get_db().execute(
        """
        UPDATE connect_calls
        SET status='ended',offer_json='{}',answer_json=NULL,updated_at=?,ended_at=?
        WHERE id=?
        """,
        (now, now, int(call_id)),
    )
    get_db().execute("DELETE FROM connect_call_ice WHERE call_id=?", (int(call_id),))
    get_db().commit()
    return get_call_state(actor, call_id)


def list_incoming_calls(actor, limit: int = 10) -> list[dict]:
    ensure_call_schema()
    uid = _uid(actor)
    rows = get_db().execute(
        """
        SELECT c.id,c.conversation_id,c.call_type,c.status,c.created_at,u.name initiator_name
        FROM connect_calls c
        JOIN users u ON u.id=c.initiator_id
        WHERE c.callee_id=? AND c.status='ringing'
        ORDER BY c.created_at DESC,c.id DESC
        LIMIT ?
        """,
        (uid, max(1, min(int(limit or 10), 25))),
    ).fetchall()
    return [dict(row) for row in rows]
