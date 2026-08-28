"""
Family Care & Remote Parent Care Service.

Allows users to manage healthcare for parents, children, spouse, grandparents,
and dependents. Supports explicit consent grants, remote parent care tasks,
and audit logging.
"""

import json
from datetime import datetime, timezone

from .db import get_db, now_iso


RELATIONSHIPS = (
    "self", "father", "mother", "spouse", "son", "daughter",
    "grandfather", "grandmother", "guardian", "other"
)

GENDERS = ("male", "female", "other", "prefer_not_to_say")

SCOPES = (
    "appointments",
    "reports",
    "metrics",
    "timeline",
    "emergency",
    "home_health",
    "pharmacy",
    "transport",
    "care_tasks",
)


def _user_id(user):
    uid = user["id"] if hasattr(user, "__getitem__") else getattr(user, "id", None)
    return int(uid or 0)


def _row_value(row, key, default=None):
    if row is None:
        return default
    if hasattr(row, "keys") and key in row.keys():
        return row[key]
    return row.get(key, default) if isinstance(row, dict) else default


def _normalize_scopes(scopes):
    if isinstance(scopes, str):
        scopes = [item.strip() for item in scopes.split(",")]
    normalized = sorted({str(item).strip().lower() for item in (scopes or []) if str(item).strip()})
    invalid = [scope for scope in normalized if scope not in SCOPES]
    if invalid:
        raise ValueError(f"Unsupported family access scope: {', '.join(invalid)}")
    if not normalized:
        raise ValueError("At least one family access scope is required.")
    return normalized


def _parse_scopes(value):
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item).strip().lower() for item in parsed if str(item).strip()]


