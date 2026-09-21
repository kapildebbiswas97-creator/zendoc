import json

from .communication_policy import (
    can_call,
    can_message,
    can_share_record,
    can_start_conversation,
    can_video_call,
    discover_contacts as discover_permitted_contacts,
    get_user,
    normalize_context,
    public_contact,
)
from .db import get_db, now_iso
from .family_care import has_family_access


MESSAGE_TYPES = (
    "text",
    "system",
    "appointment",
    "consultation",
    "record",
    "report",
    "image",
    "video",
    "audio",
    "service_update",
    "task_update",
)


def _value(user, key, default=None):
    if user is None:
        return default
    if hasattr(user, "keys") and key in user.keys():
        return user[key]
    return user.get(key, default) if isinstance(user, dict) else default


def _user_id(user):
    return int(_value(user, "id", 0) or 0)


def _json(value):
    return json.dumps(value or {}, sort_keys=True)


def _decode_json(value):
    try:
        return json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def _conversation_row(conversation_id):
    row = get_db().execute("SELECT * FROM conversations WHERE id=? AND status='active'", (int(conversation_id),)).fetchone()
    if not row:
        raise LookupError("Conversation not found.")
    return dict(row)


def _participant_ids(conversation_id):
    rows = get_db().execute(
        "SELECT user_id FROM conversation_participants WHERE conversation_id=?",
        (int(conversation_id),),
    ).fetchall()
    return [int(row["user_id"]) for row in rows]


def _assert_participant(actor, conversation_id):
    uid = _user_id(actor)
    row = get_db().execute(
        "SELECT 1 FROM conversation_participants WHERE conversation_id=? AND user_id=?",
        (int(conversation_id), uid),
    ).fetchone()
    if not row:
        raise PermissionError("You cannot access this conversation.")
    return uid


def _other_participant_id(actor, conversation_id):
    uid = _user_id(actor)
    participants = _participant_ids(conversation_id)
    for participant_id in participants:
        if participant_id != uid:
            return participant_id
    return None


def _message_to_dict(row):
    item = dict(row)
    item["metadata"] = _decode_json(item.pop("metadata_json", "{}"))
    attachments = get_db().execute(
        "SELECT id, attachment_type, record_id, url, title, metadata_json FROM message_attachments WHERE message_id=?",
        (item["id"],),
    ).fetchall()
    item["attachments"] = [
        {
            "id": att["id"],
            "attachment_type": att["attachment_type"],
            "record_id": att["record_id"],
            "url": att["url"],
            "title": att["title"],
            "metadata": _decode_json(att["metadata_json"]),
        }
        for att in attachments
    ]

    receipts = get_db().execute(
        """
        SELECT status,delivered_at,read_at
        FROM message_receipts
        WHERE message_id=?
        """,
        (item["id"],),
    ).fetchall()
    total_receipts = len(receipts)
    read_count = sum(1 for receipt in receipts if str(receipt["status"] or "").lower() == "read")
    delivered_count = sum(
        1 for receipt in receipts
        if str(receipt["status"] or "").lower() in {"delivered", "read"}
    )
    if total_receipts and read_count == total_receipts:
        receipt_status = "read"
    elif total_receipts and delivered_count == total_receipts:
        receipt_status = "delivered"
    else:
        receipt_status = "sent"
    item["receipt_summary"] = {
        "status": receipt_status,
        "recipient_count": total_receipts,
        "delivered_count": delivered_count,
        "read_count": read_count,
    }
    return item


