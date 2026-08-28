from .db import get_db, now_iso


STAFF_TYPES = (
    "home_care_nurse",
    "caregiver",
    "physiotherapist",
    "sample_collection_worker",
    "pharmacy_worker",
    "medicine_delivery_staff",
    "transport_driver",
    "ambulance_operator",
    "device_technician",
    "customer_support",
    "field_operations",
)
TASK_STATUSES = ("requested", "queued", "assigned", "accepted", "in_progress", "completed", "failed", "escalated", "cancelled")


def _value(user, key, default=None):
    if user is None:
        return default
    if hasattr(user, "keys") and key in user.keys():
        return user[key]
    return user.get(key, default) if isinstance(user, dict) else default


def _user_id(user):
    return int(_value(user, "id", 0) or 0)


def upsert_staff_profile(actor, data):
    if _value(actor, "role") != "admin":
        raise PermissionError("Only admins can manage staff profiles.")
    user_id = int(data.get("user_id") or 0)
    staff_type = str(data.get("staff_type") or "").strip().lower()
    if staff_type not in STAFF_TYPES:
        raise ValueError("Invalid staff type.")
    target = get_db().execute("SELECT id FROM users WHERE id=? AND active=1", (user_id,)).fetchone()
    if not target:
        raise LookupError("Staff user account not found.")
    now = now_iso()
    get_db().execute(
        """
        INSERT INTO staff_profiles (user_id, staff_type, service_area, status, verified, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            staff_type=excluded.staff_type,
            service_area=excluded.service_area,
            status=excluded.status,
            verified=excluded.verified,
            updated_at=excluded.updated_at
        """,
        (
            user_id,
            staff_type,
            str(data.get("service_area") or "").strip() or None,
            str(data.get("status") or "available").strip().lower(),
            1 if data.get("verified", True) else 0,
            now,
            now,
        ),
    )
    get_db().commit()
    return get_staff_profile(user_id)


def get_staff_profile(user_id):
    row = get_db().execute(
        "SELECT sp.*, u.name, u.email FROM staff_profiles sp JOIN users u ON u.id=sp.user_id WHERE sp.user_id=?",
        (int(user_id),),
    ).fetchone()
    if not row:
        raise LookupError("Staff profile not found.")
    return dict(row)


def create_staff_task(actor, data):
    if _value(actor, "role") not in {"admin", "doctor", "hospital", "pharmacy"}:
        raise PermissionError("Only operations roles can create staff tasks.")
    task_type = str(data.get("task_type") or "").strip().lower()
    if not task_type:
        raise ValueError("task_type is required.")
    title = str(data.get("title") or "").strip()
    if not title:
        raise ValueError("title is required.")
    assigned_staff_id = data.get("assigned_staff_id")
    if assigned_staff_id:
        get_staff_profile(int(assigned_staff_id))
    now = now_iso()
    cursor = get_db().execute(
        """
        INSERT INTO staff_tasks
        (requested_by, assigned_staff_id, patient_id, source_type, source_id, task_type, title, description, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _user_id(actor),
            assigned_staff_id,
            data.get("patient_id"),
            data.get("source_type"),
            data.get("source_id"),
            task_type,
            title[:200],
            str(data.get("description") or "").strip()[:1000] or None,
            "assigned" if assigned_staff_id else "requested",
            now,
            now,
        ),
    )
    _add_task_event(cursor.lastrowid, actor, "created", "Task created.")
    get_db().commit()
    return get_staff_task(actor, cursor.lastrowid)


def list_staff_tasks(actor):
    uid = _user_id(actor)
    role = _value(actor, "role")
    if role == "admin":
        where = "1=1"
        params = ()
    else:
        where = "requested_by=? OR assigned_staff_id=?"
        params = (uid, uid)
    rows = get_db().execute(
        f"""
        SELECT st.*, requester.name requester_name, staff.name assigned_staff_name
        FROM staff_tasks st
        JOIN users requester ON requester.id=st.requested_by
        LEFT JOIN users staff ON staff.id=st.assigned_staff_id
        WHERE {where}
        ORDER BY st.created_at DESC
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def get_staff_task(actor, task_id):
    uid = _user_id(actor)
    role = _value(actor, "role")
    row = get_db().execute(
        """
        SELECT st.*, requester.name requester_name, staff.name assigned_staff_name
        FROM staff_tasks st
        JOIN users requester ON requester.id=st.requested_by
        LEFT JOIN users staff ON staff.id=st.assigned_staff_id
        WHERE st.id=?
        """,
        (int(task_id),),
    ).fetchone()
    if not row:
        raise LookupError("Staff task not found.")
    if role != "admin" and uid not in {row["requested_by"], row["assigned_staff_id"]}:
        raise PermissionError("You cannot access another staff task.")
    return dict(row)


def update_staff_task(actor, task_id, status, message=None):
    task = get_staff_task(actor, task_id)
    uid = _user_id(actor)
    role = _value(actor, "role")
    if role != "admin" and uid != task["assigned_staff_id"]:
        raise PermissionError("Only assigned staff or admins can update this task.")
    status = str(status or "").strip().lower()
    if status not in TASK_STATUSES:
        raise ValueError("Invalid task status.")
    now = now_iso()
    get_db().execute(
        "UPDATE staff_tasks SET status=?, escalation_reason=CASE WHEN ?='escalated' THEN ? ELSE escalation_reason END, updated_at=? WHERE id=?",
        (status, status, message, now, task_id),
    )
    _add_task_event(task_id, actor, status, message)
    get_db().commit()
    return get_staff_task(actor, task_id)


def _add_task_event(task_id, actor, event_type, message):
    get_db().execute(
        "INSERT INTO staff_task_events (task_id, actor_id, event_type, message, created_at) VALUES (?, ?, ?, ?, ?)",
        (task_id, _user_id(actor) or None, event_type, message, now_iso()),
    )
