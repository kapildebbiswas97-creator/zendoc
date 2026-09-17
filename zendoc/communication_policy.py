from .db import get_db
from .family_care import has_family_access


CONTACT_ROLES = ("patient", "doctor", "hospital", "pharmacy", "government", "admin")
CONTEXT_TYPES = (
    "direct",
    "family",
    "appointment",
    "consultation",
    "pharmacy_order",
    "staff_task",
    "support",
    "video_share",
    "report_share",
)


def _value(user, key, default=None):
    if user is None:
        return default
    if hasattr(user, "keys") and key in user.keys():
        return user[key]
    return user.get(key, default) if isinstance(user, dict) else default


def _user_id(user):
    return int(_value(user, "id", 0) or 0)


def normalize_context(context=None):
    context = dict(context or {})
    context_type = str(context.get("type") or context.get("context_type") or "direct").strip().lower()
    if context_type not in CONTEXT_TYPES:
        context_type = "direct"
    context_id = context.get("id") or context.get("context_id")
    return {"type": context_type, "id": str(context_id) if context_id is not None and str(context_id).strip() else None}


def get_user(user_id):
    row = get_db().execute(
        "SELECT id, name, role, city, verified, active FROM users WHERE id=? AND active=1",
        (int(user_id),),
    ).fetchone()
    return dict(row) if row else None


def public_contact(row, reason=None, context=None):
    return {
        "id": row["id"],
        "name": row["name"],
        "role": row["role"],
        "city": row["city"],
        "verified": row["verified"],
        "reason": reason or "Permitted ZENDOC contact",
        "context": context,
    }


def _has_explicit_permission(requester_id, target_id, channel="chat"):
    column = {
        "chat": "allow_chat",
        "voice": "allow_voice",
        "video": "allow_video",
        "record": "allow_record_sharing",
    }.get(channel, "allow_chat")
    row = get_db().execute(
        f"""
        SELECT id FROM communication_permissions
        WHERE requester_id=? AND target_user_id=? AND status='active' AND revoked_at IS NULL AND {column}=1
        ORDER BY created_at DESC LIMIT 1
        """,
        (int(requester_id), int(target_id)),
    ).fetchone()
    return bool(row)


def _has_patient_initiated_conversation(patient_id, target_id):
    """Return True only for an active conversation that the patient created.

    Starting a conversation and replying to one are intentionally different
    permissions. A provider/service may reply after a patient reaches out, but
    this relationship must never be used to let a doctor or hospital initiate a
    new patient conversation without explicit permission.
    """
    row = get_db().execute(
        """
        SELECT c.id
        FROM conversations c
        JOIN conversation_participants patient_cp
          ON patient_cp.conversation_id=c.id AND patient_cp.user_id=?
        JOIN conversation_participants target_cp
          ON target_cp.conversation_id=c.id AND target_cp.user_id=?
        WHERE c.status='active' AND c.created_by=?
        ORDER BY c.updated_at DESC
        LIMIT 1
        """,
        (int(patient_id), int(target_id), int(patient_id)),
    ).fetchone()
    return bool(row)


def _has_appointment(patient_id, doctor_id):
    row = get_db().execute(
        """
        SELECT id FROM appointments
        WHERE patient_id=? AND provider_id=? AND status NOT IN ('cancelled','rejected')
        ORDER BY scheduled_for DESC LIMIT 1
        """,
        (int(patient_id), int(doctor_id)),
    ).fetchone()
    return bool(row)


def _has_accepted_consultation(patient_id, doctor_id):
    row = get_db().execute(
        """
        SELECT id FROM consultation_requests
        WHERE patient_id=? AND doctor_id=? AND status IN ('accepted','scheduled')
        ORDER BY updated_at DESC LIMIT 1
        """,
        (int(patient_id), int(doctor_id)),
    ).fetchone()
    return bool(row)


def _has_any_consultation(patient_id, doctor_id):
    row = get_db().execute(
        """
        SELECT id FROM consultation_requests
        WHERE patient_id=? AND doctor_id=? AND status NOT IN ('cancelled','rejected')
        ORDER BY updated_at DESC LIMIT 1
        """,
        (int(patient_id), int(doctor_id)),
    ).fetchone()
    return bool(row)