def _conversation_to_dict(row, actor):
    item = dict(row)
    uid = _user_id(actor)
    participants = get_db().execute(
        """
        SELECT cp.user_id AS id, cp.user_id, cp.role AS participant_role, cp.last_read_at,
               u.name, u.role, u.city, u.verified
        FROM conversation_participants cp
        JOIN users u ON u.id=cp.user_id
        WHERE cp.conversation_id=?
        ORDER BY cp.joined_at ASC
        """,
        (item["id"],),
    ).fetchall()
    item["participants"] = [
        public_contact(dict(row), reason="Conversation participant", context={"type": item["context_type"], "id": item["context_id"]})
        for row in participants
    ]
    other_participant = next(
        (participant for participant in item["participants"] if int(participant.get("id") or 0) != uid),
        None,
    )
    item["other_participant"] = other_participant
    item["display_name"] = (
        other_participant.get("name")
        if other_participant and str(item.get("conversation_type") or "direct") == "direct"
        else item.get("title") or "ZENDOC Conversation"
    )
    other_id = int(other_participant["id"]) if other_participant else None
    item["unread_count"] = unread_count(actor, conversation_id=item["id"])
    item["can_call"] = False
    item["can_video"] = False
    if other_id:
        policy_context = {"type": item["context_type"], "id": item["context_id"]}
        try:
            item["can_call"] = bool(can_call(actor, other_id, policy_context).get("allowed"))
        except Exception:
            # A capability check must fail closed, never take down the entire
            # Messages page for an otherwise valid conversation.
            item["can_call"] = False
        try:
            item["can_video"] = bool(can_video_call(actor, other_id, policy_context).get("allowed"))
        except Exception:
            item["can_video"] = False
    last = get_db().execute(
        """
        SELECT m.id, m.message_type, m.body, m.created_at, u.name sender_name
        FROM messages m JOIN users u ON u.id=m.sender_id
        WHERE m.conversation_id=? AND m.deleted_at IS NULL
        ORDER BY m.created_at DESC LIMIT 1
        """,
        (item["id"],),
    ).fetchone()
    item["last_message"] = dict(last) if last else None
    return item


def create_communication_permission(actor, data):
    if not actor:
        raise PermissionError("Authentication required.")
    requester_id = int(data.get("requester_id") or _user_id(actor))
    target_user_id = int(data.get("target_user_id") or 0)
    requester = get_user(requester_id)
    target = get_user(target_user_id)
    if not requester:
        raise LookupError("Permission requester not found.")
    if not target:
        raise LookupError("Permission target not found.")
    if requester_id == target_user_id:
        raise ValueError("Communication permission must be granted to another account.")

    actor_id = _user_id(actor)
    actor_role = _value(actor, "role")
    # An active permission is a grant *to* requester_id. The requester must
    # never be able to mint that grant for themselves. Only the target account
    # (the account being contacted) or an authorized admin can activate it.
    if actor_role != "admin" and actor_id != target_user_id:
        raise PermissionError(
            "Only the target account can grant active communication permission."
        )
    context = normalize_context(data)
    now = now_iso()
    cursor = get_db().execute(
        """
        INSERT INTO communication_permissions
        (requester_id, target_user_id, context_type, context_id, allow_chat, allow_voice, allow_video,
         allow_record_sharing, status, created_by, expires_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
        """,
        (
            requester_id,
            target_user_id,
            context["type"],
            context["id"],
            1 if data.get("allow_chat", True) else 0,
            1 if data.get("allow_voice") else 0,
            1 if data.get("allow_video") else 0,
            1 if data.get("allow_record_sharing") else 0,
            actor_id,
            data.get("expires_at"),
            now,
            now,
        ),
    )
    get_db().commit()
    return dict(get_db().execute("SELECT * FROM communication_permissions WHERE id=?", (cursor.lastrowid,)).fetchone())


