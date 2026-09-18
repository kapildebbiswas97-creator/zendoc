"""Account lifecycle and deletion controls for ZENDOC.

Deletion is deliberately separate from deactivation. For ordinary user accounts,
this service removes the account plus directly associated ZENDOC data and
uploaded files that the account owns. Cross-user operational records that another
patient needs (for example an appointment with a provider who later deletes
their account) are retained only in de-identified form.

The configured owner/admin account cannot be deleted through this service.
"""
from __future__ import annotations

from typing import Any

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db, now_iso
from .record_storage import get_record_storage
from .security import hash_token, is_owner, new_token


DELETE_TOKEN_TYPE = "account_delete"
DELETE_TOKEN_MINUTES = 60


def _value(user: Any, key: str, default=None):
    if user is None:
        return default
    if hasattr(user, "keys") and key in user.keys():
        return user[key]
    if isinstance(user, dict):
        return user.get(key, default)
    return default


def _load_user(user_id: int):
    row = get_db().execute("SELECT * FROM users WHERE id=?", (int(user_id),)).fetchone()
    if not row:
        raise LookupError("Account not found.")
    return row


def create_account_deletion_token(email_normalized: str) -> tuple[str, Any] | None:
    email = str(email_normalized or "").strip().lower()
    if not email:
        return None
    user = get_db().execute(
        "SELECT * FROM users WHERE email_normalized=? AND active=1",
        (email,),
    ).fetchone()
    if not user or is_owner(user):
        return None

    token = new_token()
    digest = hash_token(token)
    db = get_db()
    db.execute(
        "UPDATE api_tokens SET revoked_at=? WHERE user_id=? AND token_type=? AND revoked_at IS NULL",
        (now_iso(), int(user["id"]), DELETE_TOKEN_TYPE),
    )
    # SQLite and PostgreSQL both accept datetime text in the canonical ISO form
    # used by the rest of ZENDOC. Keep token expiry creation in SQL-independent
    # Python via the existing helper import to avoid dialect-specific intervals.
    from datetime import datetime, timedelta, timezone

    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=DELETE_TOKEN_MINUTES)).isoformat(timespec="seconds")
    db.execute(
        """
        INSERT INTO api_tokens (user_id,token_hash,token_type,expires_at,created_at)
        VALUES (?,?,?,?,?)
        """,
        (int(user["id"]), digest, DELETE_TOKEN_TYPE, expires_at, now_iso()),
    )
    db.commit()
    return token, user


def resolve_account_deletion_token(token: str):
    digest = hash_token(str(token or ""))
    row = get_db().execute(
        """
        SELECT t.*,u.name,u.email,u.email_normalized,u.password_hash,u.role,u.active
        FROM api_tokens t
        JOIN users u ON u.id=t.user_id
        WHERE t.token_hash=? AND t.token_type=? AND t.revoked_at IS NULL
          AND t.expires_at IS NOT NULL AND t.expires_at>?
          AND u.active=1
        """,
        (digest, DELETE_TOKEN_TYPE, now_iso()),
    ).fetchone()
    if not row:
        raise PermissionError("This account-deletion link is invalid or expired.")
    if is_owner(row):
        raise PermissionError("The configured owner account cannot be deleted here.")
    return row


def _owned_record_storage_keys(user_id: int) -> list[str]:
    rows = get_db().execute(
        "SELECT stored_filename FROM medical_records WHERE owner_id=? ORDER BY id",
        (int(user_id),),
    ).fetchall()
    return [str(row["stored_filename"]) for row in rows if row["stored_filename"]]


def _delete_owned_files(user_id: int) -> int:
    keys = _owned_record_storage_keys(user_id)
    if not keys:
        return 0
    storage = get_record_storage()
    status = storage.status()
    if status.get("status") == "integration_required":
        raise RuntimeError(
            "Account deletion cannot complete while the configured medical-record storage provider is unavailable."
        )
    deleted = 0
    for key in keys:
        storage.delete(key)
        deleted += 1
    return deleted