def _has_pharmacy_order(patient_id, pharmacy_id, ordered_by=None):
    params = [int(patient_id), int(pharmacy_id)]
    where = "patient_id=? AND pharmacy_id=?"
    if ordered_by:
        where = f"({where} OR (ordered_by=? AND pharmacy_id=?))"
        params.extend([int(ordered_by), int(pharmacy_id)])
    row = get_db().execute(
        f"SELECT id FROM medicine_orders WHERE {where} ORDER BY created_at DESC LIMIT 1",
        params,
    ).fetchone()
    return bool(row)


def _has_staff_task(actor_id, target_id):
    row = get_db().execute(
        """
        SELECT id FROM staff_tasks
        WHERE (requested_by=? AND assigned_staff_id=?)
           OR (requested_by=? AND assigned_staff_id=?)
           OR (patient_id=? AND assigned_staff_id=?)
        ORDER BY updated_at DESC LIMIT 1
        """,
        (int(actor_id), int(target_id), int(target_id), int(actor_id), int(actor_id), int(target_id)),
    ).fetchone()
    return bool(row)


def _doctor_availability(doctor_id):
    row = get_db().execute("SELECT * FROM doctor_availability WHERE doctor_id=?", (int(doctor_id),)).fetchone()
    if row:
        return dict(row)
    return {
        "accepts_chat": 0,
        "accepts_voice": 0,
        "accepts_video": 0,
        "patient_message_policy": "accepted_consultation",
        "allow_voice_requests": 0,
        "allow_video_requests": 0,
        "allow_new_consultation_requests": 1,
    }


def _doctor_patient_allowed(actor, target, channel="chat"):
    actor_role = actor["role"]
    target_role = target["role"]
    if actor_role == "patient" and target_role in {"doctor", "hospital"}:
        patient_id, doctor_id = actor["id"], target["id"]
        if channel == "chat":
            return True, "Patient-initiated care conversation"
        availability = _doctor_availability(doctor_id)
        if channel == "voice":
            return bool(availability["allow_voice_requests"] and availability["accepts_voice"]), "Doctor allows voice requests"
        if channel == "video":
            return bool(availability["allow_video_requests"] and availability["accepts_video"]), "Doctor allows video requests"
        return False, "Unsupported doctor-patient communication channel"
    if actor_role in {"doctor", "hospital"} and target_role == "patient":
        if channel == "chat" and _has_patient_initiated_conversation(target["id"], actor["id"]):
            return True, "Reply to patient-initiated conversation"
        return False, "Doctor or hospital initiation requires explicit patient communication permission"
    return False, "No doctor-patient context"


def permission_decision(actor, target_user_id, context=None, channel="chat"):
    if not actor:
        return {"allowed": False, "reason": "Authentication required.", "context": normalize_context(context)}
    actor_row = get_user(_user_id(actor))
    target = get_user(target_user_id)
    ctx = normalize_context(context)
    if not actor_row:
        return {"allowed": False, "reason": "Actor account not found.", "context": ctx}
    if not target:
        return {"allowed": False, "reason": "Contact not found.", "context": ctx}
    if actor_row["id"] == target["id"]:
        return {"allowed": False, "reason": "Choose another ZENDOC account.", "context": ctx}

    if _has_explicit_permission(actor_row["id"], target["id"], channel):
        return {"allowed": True, "reason": "Explicit communication permission.", "context": ctx}

    actor_role = actor_row["role"]
    target_role = target["role"]

    # Patient-first messaging is intentionally asymmetric. Patients may open a
    # chat with any non-patient ZENDOC care/service role without waiting for a
    # provider-side permission toggle. Voice, video and record sharing retain
    # their stricter channel-specific gates.
    if channel == "chat" and actor_role == "patient" and target_role in CONTACT_ROLES and target_role != "patient":
        return {"allowed": True, "reason": "Patient-initiated care conversation", "context": ctx}

    # Once a patient has opened a conversation, its other participant may reply
    # in that established thread. This does not grant initiation permission.
    if channel == "chat" and target_role == "patient" and actor_role != "patient":
        if _has_patient_initiated_conversation(target["id"], actor_row["id"]):
            return {"allowed": True, "reason": "Reply to patient-initiated conversation", "context": ctx}

    allowed = False
    reason = "No permitted communication context."

    if actor_role == "admin" or target_role == "admin":
        allowed = ctx["type"] == "support" or _has_explicit_permission(actor_row["id"], target["id"], channel)
        reason = "Support context" if allowed else "Admin access requires support context or explicit permission"
    elif actor_role in {"doctor", "hospital"} and target_role in {"doctor", "hospital"}:
        allowed, reason = True, "Doctor-to-doctor clinical coordination"
    elif {actor_role, target_role} <= {"patient"}:
        allowed = has_family_access(actor_row["id"], target["id"], "care_tasks") or has_family_access(target["id"], actor_row["id"], "care_tasks")
        reason = "Family care consent" if allowed else "Patient-to-patient messaging requires family consent"
    elif "doctor" in {actor_role, target_role} or "hospital" in {actor_role, target_role}:
        allowed, reason = _doctor_patient_allowed(actor_row, target, channel=channel)
    elif actor_role == "patient" and target_role == "pharmacy":
        allowed = channel == "chat" or _has_pharmacy_order(actor_row["id"], target["id"], ordered_by=actor_row["id"])
        reason = "Patient-initiated care conversation" if channel == "chat" else ("Medicine order context" if allowed else "Pharmacy communication requires a medicine order context")
    elif actor_role == "pharmacy" and target_role == "patient":
        allowed = _has_pharmacy_order(target["id"], actor_row["id"])
        reason = "Medicine order context" if allowed else "Pharmacy messaging requires a medicine order context"
    elif _has_staff_task(actor_row["id"], target["id"]):
        allowed, reason = True, "Assigned staff task context"

    return {"allowed": bool(allowed), "reason": reason, "context": ctx}