def list_communication_permissions(actor, related_user_id=None):
    """List explicit communication grants visible to the signed-in participant."""
    if not actor:
        raise PermissionError("Authentication required.")
    actor_id = _user_id(actor)
    params = [actor_id, actor_id]
    related_clause = ""
    if related_user_id is not None:
        related_id = int(related_user_id)
        related_clause = """
          AND (
            (cp.requester_id=? AND cp.target_user_id=?)
            OR (cp.requester_id=? AND cp.target_user_id=?)
          )
        """
        params.extend([actor_id, related_id, related_id, actor_id])

    rows = get_db().execute(
        f"""
        SELECT cp.*,
               requester.name requester_name,
               requester.role requester_role,
               target.name target_name,
               target.role target_role
        FROM communication_permissions cp
        JOIN users requester ON requester.id=cp.requester_id
        JOIN users target ON target.id=cp.target_user_id
        WHERE (cp.requester_id=? OR cp.target_user_id=?)
        {related_clause}
        ORDER BY cp.created_at DESC,cp.id DESC
        LIMIT 100
        """,
        tuple(params),
    ).fetchall()
    now = now_iso()
    result = []
    for row in rows:
        item = dict(row)
        expires_at = str(item.get("expires_at") or "").strip()
        item["expired"] = bool(expires_at and expires_at <= now)
        item["effective"] = bool(
            str(item.get("status") or "") == "active"
            and not item.get("revoked_at")
            and not item["expired"]
        )
        result.append(item)
    return result


def revoke_communication_permission(actor, permission_id):
    """Revoke a grant as either participant or an authorized admin."""
    if not actor:
        raise PermissionError("Authentication required.")
    row = get_db().execute(
        "SELECT * FROM communication_permissions WHERE id=?",
        (int(permission_id),),
    ).fetchone()
    if not row:
        raise LookupError("Communication permission not found.")

    item = dict(row)
    actor_id = _user_id(actor)
    actor_role = _value(actor, "role")
    if actor_role != "admin" and actor_id not in {
        int(item["requester_id"]),
        int(item["target_user_id"]),
    }:
        raise PermissionError("Only a permission participant or admin can revoke it.")

    if item.get("revoked_at") or str(item.get("status") or "") == "revoked":
        return item

    now = now_iso()
    get_db().execute(
        """
        UPDATE communication_permissions
        SET status='revoked',revoked_at=?,updated_at=?
        WHERE id=?
        """,
        (now, now, int(permission_id)),
    )
    get_db().commit()
    return dict(
        get_db().execute(
            "SELECT * FROM communication_permissions WHERE id=?",
            (int(permission_id),),
        ).fetchone()
    )


def discover_contacts(actor, query="", limit=12):
    return discover_permitted_contacts(actor, query=query, limit=limit)


def _find_existing_conversation(actor_id, target_user_id, context):
    row = get_db().execute(
        """
        SELECT c.*
        FROM conversations c
        JOIN conversation_participants a ON a.conversation_id=c.id AND a.user_id=?
        JOIN conversation_participants b ON b.conversation_id=c.id AND b.user_id=?
        WHERE c.status='active'
          AND COALESCE(c.context_type, '')=COALESCE(?, '')
          AND COALESCE(c.context_id, '')=COALESCE(?, '')
        ORDER BY c.updated_at DESC LIMIT 1
        """,
        (int(actor_id), int(target_user_id), context["type"], context["id"]),
    ).fetchone()
    return dict(row) if row else None


