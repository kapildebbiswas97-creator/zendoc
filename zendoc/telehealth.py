import secrets

from .db import get_db, now_iso
from .security import hash_token


DOCTOR_STATUSES = ("available", "busy", "offline", "consultation_only")
CONSULTATION_TYPES = ("chat", "voice", "video")
CONSULTATION_STATUSES = ("requested", "accepted", "rejected", "scheduled", "ended", "cancelled")
PATIENT_MESSAGE_POLICIES = ("nobody", "existing_patient", "appointment", "accepted_consultation", "anyone")


def _value(user, key, default=None):
    if user is None:
        return default
    if hasattr(user, "keys") and key in user.keys():
        return user[key]
    return user.get(key, default) if isinstance(user, dict) else default


def _user_id(user):
    return int(_value(user, "id", 0) or 0)


def _doctor_row(doctor_id):
    return get_db().execute(
        "SELECT * FROM users WHERE id=? AND role IN ('doctor','hospital') AND active=1",
        (int(doctor_id),),
    ).fetchone()


def set_doctor_availability(actor, data):
    if _value(actor, "role") not in {"doctor", "hospital", "admin"}:
        raise PermissionError("Only doctors, hospitals, or admins can update doctor availability.")
    doctor_id = int(data.get("doctor_id") or _user_id(actor))
    if _value(actor, "role") != "admin" and doctor_id != _user_id(actor):
        raise PermissionError("Doctors can only update their own availability.")
    if not _doctor_row(doctor_id):
        raise LookupError("Doctor account not found.")
    status = str(data.get("status") or "offline").strip().lower()
    if status not in DOCTOR_STATUSES:
        raise ValueError("Invalid doctor availability status.")
    patient_message_policy = str(data.get("patient_message_policy") or "accepted_consultation").strip().lower()
    if patient_message_policy not in PATIENT_MESSAGE_POLICIES:
        raise ValueError("Invalid patient message policy.")
    now = now_iso()
    get_db().execute(
        """
        INSERT INTO doctor_availability
        (doctor_id, status, accepts_chat, accepts_voice, accepts_video, patient_message_policy,
         allow_voice_requests, allow_video_requests, allow_new_consultation_requests, note, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(doctor_id) DO UPDATE SET
            status=excluded.status,
            accepts_chat=excluded.accepts_chat,
            accepts_voice=excluded.accepts_voice,
            accepts_video=excluded.accepts_video,
            patient_message_policy=excluded.patient_message_policy,
            allow_voice_requests=excluded.allow_voice_requests,
            allow_video_requests=excluded.allow_video_requests,
            allow_new_consultation_requests=excluded.allow_new_consultation_requests,
            note=excluded.note,
            updated_at=excluded.updated_at
        """,
        (
            doctor_id,
            status,
            1 if data.get("accepts_chat", True) else 0,
            1 if data.get("accepts_voice") else 0,
            1 if data.get("accepts_video") else 0,
            patient_message_policy,
            1 if data.get("allow_voice_requests") else 0,
            1 if data.get("allow_video_requests") else 0,
            1 if data.get("allow_new_consultation_requests", True) else 0,
            str(data.get("note") or "").strip()[:300] or None,
            now,
        ),
    )
    get_db().commit()
    return get_doctor_availability(doctor_id)


def get_doctor_availability(doctor_id):
    row = get_db().execute(
        """
        SELECT da.*, u.name doctor_name
        FROM doctor_availability da JOIN users u ON u.id=da.doctor_id
        WHERE da.doctor_id=?
        """,
        (int(doctor_id),),
    ).fetchone()
    if row:
        return dict(row)
    doctor = _doctor_row(doctor_id)
    if not doctor:
        raise LookupError("Doctor account not found.")
    return {
        "doctor_id": int(doctor_id),
        "doctor_name": doctor["name"],
        "status": "offline",
        "accepts_chat": 0,
        "accepts_voice": 0,
        "accepts_video": 0,
        "patient_message_policy": "accepted_consultation",
        "allow_voice_requests": 0,
        "allow_video_requests": 0,
        "allow_new_consultation_requests": 1,
        "note": None,
    }


def request_consultation(actor, data):
    if _value(actor, "role") != "patient":
        raise PermissionError("Only patients can request consultations.")
    doctor_id = int(data.get("doctor_id") or 0)
    if not _doctor_row(doctor_id):
        raise LookupError("Doctor account not found.")
    consultation_type = str(data.get("consultation_type") or "chat").strip().lower()
    if consultation_type not in CONSULTATION_TYPES:
        raise ValueError("Invalid consultation type.")
    reason = str(data.get("reason") or "").strip()
    if not reason:
        raise ValueError("Consultation reason is required.")
    now = now_iso()
    cursor = get_db().execute(
        """
        INSERT INTO consultation_requests
        (patient_id, doctor_id, appointment_id, consultation_type, status, reason, scheduled_for, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'requested', ?, ?, ?, ?)
        """,
        (
            _user_id(actor),
            doctor_id,
            data.get("appointment_id"),
            consultation_type,
            reason[:500],
            data.get("scheduled_for"),
            now,
            now,
        ),
    )
    get_db().commit()
    return get_consultation(actor, cursor.lastrowid)