def add_family_member(user, data):
    """Add a family member under the user's account."""
    uid = _user_id(user)
    if not uid:
        raise PermissionError("Authentication required.")

    name = str(data.get("member_name") or "").strip()
    if not name:
        raise ValueError("Family member name is required.")

    relationship = str(data.get("relationship") or "other").strip().lower()
    if relationship not in RELATIONSHIPS:
        relationship = "other"

    gender = str(data.get("gender") or "prefer_not_to_say").strip().lower()
    if gender not in GENDERS:
        gender = "prefer_not_to_say"

    age = None
    if data.get("age"):
        try:
            age = int(data["age"])
            if age < 0 or age > 150:
                raise ValueError("Age must be between 0 and 150.")
        except (TypeError, ValueError):
            raise ValueError("Age must be a valid number.")

    phone = str(data.get("phone") or "").strip() or None
    city = str(data.get("city") or "").strip() or None
    is_remote_parent = 1 if data.get("is_remote_parent") or relationship in ("father", "mother", "grandfather", "grandmother") else 0

    now = now_iso()
    db = get_db()
    cursor = db.execute(
        """INSERT INTO family_members
        (user_id, member_name, relationship, age, gender, phone, city, is_remote_parent, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (uid, name, relationship, age, gender, phone, city, is_remote_parent, now, now),
    )
    db.commit()
    return get_family_member(user, cursor.lastrowid)


def create_family_access_grant(grantor, data):
    """Grant another active user scoped access for family care coordination."""
    grantor_id = _user_id(grantor)
    if _row_value(grantor, "role") != "patient":
        raise PermissionError("Only patient accounts can grant family care access.")

    grantee_id = data.get("grantee_id")
    grantee_email = str(data.get("grantee_email") or "").strip().lower()
    if grantee_id:
        grantee = get_db().execute("SELECT * FROM users WHERE id=? AND active=1", (int(grantee_id),)).fetchone()
    elif grantee_email:
        grantee = get_db().execute("SELECT * FROM users WHERE email=? AND active=1", (grantee_email,)).fetchone()
    else:
        raise ValueError("grantee_id or grantee_email is required.")
    if not grantee:
        raise LookupError("Family care grantee account not found.")
    if grantee["id"] == grantor_id:
        raise ValueError("Family care access must be granted to another account.")

    family_member_id = data.get("family_member_id")
    if family_member_id:
        get_family_member(grantor, int(family_member_id))
    scopes = _normalize_scopes(data.get("scopes"))
    now = now_iso()
    cursor = get_db().execute(
        """
        INSERT INTO family_access_grants
        (grantor_id, grantee_id, family_member_id, scopes, revoked_at, created_at)
        VALUES (?, ?, ?, ?, NULL, ?)
        """,
        (grantor_id, grantee["id"], int(family_member_id) if family_member_id else None, json.dumps(scopes), now),
    )
    get_db().commit()
    return get_family_access_grant(grantor, cursor.lastrowid)


def _grant_to_dict(row):
    item = dict(row)
    item["scopes"] = _parse_scopes(item.get("scopes"))
    item["active"] = item.get("revoked_at") is None
    return item


def list_family_access_grants(user, direction="given"):
    """List grants the user has given or received."""
    uid = _user_id(user)
    if direction == "received":
        where = "fag.grantee_id=?"
        params = (uid,)
    else:
        where = "fag.grantor_id=?"
        params = (uid,)
    rows = get_db().execute(
        f"""
        SELECT fag.*, grantor.name grantor_name, grantor.email grantor_email,
               grantee.name grantee_name, grantee.email grantee_email,
               fm.member_name, fm.relationship
        FROM family_access_grants fag
        JOIN users grantor ON grantor.id=fag.grantor_id
        JOIN users grantee ON grantee.id=fag.grantee_id
        LEFT JOIN family_members fm ON fm.id=fag.family_member_id
        WHERE {where}
        ORDER BY fag.created_at DESC
        """,
        params,
    ).fetchall()
    return [_grant_to_dict(row) for row in rows]


def get_family_access_grant(user, grant_id):
    uid = _user_id(user)
    row = get_db().execute(
        """
        SELECT fag.*, grantor.name grantor_name, grantor.email grantor_email,
               grantee.name grantee_name, grantee.email grantee_email,
               fm.member_name, fm.relationship
        FROM family_access_grants fag
        JOIN users grantor ON grantor.id=fag.grantor_id
        JOIN users grantee ON grantee.id=fag.grantee_id
        LEFT JOIN family_members fm ON fm.id=fag.family_member_id
        WHERE fag.id=? AND (fag.grantor_id=? OR fag.grantee_id=?)
        """,
        (grant_id, uid, uid),
    ).fetchone()
    if not row:
        raise LookupError("Family access grant not found.")
    return _grant_to_dict(row)


def revoke_family_access_grant(grantor, grant_id):
    grantor_id = _user_id(grantor)
    row = get_db().execute(
        "SELECT id FROM family_access_grants WHERE id=? AND grantor_id=? AND revoked_at IS NULL",
        (grant_id, grantor_id),
    ).fetchone()
    if not row:
        raise LookupError("Active family access grant not found.")
    get_db().execute("UPDATE family_access_grants SET revoked_at=? WHERE id=?", (now_iso(), grant_id))
    get_db().commit()
    return True


def has_family_access(grantor_id, grantee_id, scope):
    if scope not in SCOPES:
        return False
    rows = get_db().execute(
        """
        SELECT scopes, revoked_at FROM family_access_grants
        WHERE grantor_id=? AND grantee_id=? AND revoked_at IS NULL
        ORDER BY created_at DESC
        """,
        (int(grantor_id), int(grantee_id)),
    ).fetchall()
    return any(scope in _parse_scopes(row["scopes"]) for row in rows)


def authorize_family_patient(actor, patient_id=None, scope="care_tasks"):
    """Return a patient id if actor owns the account or has explicit family access."""
    actor_id = _user_id(actor)
    target_id = int(patient_id or actor_id)
    if not actor_id or not target_id:
        raise PermissionError("Authentication required.")
    target = get_db().execute(
        "SELECT id, role, active FROM users WHERE id=? AND role='patient' AND active=1",
        (target_id,),
    ).fetchone()
    if not target:
        raise LookupError("Patient account not found.")
    if actor_id == target_id or _row_value(actor, "role") == "admin":
        return target_id
    if has_family_access(target_id, actor_id, scope):
        return target_id
    raise PermissionError("Explicit family consent is required for this action.")


def list_family_members(user):
    """Return all family members for the user."""
    uid = _user_id(user)
    rows = get_db().execute(
        "SELECT * FROM family_members WHERE user_id=? ORDER BY relationship, member_name",
        (uid,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_family_member(user, member_id):
    """Return details for a single family member. Ensures ownership/permission."""
    uid = _user_id(user)
    row = get_db().execute(
        "SELECT * FROM family_members WHERE id=? AND user_id=?",
        (member_id, uid),
    ).fetchone()
    if not row:
        raise LookupError("Family member not found.")
    return dict(row)


def update_family_member(user, member_id, data):
    """Update family member details."""
    uid = _user_id(user)
    existing = get_family_member(user, member_id)
    name = str(data.get("member_name") or existing["member_name"]).strip()
    relationship = str(data.get("relationship") or existing["relationship"]).strip().lower()
    phone = str(data.get("phone") if "phone" in data else existing.get("phone") or "").strip() or None
    city = str(data.get("city") if "city" in data else existing.get("city") or "").strip() or None
    now = now_iso()

    get_db().execute(
        """UPDATE family_members SET
        member_name=?, relationship=?, phone=?, city=?, updated_at=?
        WHERE id=? AND user_id=?""",
        (name, relationship, phone, city, now, member_id, uid),
    )
    get_db().commit()
    return get_family_member(user, member_id)


def delete_family_member(user, member_id):
    """Delete a family member record."""
    uid = _user_id(user)
    get_family_member(user, member_id)  # raises LookupError if not owned
    get_db().execute("DELETE FROM family_members WHERE id=? AND user_id=?", (member_id, uid))
    get_db().commit()
    return True


# ---------------------------------------------------------------------------
# Family Care Tasks (Remote Parent Care)
# ---------------------------------------------------------------------------

def create_care_task(user, data):
    """Create a care task for a family member / remote parent."""
    uid = _user_id(user)
    title = str(data.get("title") or "").strip()
    if not title:
        raise ValueError("Task title is required.")

    member_id = data.get("family_member_id")
    if member_id:
        get_family_member(user, member_id)

    task_type = str(data.get("task_type") or "general").strip().lower()
    due_date = str(data.get("due_date") or "").strip() or None
    notes = str(data.get("notes") or "").strip() or None

    now = now_iso()
    cursor = get_db().execute(
        """INSERT INTO family_care_tasks
        (user_id, family_member_id, title, task_type, due_date, status, notes, created_at)
        VALUES (?,?,?,?,?,?,?,?)""",
        (uid, member_id, title, task_type, due_date, "pending", notes, now),
    )
    get_db().commit()
    return dict(get_db().execute("SELECT * FROM family_care_tasks WHERE id=?", (cursor.lastrowid,)).fetchone())


def list_care_tasks(user, status=None, member_id=None):
    """List care tasks for the user."""
    uid = _user_id(user)
    conditions = ["fct.user_id=?"]
    params = [uid]

    if status:
        conditions.append("fct.status=?")
        params.append(status)
    if member_id:
        conditions.append("fct.family_member_id=?")
        params.append(member_id)

    where = " WHERE " + " AND ".join(conditions)
    rows = get_db().execute(
        f"""SELECT fct.*, fm.member_name, fm.relationship
           FROM family_care_tasks fct
           LEFT JOIN family_members fm ON fm.id=fct.family_member_id
           {where} ORDER BY fct.created_at DESC""",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def update_care_task_status(user, task_id, status):
    """Mark care task pending, completed, or cancelled."""
    uid = _user_id(user)
    row = get_db().execute("SELECT id FROM family_care_tasks WHERE id=? AND user_id=?", (task_id, uid)).fetchone()
    if not row:
        raise LookupError("Care task not found.")

    new_status = str(status).lower()
    if new_status not in ("pending", "completed", "cancelled"):
        raise ValueError("Invalid status.")

    get_db().execute("UPDATE family_care_tasks SET status=? WHERE id=?", (new_status, task_id))
    get_db().commit()
    return dict(get_db().execute("SELECT * FROM family_care_tasks WHERE id=?", (task_id,)).fetchone())