def start_conversation(actor, data):
    if not actor:
        raise PermissionError("Authentication required.")
    target_user_id = int(data.get("target_user_id") or data.get("contact_id") or 0)
    context = normalize_context(data)
    decision = can_start_conversation(actor, target_user_id, context)
    if not decision["allowed"]:
        raise PermissionError(decision["reason"])
    actor_id = _user_id(actor)
    existing = _find_existing_conversation(actor_id, target_user_id, context)
    if existing:
        return get_conversation(actor, existing["id"])
    target = get_user(target_user_id)
    now = now_iso()
    title = str(data.get("title") or f"{_value(actor, 'name', 'ZENDOC')} and {target['name']}").strip()[:180]
    cursor = get_db().execute(
        """
        INSERT INTO conversations (conversation_type, title, created_by, context_type, context_id, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
        """,
        (str(data.get("conversation_type") or "direct")[:50], title, actor_id, context["type"], context["id"], now, now),
    )
    conversation_id = cursor.lastrowid
    get_db().executemany(
        """
        INSERT INTO conversation_participants (conversation_id, user_id, role, joined_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            (conversation_id, actor_id, "owner", now),
            (conversation_id, target_user_id, "member", now),
        ),
    )
    get_db().execute(
        """
        INSERT INTO messages (conversation_id, sender_id, message_type, body, metadata_json, created_at)
        VALUES (?, ?, 'system', ?, ?, ?)
        """,
        (conversation_id, actor_id, f"Conversation started: {decision['reason']}.", _json({"context": context}), now),
    )
    get_db().commit()
    return get_conversation(actor, conversation_id)


def list_conversations(actor, limit=25):
    if not actor:
        raise PermissionError("Authentication required.")
    rows = get_db().execute(
        """
        SELECT c.*
        FROM conversations c
        JOIN conversation_participants cp ON cp.conversation_id=c.id
        WHERE cp.user_id=? AND c.status='active'
        ORDER BY c.updated_at DESC LIMIT ?
        """,
        (_user_id(actor), max(1, min(int(limit or 25), 100))),
    ).fetchall()
    return [_conversation_to_dict(dict(row), actor) for row in rows]


def get_conversation(actor, conversation_id):
    _assert_participant(actor, conversation_id)
    return _conversation_to_dict(_conversation_row(conversation_id), actor)


def list_messages(actor, conversation_id, limit=100):
    _assert_participant(actor, conversation_id)
    mark_read(actor, conversation_id)
    rows = get_db().execute(
        """
        SELECT m.*, u.name sender_name, u.role sender_role
        FROM messages m JOIN users u ON u.id=m.sender_id
        WHERE m.conversation_id=? AND m.deleted_at IS NULL
        ORDER BY m.created_at ASC LIMIT ?
        """,
        (int(conversation_id), max(1, min(int(limit or 100), 200))),
    ).fetchall()
    return [_message_to_dict(row) for row in rows]


def _message_recipient_ids(conversation_id, sender_id):
    return [uid for uid in _participant_ids(conversation_id) if uid != int(sender_id)]


def _create_message_receipts(message_id, conversation_id, sender_id):
    now = now_iso()
    for uid in _message_recipient_ids(conversation_id, sender_id):
        get_db().execute(
            """
            INSERT OR IGNORE INTO message_receipts (message_id, user_id, status, delivered_at)
            VALUES (?, ?, 'delivered', ?)
            """,
            (int(message_id), uid, now),
        )


def _deliver_message_notifications_best_effort(conversation_id, sender_id, message_type):
    """Notifications are auxiliary; they must never roll back a valid message."""
    from .notification_providers import deliver_notification

    for uid in _message_recipient_ids(conversation_id, sender_id):
        try:
            deliver_notification(
                uid,
                "New ZENDOC message",
                f"A {message_type.replace('_', ' ')} message is waiting in ZENDOC Connect.",
                channel="in_app",
                template_type="connect_message",
            )
            get_db().commit()
        except Exception:
            # On PostgreSQL an exception can abort the transaction. Roll back
            # only the notification attempt; the message was committed first.
            try:
                get_db().rollback()
            except Exception:
                pass

def send_message(actor, conversation_id, data):
    conversation = _conversation_row(conversation_id)
    sender_id = _assert_participant(actor, conversation_id)
    other_id = _other_participant_id(actor, conversation_id)
    if other_id:
        decision = can_message(actor, other_id, {"type": conversation["context_type"], "id": conversation["context_id"]})
        if not decision["allowed"]:
            raise PermissionError(decision["reason"])
    message_type = str(data.get("message_type") or data.get("type") or "text").strip().lower()
    if message_type not in MESSAGE_TYPES:
        raise ValueError("Unsupported message type.")
    body = str(data.get("body") or "").strip()
    if not body:
        raise ValueError("Message body is required.")
    now = now_iso()
    cursor = get_db().execute(
        """
        INSERT INTO messages (conversation_id, sender_id, message_type, body, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (int(conversation_id), sender_id, message_type, body[:4000], _json(data.get("metadata")), now),
    )
    message_id = cursor.lastrowid
    get_db().execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, int(conversation_id)))
    _create_message_receipts(message_id, conversation_id, sender_id)
    # Persist the actual private message before auxiliary notifications. This
    # prevents an SMTP/notification/schema outage from surfacing as a 500 and
    # losing a message the user successfully submitted.
    get_db().commit()
    try:
        _deliver_message_notifications_best_effort(conversation_id, sender_id, message_type)
    except Exception:
        # Core messaging has already committed. Even an unexpected auxiliary
        # notification failure must not turn the successful send into a 500.
        try:
            get_db().rollback()
        except Exception:
            pass
    try:
        from .event_bus import publish_event
        publish_event(
            "connect.message.created",
            actor=actor,
            entity_type="conversation",
            entity_id=str(conversation_id),
            status="created",
            payload={"message_id": message_id, "message_type": message_type},
        )
    except Exception:
        pass
    return _message_to_dict(get_db().execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone())