def can_start_conversation(actor, target_user_id, context=None):
    ctx = normalize_context(context)
    if not actor:
        return {"allowed": False, "reason": "Authentication required.", "context": ctx}
    actor_row = get_user(_user_id(actor))
    target = get_user(target_user_id)
    if actor_row and target and actor_row["role"] in {"doctor", "hospital"} and target["role"] == "patient":
        if not _has_explicit_permission(actor_row["id"], target["id"], "chat"):
            return {
                "allowed": False,
                "reason": "Doctor or hospital initiation requires explicit patient communication permission",
                "context": ctx,
            }
    return permission_decision(actor, target_user_id, context=ctx, channel="chat")


def can_message(actor, target_user_id, context=None):
    return permission_decision(actor, target_user_id, context=context, channel="chat")


def can_call(actor, target_user_id, context=None):
    return permission_decision(actor, target_user_id, context=context, channel="voice")


def can_video_call(actor, target_user_id, context=None):
    return permission_decision(actor, target_user_id, context=context, channel="video")


def can_share_record(actor, target_user_id, context=None):
    return permission_decision(actor, target_user_id, context=context, channel="record")


def can_discover_contact(actor, target_user_id, context=None):
    return can_start_conversation(actor, target_user_id, context=context)


def discover_contacts(actor, query="", limit=12):
    if not actor:
        raise PermissionError("Authentication required.")
    clean_q = str(query or "").strip().lower()
    actor_id = _user_id(actor)
    actor_row = get_user(actor_id)
    if not actor_row:
        raise PermissionError("Actor account not found.")

    # Patients should immediately see care/service contacts so Messages does not
    # look empty or broken. Other roles keep search-first discovery to avoid
    # exposing patient directories without an allowed communication context.
    if len(clean_q) < 2 and actor_row["role"] != "patient":
        return []
    q_param = f"%{clean_q}%" if clean_q else "%"
    rows = get_db().execute(
        """
        SELECT DISTINCT u.id, u.name, u.role, u.city, u.verified, u.active
        FROM users u
        LEFT JOIN provider_profiles pp ON pp.user_id=u.id
        WHERE u.active=1
          AND u.id<>?
          AND (
            LOWER(u.name) LIKE ?
            OR LOWER(u.role) LIKE ?
            OR LOWER(COALESCE(u.city, '')) LIKE ?
            OR LOWER(COALESCE(pp.specialty, '')) LIKE ?
            OR LOWER(COALESCE(pp.organization, '')) LIKE ?
            OR LOWER(COALESCE(pp.provider_type, '')) LIKE ?
          )
        ORDER BY u.role, u.name
        LIMIT 50
        """,
        (actor_id, q_param, q_param, q_param, q_param, q_param, q_param),
    ).fetchall()
    contacts = []
    seen_ids = set()
    for row in rows:
        uid = int(row["id"])
        if uid in seen_ids:
            continue
        decision = can_discover_contact(actor, uid)
        if decision["allowed"]:
            seen_ids.add(uid)
            contacts.append(public_contact(dict(row), reason=decision["reason"], context=decision["context"]))
        if len(contacts) >= int(limit):
            break
    return contacts
