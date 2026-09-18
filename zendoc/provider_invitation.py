"""Owner-controlled provider account invitations for public ZENDOC."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from werkzeug.security import generate_password_hash

from .auth import normalize_email, validate_email
from .db import get_db, now_iso
from .email_verification import mark_email_verified
from .policy_acceptance import record_registration_policy_acceptance
from .security import hash_token, new_token


INVITABLE_PROVIDER_ROLES = {"doctor", "hospital", "pharmacy", "government"}
INVITE_TOKEN_TYPE = "provider_invite"
INVITE_HOURS = 72


def ensure_provider_invitation_schema():
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS provider_invitations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            email_normalized TEXT NOT NULL,
            role TEXT NOT NULL,
            invited_name TEXT,
            invited_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            accepted_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            accepted_at TEXT,
            revoked_at TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_provider_invitations_email
        ON provider_invitations(email_normalized, role, revoked_at, accepted_at)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_provider_invitations_expiry
        ON provider_invitations(expires_at, accepted_at, revoked_at)
        """
    )


def _user_id(actor: Any) -> int:
    try:
        return int(actor["id"])
    except Exception:
        return 0


def create_provider_invitation(
    actor: Any,
    *,
    email: str,
    role: str,
    invited_name: str | None = None,
) -> tuple[str, dict]:
    ensure_provider_invitation_schema()
    role = str(role or "").strip().lower()
    if role not in INVITABLE_PROVIDER_ROLES:
        raise ValueError("Controlled invitation role must be doctor, hospital, pharmacy, or government.")
    email = validate_email(email)

    db = get_db()
    existing = db.execute(
        """
        SELECT id,active FROM users
        WHERE email_normalized=? OR LOWER(TRIM(email))=?
        ORDER BY id LIMIT 1
        """,
        (email, email),
    ).fetchone()
    if existing:
        raise ValueError("An account with this email already exists.")

    now = now_iso()
    db.execute(
        """
        UPDATE provider_invitations
        SET revoked_at=?
        WHERE email_normalized=? AND accepted_at IS NULL AND revoked_at IS NULL
        """,
        (now, email),
    )

    token = new_token()
    expires_at = (
        datetime.now(timezone.utc) + timedelta(hours=INVITE_HOURS)
    ).isoformat(timespec="seconds")
    cursor = db.execute(
        """
        INSERT INTO provider_invitations
        (email,email_normalized,role,invited_name,invited_by,token_hash,expires_at,created_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            email,
            email,
            role,
            str(invited_name or "").strip()[:160] or None,
            _user_id(actor) or None,
            hash_token(token),
            expires_at,
            now,
        ),
    )
    db.commit()
    return token, get_provider_invitation(int(cursor.lastrowid))


def get_provider_invitation(invitation_id: int) -> dict:
    ensure_provider_invitation_schema()
    row = get_db().execute(
        """
        SELECT i.*,u.name invited_by_name
        FROM provider_invitations i
        LEFT JOIN users u ON u.id=i.invited_by
        WHERE i.id=?
        """,
        (int(invitation_id),),
    ).fetchone()
    if not row:
        raise LookupError("Provider invitation not found.")
    return dict(row)


def resolve_provider_invitation(token: str) -> dict:
    ensure_provider_invitation_schema()
    row = get_db().execute(
        """
        SELECT i.*,u.name invited_by_name
        FROM provider_invitations i
        LEFT JOIN users u ON u.id=i.invited_by
        WHERE i.token_hash=? AND i.accepted_at IS NULL AND i.revoked_at IS NULL
          AND i.expires_at>?
        """,
        (hash_token(str(token or "")), now_iso()),
    ).fetchone()
    if not row:
        raise PermissionError("This provider invitation is invalid, expired, revoked, or already used.")
    return dict(row)


def accept_provider_invitation(
    token: str,
    *,
    name: str,
    password: str,
    accept_privacy: bool,
    accept_terms: bool,
) -> dict:
    invite = resolve_provider_invitation(token)
    if not accept_privacy or not accept_terms:
        raise ValueError("Privacy Policy and Terms of Service acceptance are required.")
    name = str(name or "").strip()
    if not name:
        raise ValueError("Name is required.")
    if len(str(password or "")) < 8:
        raise ValueError("Password must be at least 8 characters.")

    db = get_db()
    email = normalize_email(invite["email_normalized"] or invite["email"])
    existing = db.execute(
        """
        SELECT id FROM users
        WHERE email_normalized=? OR LOWER(TRIM(email))=?
        ORDER BY id LIMIT 1
        """,
        (email, email),
    ).fetchone()
    if existing:
        raise ValueError("An account with this email already exists.")

    now = now_iso()
    cursor = db.execute(
        """
        INSERT INTO users
        (name,email,email_normalized,password_hash,role,verified,active,created_at,updated_at)
        VALUES (?,?,?,?,?,0,1,?,?)
        """,
        (
            name[:160],
            email,
            email,
            generate_password_hash(str(password)),
            invite["role"],
            now,
            now,
        ),
    )
    user_id = int(cursor.lastrowid)
    record_registration_policy_acceptance(user_id, source="provider_invitation")
    mark_email_verified(user_id, email)
    db.execute(
        """
        UPDATE provider_invitations
        SET accepted_user_id=?,accepted_at=?
        WHERE id=? AND accepted_at IS NULL AND revoked_at IS NULL
        """,
        (user_id, now, int(invite["id"])),
    )
    db.execute(
        """
        UPDATE provider_invitations
        SET revoked_at=?
        WHERE email_normalized=? AND id<>? AND accepted_at IS NULL AND revoked_at IS NULL
        """,
        (now, email, int(invite["id"])),
    )
    db.commit()
    user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    is_provider_role = str(invite["role"]) in {"doctor", "hospital", "pharmacy"}
    return {
        "status": "accepted",
        "user": dict(user),
        "invitation_id": int(invite["id"]),
        "provider_verification_status": "profile_required" if is_provider_role else "not_applicable",
        "truth_notice": (
            "Accepting the invitation creates the account and proves control of the invited email. "
            + (
                "It does not verify professional credentials or make the provider publicly bookable."
                if is_provider_role
                else "It does not grant provider verification, clinical authority, or owner/admin privileges."
            )
        ),
    }


def list_provider_invitations(limit: int = 100) -> list[dict]:
    ensure_provider_invitation_schema()
    limit = max(1, min(int(limit or 100), 300))
    rows = get_db().execute(
        """
        SELECT i.*,u.name invited_by_name,a.name accepted_user_name
        FROM provider_invitations i
        LEFT JOIN users u ON u.id=i.invited_by
        LEFT JOIN users a ON a.id=i.accepted_user_id
        ORDER BY i.created_at DESC,i.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]