def mark_read(actor, conversation_id):
    uid = _assert_participant(actor, conversation_id)
    now = now_iso()
    get_db().execute(
        "UPDATE conversation_participants SET last_read_at=? WHERE conversation_id=? AND user_id=?",
        (now, int(conversation_id), uid),
    )
    get_db().execute(
        """
        UPDATE message_receipts
        SET status='read', read_at=COALESCE(read_at, ?)
        WHERE user_id=? AND message_id IN (SELECT id FROM messages WHERE conversation_id=?)
        """,
        (now, uid, int(conversation_id)),
    )
    get_db().commit()
    return {"conversation_id": int(conversation_id), "read_at": now}


def unread_count(actor, conversation_id=None):
    if not actor:
        return 0
    uid = _user_id(actor)
    if conversation_id:
        row = get_db().execute(
            """
            SELECT COUNT(*) c
            FROM message_receipts mr
            JOIN messages m ON m.id=mr.message_id
            WHERE mr.user_id=? AND m.conversation_id=? AND mr.read_at IS NULL
            """,
            (uid, int(conversation_id)),
        ).fetchone()
        return int(row["c"] or 0)
    row = get_db().execute(
        "SELECT COUNT(*) c FROM message_receipts WHERE user_id=? AND read_at IS NULL",
        (uid,),
    ).fetchone()
    return int(row["c"] or 0)


def share_video_message(actor, conversation_id, data):
    video_url = str(data.get("video_url") or data.get("url") or "").strip()
    title = str(data.get("title") or "Educational video").strip()
    if not video_url:
        raise ValueError("video_url is required.")
    message = send_message(
        actor,
        conversation_id,
        {
            "message_type": "video",
            "body": f"Shared video: {title}",
            "metadata": {"video_url": video_url, "title": title, "provider": data.get("provider"), "educational_only": True},
        },
    )
    get_db().execute(
        """
        INSERT INTO message_attachments (message_id, attachment_type, url, title, metadata_json, created_at)
        VALUES (?, 'video', ?, ?, ?, ?)
        """,
        (message["id"], video_url, title[:200], _json({"provider": data.get("provider")}), now_iso()),
    )
    get_db().commit()
    return message


def _record_share_allowed(actor, conversation_id, record_id):
    row = get_db().execute("SELECT owner_id FROM medical_records WHERE id=?", (int(record_id),)).fetchone()
    if not row:
        raise LookupError("Medical record not found.")
    actor_id = _user_id(actor)
    if int(row["owner_id"]) == actor_id or _value(actor, "role") == "admin":
        return True
    if has_family_access(int(row["owner_id"]), actor_id, "reports"):
        return True
    other_id = _other_participant_id(actor, conversation_id)
    return bool(other_id and can_share_record(actor, other_id, {"type": "report_share", "id": record_id})["allowed"])