def _delete_directly_attributed_rows(user_id: int):
    """Remove rows that would otherwise survive via ON DELETE SET NULL.

    Rows that are part of another patient's required operational history are
    allowed to survive only after their direct user reference is nulled by the
    database FK. Tables below contain interaction/log/personal payloads that
    should not survive account deletion merely because their FK is nullable.
    """
    db = get_db()
    statements = (
        ("DELETE FROM ai_interactions WHERE user_id=?", (user_id,)),
        ("DELETE FROM audit_logs WHERE actor_id=?", (user_id,)),
        ("DELETE FROM agent_actions WHERE actor_id=?", (user_id,)),
        ("DELETE FROM agent_tool_calls WHERE actor_id=?", (user_id,)),
        ("DELETE FROM agent_approvals WHERE actor_id=? OR requested_by_user_id=? OR approver_user_id=? OR resolved_by=?",
         (user_id, user_id, user_id, user_id)),
        ("DELETE FROM agent_tasks WHERE requested_by=?", (user_id,)),
        ("DELETE FROM agent_runs WHERE actor_id=?", (user_id,)),
        ("DELETE FROM platform_events WHERE actor_id=?", (user_id,)),
        ("DELETE FROM video_search_history WHERE user_id=?", (user_id,)),
        ("DELETE FROM model_execution_logs WHERE actor_id=?", (user_id,)),
        ("DELETE FROM model_evaluation_runs WHERE requested_by=?", (user_id,)),
        ("DELETE FROM staff_task_events WHERE actor_id=?", (user_id,)),
        ("DELETE FROM staff_tasks WHERE patient_id=? OR assigned_staff_id=?", (user_id, user_id)),
        ("DELETE FROM product_analytics_events WHERE user_id=?", (user_id,)),
        ("DELETE FROM product_feedback WHERE user_id=?", (user_id,)),
        ("DELETE FROM request_observations WHERE actor_id=?", (user_id,)),
        ("DELETE FROM user_email_verifications WHERE user_id=?", (user_id,)),
        ("DELETE FROM user_policy_acceptances WHERE user_id=?", (user_id,)),
    )
    for sql, params in statements:
        db.execute(sql, params)


def delete_account(user: Any, *, password: str | None = None, token_authorized: bool = False) -> dict:
    user_id = int(_value(user, "user_id", 0) or _value(user, "id", 0) or 0)
    if not user_id:
        raise PermissionError("Authentication is required.")
    persisted = _load_user(user_id)
    if is_owner(persisted) or str(persisted["role"]) == "admin":
        raise PermissionError("Admin/owner deletion is not available through the public account-deletion flow.")

    if not token_authorized:
        if not password or not check_password_hash(persisted["password_hash"], str(password)):
            raise PermissionError("Your current password is required to delete this account.")

    # Remove account-owned files before the database rows that reference them.
    # If storage is unavailable, fail closed instead of claiming deletion.
    deleted_files = _delete_owned_files(user_id)

    db = get_db()
    role = str(persisted["role"] or "")
    email = str(persisted["email_normalized"] or persisted["email"] or "").strip().lower()

    try:
        _delete_directly_attributed_rows(user_id)

        provider_tombstone = role in {"doctor", "hospital", "pharmacy", "government"}

        # Provider/staff accounts can be referenced by another patient's
        # appointment, uploaded report, message or operational history. Hard
        # deletion could cascade-delete that patient's data because some older
        # schema relations are intentionally NOT NULL. In that case erase the
        # account identity and credentials while preserving only a de-identified,
        # inactive FK anchor.
        if provider_tombstone:
            db.execute(
                """
                UPDATE appointments
                SET provider_name='Former ZENDOC provider',
                    provider_id=NULL,
                    provider_profile_id=NULL,
                    updated_at=?
                WHERE provider_id=?
                """,
                (now_iso(), user_id),
            )
            db.execute("DELETE FROM provider_profiles WHERE user_id=?", (user_id,))
            db.execute("DELETE FROM api_tokens WHERE user_id=?", (user_id,))
            db.execute("DELETE FROM organization_memberships WHERE user_id=?", (user_id,))
            db.execute("UPDATE provider_network_prospects SET linked_user_id=NULL WHERE linked_user_id=?", (user_id,))

        if email:
            db.execute(
                "DELETE FROM duplicate_account_groups WHERE email_normalized=? OR primary_user_id=?",
                (email, user_id),
            )

        if provider_tombstone:
            tombstone_email = f"deleted-provider-{user_id}@zendoc.invalid"
            db.execute(
                """
                UPDATE users
                SET name='Former ZENDOC provider',
                    email=?,email_normalized=?,duplicate_of_user_id=NULL,
                    password_hash=?,phone=NULL,age=NULL,gender=NULL,city=NULL,
                    emergency_contact=NULL,verified=0,active=0,updated_at=?
                WHERE id=?
                """,
                (
                    tombstone_email,
                    tombstone_email,
                    generate_password_hash(new_token()),
                    now_iso(),
                    user_id,
                ),
            )
        else:
            deleted = db.execute("DELETE FROM users WHERE id=?", (user_id,))
            if int(getattr(deleted, "rowcount", 0) or 0) != 1:
                raise RuntimeError("Account deletion did not remove exactly one account.")
        db.commit()
    except Exception:
        db.rollback()
        current_app.logger.exception("Account deletion failed for user_id=%s", user_id)
        raise

    retained_tombstone = role in {"doctor", "hospital", "pharmacy", "government"}
    return {
        "status": "deleted",
        "account_id": user_id,
        "role": role,
        "owned_record_files_deleted": deleted_files,
        "deidentified_operational_anchor_retained": retained_tombstone,
        "notice": (
            "The ZENDOC account credentials and directly associated application data were deleted. "
            "Where another user's care history depends on a former provider/staff reference, only a "
            "de-identified inactive operational anchor is retained."
            if retained_tombstone
            else
            "The ZENDOC account and directly associated application data were deleted. "
            "Operational records needed by another user's care history may remain only in de-identified form."
        ),
    }
