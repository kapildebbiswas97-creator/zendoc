from .db import get_db, now_iso
from .security import is_owner
from .organization_service import active_membership, assert_same_organization


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
    if not is_owner(actor):
        raise PermissionError("Only the configured ZENDOC owner can manage staff profiles.")
    user_id = int(data.get("user_id") or 0)
    staff_type = str(data.get("staff_type") or "").strip().lower()
    if staff_type not in STAFF_TYPES:
        raise ValueError("Invalid staff type.")
    target = get_db().execute("SELECT id FROM users WHERE id=? AND active=1", (user_id,)).fetchone()
    if not target:
        raise LookupError("Staff user account not found.")
    organization_id = data.get("organization_id")
    organization_location_id = data.get("organization_location_id")
    if organization_id not in (None, ""):
        organization_id = int(organization_id)
        membership = active_membership(user_id, organization_id)
        if not membership:
            raise PermissionError("Staff must have an active organization membership before profile binding.")
        if organization_location_id not in (None, ""):
            loc = get_db().execute(
                "SELECT id FROM organization_locations WHERE id=? AND organization_id=? AND active=1",
                (int(organization_location_id), organization_id),
            ).fetchone()
            if not loc:
                raise PermissionError("Staff location does not belong to the selected organization.")
        organization_location_id = int(organization_location_id) if organization_location_id not in (None, "") else None
    else:
        organization_id = None
        organization_location_id = None
    now = now_iso()
    get_db().execute(
        """
        INSERT INTO staff_profiles
        (user_id, staff_type, service_area, status, verified, organization_id, organization_location_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            staff_type=excluded.staff_type,
            service_area=excluded.service_area,
            status=excluded.status,
            verified=excluded.verified,
            organization_id=excluded.organization_id,
            organization_location_id=excluded.organization_location_id,
            updated_at=excluded.updated_at
        """,
        (
            user_id,
            staff_type,
            str(data.get("service_area") or "").strip() or None,
            str(data.get("status") or "available").strip().lower(),
            1 if data.get("verified", True) else 0,
            organization_id,
            organization_location_id,
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


def _assert_patient_task_scope(actor, patient_id):
    """Require a real care/fulfilment relationship before provider task creation."""
    if patient_id in (None, ""):
        return None
    try:
        patient_id = int(patient_id)
    except (TypeError, ValueError) as error:
        raise ValueError("patient_id must be a valid patient account id.") from error

    db = get_db()
    patient = db.execute(
        "SELECT id FROM users WHERE id=? AND role='patient' AND active=1",
        (patient_id,),
    ).fetchone()
    if not patient:
        raise LookupError("Patient account not found.")

    if is_owner(actor):
        return patient_id

    actor_id = _user_id(actor)
    role = _value(actor, "role")
    if role in {"doctor", "hospital"}:
        linked = db.execute(
            """
            SELECT 1
            FROM appointments
            WHERE patient_id=? AND provider_id=?
            UNION ALL
            SELECT 1
            FROM consultation_requests
            WHERE patient_id=? AND doctor_id=?
            LIMIT 1
            """,
            (patient_id, actor_id, patient_id, actor_id),
        ).fetchone()
        if linked:
            return patient_id
        raise PermissionError("This provider has no active care relationship with the requested patient.")

    if role == "pharmacy":
        linked = db.execute(
            "SELECT 1 FROM medicine_orders WHERE patient_id=? AND pharmacy_id=? LIMIT 1",
            (patient_id, actor_id),
        ).fetchone()
        if linked:
            return patient_id
        raise PermissionError("This pharmacy has no assigned fulfilment relationship with the requested patient.")

    raise PermissionError("This account cannot create patient-linked operations tasks.")


def create_staff_task(actor, data):
    role = _value(actor, "role")
    if role == "admin" and not is_owner(actor):
        raise PermissionError("Only the configured ZENDOC owner may use the admin operations role.")
    if role not in {"admin", "doctor", "hospital", "pharmacy"}:
        raise PermissionError("Only operations roles can create staff tasks.")
    task_type = str(data.get("task_type") or "").strip().lower()
    if not task_type:
        raise ValueError("task_type is required.")
    title = str(data.get("title") or "").strip()
    if not title:
        raise ValueError("title is required.")
    assigned_staff_id = data.get("assigned_staff_id")
    if assigned_staff_id:
        staff_profile = get_staff_profile(int(assigned_staff_id))
        if is_owner(actor):
            pass
        else:
            if not organization_id:
                raise PermissionError("Standalone providers cannot directly assign organization staff.")
            if int(staff_profile.get("organization_id") or 0) != organization_id:
                raise PermissionError("Assigned staff must belong to the same provider organization.")
            assert_same_organization(actor, int(assigned_staff_id))
    patient_id = _assert_patient_task_scope(actor, data.get("patient_id"))
    actor_membership = active_membership(_user_id(actor))
    organization_id = int(actor_membership["organization_id"]) if actor_membership else None
    now = now_iso()
    cursor = get_db().execute(
        """
        INSERT INTO staff_tasks
        (requested_by, assigned_staff_id, patient_id, organization_id, source_type, source_id, task_type, title, description, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _user_id(actor),
            assigned_staff_id,
            patient_id,
            organization_id,
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
        if not is_owner(actor):
            raise PermissionError("Only the configured ZENDOC owner may view all staff tasks.")
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
    if role == "admin":
        if not is_owner(actor):
            raise PermissionError("Only the configured ZENDOC owner may access all staff tasks.")
    elif uid not in {row["requested_by"], row["assigned_staff_id"]}:
        raise PermissionError("You cannot access another staff task.")
    return dict(row)


def update_staff_task(actor, task_id, status, message=None):
    task = get_staff_task(actor, task_id)
    uid = _user_id(actor)
    role = _value(actor, "role")
    if role == "admin":
        if not is_owner(actor):
            raise PermissionError("Only the configured ZENDOC owner may update arbitrary staff tasks.")
    elif uid != task["assigned_staff_id"]:
        raise PermissionError("Only assigned staff or the ZENDOC owner can update this task.")
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