def share_report_message(actor, conversation_id, data):
    record_id = int(data.get("record_id") or 0)
    if not record_id:
        raise ValueError("record_id is required.")
    if not _record_share_allowed(actor, conversation_id, record_id):
        raise PermissionError("Report sharing requires owner consent or explicit record-sharing permission.")
    message = send_message(
        actor,
        conversation_id,
        {
            "message_type": "report",
            "body": str(data.get("body") or "Shared a ZENDOC medical report with consent."),
            "metadata": {"record_id": record_id, "consent": "owner_or_authorized_family"},
        },
    )
    get_db().execute(
        """
        INSERT INTO message_attachments (message_id, attachment_type, record_id, title, metadata_json, created_at)
        VALUES (?, 'record', ?, ?, ?, ?)
        """,
        (message["id"], record_id, str(data.get("title") or "Medical report")[:200], _json({"consent": True}), now_iso()),
    )
    get_db().commit()
    return message



def share_native_media_message(actor, conversation_id, data):
    """Attach already-validated/stored native image, video or audio media to a conversation."""
    media_kind = str(data.get("media_kind") or "").strip().lower()
    if media_kind not in {"image", "video", "audio"}:
        raise ValueError("Message media must be an image, video or audio clip.")
    storage_key = str(data.get("storage_key") or "").strip()
    mime_type = str(data.get("mime_type") or "").strip().lower()
    original_name = str(data.get("original_name") or "message-media").strip()[:255]
    size_bytes = int(data.get("size_bytes") or 0)
    if not storage_key or not mime_type or size_bytes <= 0:
        raise ValueError("Stored message media metadata is incomplete.")
    caption = str(data.get("body") or data.get("caption") or "").strip()
    default_body = {
        "image": "Shared an image.",
        "video": "Shared a video.",
        "audio": "Shared a voice note.",
    }[media_kind]
    body = caption[:1500] if caption else default_body
    message = send_message(
        actor,
        conversation_id,
        {"message_type": media_kind, "body": body, "metadata": {"native_media": True}},
    )
    get_db().execute(
        """
        INSERT INTO message_attachments
        (message_id,attachment_type,url,title,metadata_json,created_at)
        VALUES (?,?,?,?,?,?)
        """,
        (
            int(message["id"]), media_kind, None, original_name,
            _json({
                "storage_key": storage_key,
                "mime_type": mime_type,
                "size_bytes": size_bytes,
                "native_media": True,
            }),
            now_iso(),
        ),
    )
    get_db().commit()
    return _message_to_dict(
        get_db().execute(
            "SELECT m.*,u.name sender_name,u.role sender_role FROM messages m JOIN users u ON u.id=m.sender_id WHERE m.id=?",
            (int(message["id"]),),
        ).fetchone()
    )


def get_message_media_access(actor, attachment_id: int) -> dict:
    """Return stored media metadata only after proving conversation membership."""
    row = get_db().execute(
        """
        SELECT ma.*,m.conversation_id
        FROM message_attachments ma
        JOIN messages m ON m.id=ma.message_id
        WHERE ma.id=? AND m.deleted_at IS NULL
        """,
        (int(attachment_id),),
    ).fetchone()
    if not row:
        raise LookupError("Message media was not found.")
    _assert_participant(actor, int(row["conversation_id"]))
    metadata = _decode_json(row["metadata_json"])
    storage_key = str(metadata.get("storage_key") or "").strip()
    mime_type = str(metadata.get("mime_type") or "").strip()
    if not metadata.get("native_media") or not storage_key or not mime_type:
        raise LookupError("This attachment is not native ZENDOC message media.")
    return {
        "attachment_id": int(row["id"]),
        "conversation_id": int(row["conversation_id"]),
        "storage_key": storage_key,
        "mime_type": mime_type,
        "title": str(row["title"] or "message-media"),
        "size_bytes": int(metadata.get("size_bytes") or 0),
    }