def list_consultations(actor):
    uid = _user_id(actor)
    role = _value(actor, "role")
    if role == "admin":
        where = "1=1"
        params = ()
    elif role in {"doctor", "hospital"}:
        where = "cr.doctor_id=?"
        params = (uid,)
    else:
        where = "cr.patient_id=?"
        params = (uid,)
    rows = get_db().execute(
        f"""
        SELECT cr.*, patient.name patient_name, doctor.name doctor_name
        FROM consultation_requests cr
        JOIN users patient ON patient.id=cr.patient_id
        JOIN users doctor ON doctor.id=cr.doctor_id
        WHERE {where}
        ORDER BY cr.created_at DESC
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def get_consultation(actor, consultation_id):
    uid = _user_id(actor)
    role = _value(actor, "role")
    row = get_db().execute(
        """
        SELECT cr.*, patient.name patient_name, doctor.name doctor_name, room.id room_id,
               room.provider room_provider, room.status room_status
        FROM consultation_requests cr
        JOIN users patient ON patient.id=cr.patient_id
        JOIN users doctor ON doctor.id=cr.doctor_id
        LEFT JOIN consultation_rooms room ON room.consultation_id=cr.id
        WHERE cr.id=?
        """,
        (int(consultation_id),),
    ).fetchone()
    if not row:
        raise LookupError("Consultation not found.")
    if role != "admin" and uid not in {row["patient_id"], row["doctor_id"]}:
        raise PermissionError("You cannot access another consultation.")
    return dict(row)


def update_consultation_status(actor, consultation_id, status, scheduled_for=None):
    consultation = get_consultation(actor, consultation_id)
    role = _value(actor, "role")
    uid = _user_id(actor)
    status = str(status or "").strip().lower()
    if status not in CONSULTATION_STATUSES:
        raise ValueError("Invalid consultation status.")
    if role not in {"admin", "doctor", "hospital"} or (role != "admin" and uid != consultation["doctor_id"]):
        raise PermissionError("Only the assigned doctor can accept, reject, schedule, or end this consultation.")
    now = now_iso()
    get_db().execute(
        "UPDATE consultation_requests SET status=?, scheduled_for=COALESCE(?, scheduled_for), updated_at=? WHERE id=?",
        (status, scheduled_for, now, consultation_id),
    )
    if status in {"accepted", "scheduled"} and not consultation.get("room_id"):
        room_token = secrets.token_urlsafe(32)
        get_db().execute(
            """
            INSERT INTO consultation_rooms (consultation_id, room_token_hash, provider, status, created_at)
            VALUES (?, ?, 'local_demo', 'waiting', ?)
            """,
            (consultation_id, hash_token(room_token), now),
        )
    if status == "ended":
        get_db().execute("UPDATE consultation_rooms SET status='ended', ended_at=? WHERE consultation_id=?", (now, consultation_id))
    get_db().commit()
    return get_consultation(actor, consultation_id)


def send_consultation_message(actor, consultation_id, data):
    consultation = get_consultation(actor, consultation_id)
    body = str(data.get("body") or "").strip()
    if not body:
        raise ValueError("Message body is required.")
    cursor = get_db().execute(
        """
        INSERT INTO consultation_messages
        (consultation_id, sender_id, body, attachment_record_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (consultation["id"], _user_id(actor), body[:2000], data.get("attachment_record_id"), now_iso()),
    )
    get_db().commit()
    return dict(get_db().execute("SELECT * FROM consultation_messages WHERE id=?", (cursor.lastrowid,)).fetchone())


def list_consultation_messages(actor, consultation_id):
    consultation = get_consultation(actor, consultation_id)
    uid = _user_id(actor)
    get_db().execute(
        "UPDATE consultation_messages SET read_at=COALESCE(read_at, ?) WHERE consultation_id=? AND sender_id<>?",
        (now_iso(), consultation["id"], uid),
    )
    get_db().commit()
    rows = get_db().execute(
        """
        SELECT cm.*, u.name sender_name, u.role sender_role
        FROM consultation_messages cm JOIN users u ON u.id=cm.sender_id
        WHERE cm.consultation_id=?
        ORDER BY cm.created_at ASC
        """,
        (consultation["id"],),
    ).fetchall()
    return [dict(row) for row in rows]
