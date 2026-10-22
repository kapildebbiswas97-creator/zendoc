"""Owner-controlled invitation-based registration for ZENDOC beta launch.

Provides secure, single-use, expiring invitations with hashed storage, optional
email binding, atomic consumption to prevent token reuse or concurrent double
redemption, and audit logging.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from .auth import normalize_email, validate_email
from .db import get_db, now_iso
from .security import hash_token


BETA_TOKEN_PREFIX = "znd_beta_"
DEFAULT_INVITE_EXPIRY_DAYS = 7


def ensure_beta_invitation_schema(db=None):
    if db is None:
        db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS beta_invitations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT NOT NULL UNIQUE,
            email TEXT,
            email_normalized TEXT,
            role TEXT NOT NULL DEFAULT 'patient',
            notes TEXT,
            invited_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            expires_at TEXT NOT NULL,
            redeemed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            redeemed_at TEXT,
            revoked_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_beta_invitations_token_hash
        ON beta_invitations(token_hash)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_beta_invitations_email
        ON beta_invitations(email_normalized)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_beta_invitations_expiry
        ON beta_invitations(expires_at, redeemed_at, revoked_at)
        """
    )


def _user_id(actor: Any) -> int | None:
    if actor is None:
        return None
    try:
        return int(actor["id"])
    except (KeyError, TypeError, IndexError, ValueError):
        return None


def hash_beta_token(token: str) -> str:
    cleaned = str(token or "").strip()
    return hash_token(cleaned)


def create_beta_invitation(
    actor: Any,
    *,
    email: str | None = None,
    role: str = "patient",
    expires_in_days: int = DEFAULT_INVITE_EXPIRY_DAYS,
    notes: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Create a new secure, single-use, expiring beta invitation.

    The raw token is returned once and NEVER stored in plaintext.
    Only its SHA-256 hash is persisted.
    """
    ensure_beta_invitation_schema()
    db = get_db()

    email_clean = None
    email_norm = None
    if email and str(email).strip():
        email_clean = validate_email(str(email).strip())
        email_norm = normalize_email(email_clean)

    role_clean = str(role or "patient").strip().lower()
    if role_clean not in {"patient", "doctor", "hospital", "pharmacy", "government"}:
        raise ValueError("Invalid account role for beta invitation.")

    days = max(1, min(int(expires_in_days or DEFAULT_INVITE_EXPIRY_DAYS), 90))
    now = now_iso()
    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=days)
    ).isoformat(timespec="seconds")

    raw_token = f"{BETA_TOKEN_PREFIX}{secrets.token_urlsafe(24)}"
    token_digest = hash_beta_token(raw_token)

    actor_id = _user_id(actor)
    notes_clean = str(notes or "").strip()[:500] or None

    cursor = db.execute(
        """
        INSERT INTO beta_invitations
        (token_hash, email, email_normalized, role, notes, invited_by, expires_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            token_digest,
            email_clean,
            email_norm,
            role_clean,
            notes_clean,
            actor_id,
            expires_at,
            now,
            now,
        ),
    )
    invitation_id = int(cursor.lastrowid)

    # Audit logging
    db.execute(
        """
        INSERT INTO audit_logs (actor_id, action, entity_type, entity_id, created_at)
        VALUES (?, 'create_beta_invitation', 'beta_invitation', ?, ?)
        """,
        (actor_id, str(invitation_id), now),
    )
    db.commit()

    return raw_token, get_beta_invitation(invitation_id)


def get_beta_invitation(invitation_id: int) -> dict[str, Any]:
    ensure_beta_invitation_schema()
    row = get_db().execute(
        """
        SELECT b.*, u.name AS invited_by_name, u.email AS invited_by_email,
               r.name AS redeemed_by_name, r.email AS redeemed_by_email
        FROM beta_invitations b
        LEFT JOIN users u ON u.id = b.invited_by
        LEFT JOIN users r ON r.id = b.redeemed_by
        WHERE b.id = ?
        """,
        (int(invitation_id),),
    ).fetchone()
    if not row:
        raise LookupError("Beta invitation not found.")
    return dict(row)


def list_beta_invitations(limit: int = 100) -> list[dict[str, Any]]:
    ensure_beta_invitation_schema()
    rows = get_db().execute(
        """
        SELECT b.*, u.name AS invited_by_name, u.email AS invited_by_email,
               r.name AS redeemed_by_name, r.email AS redeemed_by_email
        FROM beta_invitations b
        LEFT JOIN users u ON u.id = b.invited_by
        LEFT JOIN users r ON r.id = b.redeemed_by
        ORDER BY b.id DESC
        LIMIT ?
        """,
        (max(1, min(int(limit), 500)),),
    ).fetchall()
    return [dict(r) for r in rows]


def revoke_beta_invitation(actor: Any, invitation_id: int) -> dict[str, Any]:
    """Revoke an active beta invitation."""
    ensure_beta_invitation_schema()
    db = get_db()
    now = now_iso()
    actor_id = _user_id(actor)

    row = db.execute(
        "SELECT * FROM beta_invitations WHERE id = ?",
        (int(invitation_id),),
    ).fetchone()
    if not row:
        raise LookupError("Beta invitation not found.")
    if row["redeemed_at"]:
        raise ValueError("Cannot revoke an invitation that has already been redeemed.")
    if row["revoked_at"]:
        return dict(row)

    db.execute(
        "UPDATE beta_invitations SET revoked_at = ?, updated_at = ? WHERE id = ?",
        (now, now, int(invitation_id)),
    )
    db.execute(
        """
        INSERT INTO audit_logs (actor_id, action, entity_type, entity_id, created_at)
        VALUES (?, 'revoke_beta_invitation', 'beta_invitation', ?, ?)
        """,
        (actor_id, str(invitation_id), now),
    )
    db.commit()
    return get_beta_invitation(int(invitation_id))


def resolve_beta_invitation(
    raw_token: str,
    *,
    expected_email: str | None = None,
    expected_role: str = "patient",
) -> dict[str, Any]:
    """Validate a beta invitation token without redeeming it.

    Raises ValueError with a user-safe message if invalid, expired, revoked,
    already redeemed, or mismatched.
    """
    token_str = str(raw_token or "").strip()
    if not token_str:
        raise ValueError("Beta invitation code is required.")

    ensure_beta_invitation_schema()
    digest = hash_beta_token(token_str)

    row = get_db().execute(
        "SELECT * FROM beta_invitations WHERE token_hash = ?",
        (digest,),
    ).fetchone()

    if not row:
        raise ValueError("Invalid beta invitation code.")

    invitation = dict(row)
    if invitation.get("revoked_at"):
        raise ValueError("This beta invitation code has been revoked.")

    if invitation.get("redeemed_at"):
        raise ValueError("This beta invitation code has already been used.")

    now = now_iso()
    if str(invitation.get("expires_at", "")) <= now:
        raise ValueError("This beta invitation code has expired.")

    if expected_role and invitation.get("role"):
        if str(invitation["role"]).lower() != str(expected_role).lower():
            raise ValueError("This invitation code is not valid for the requested account role.")

    if invitation.get("email_normalized"):
        if not expected_email:
            raise ValueError("This invitation code is bound to a specific email address.")
        expected_norm = normalize_email(str(expected_email).strip())
        if expected_norm != invitation["email_normalized"]:
            raise ValueError("This invitation code was issued for another email address.")

    return invitation


def redeem_beta_invitation(
    raw_token: str,
    user_id: int,
    *,
    email: str | None = None,
    role: str = "patient",
) -> dict[str, Any]:
    """Atomically redeem a beta invitation.

    Prevents token reuse and concurrent double redemption.
    """
    token_str = str(raw_token or "").strip()
    if not token_str:
        raise ValueError("Beta invitation code is required.")

    ensure_beta_invitation_schema()
    digest = hash_beta_token(token_str)
    now = now_iso()
    db = get_db()

    email_norm = normalize_email(str(email).strip()) if email and str(email).strip() else None
    role_clean = str(role or "patient").strip().lower()

    # Atomic single-use consumption query:
    # Only updates if redeemed_at is currently NULL, not revoked, and not expired.
    if email_norm:
        cursor = db.execute(
            """
            UPDATE beta_invitations
            SET redeemed_by = ?, redeemed_at = ?, updated_at = ?
            WHERE token_hash = ?
              AND redeemed_at IS NULL
              AND revoked_at IS NULL
              AND expires_at > ?
              AND (email_normalized IS NULL OR email_normalized = ?)
              AND (role IS NULL OR role = ?)
            """,
            (int(user_id), now, now, digest, now, email_norm, role_clean),
        )
    else:
        cursor = db.execute(
            """
            UPDATE beta_invitations
            SET redeemed_by = ?, redeemed_at = ?, updated_at = ?
            WHERE token_hash = ?
              AND redeemed_at IS NULL
              AND revoked_at IS NULL
              AND expires_at > ?
              AND email_normalized IS NULL
              AND (role IS NULL OR role = ?)
            """,
            (int(user_id), now, now, digest, now, role_clean),
        )

    if cursor.rowcount == 0:
        # Check specific reason to give precise error
        resolve_beta_invitation(token_str, expected_email=email, expected_role=role)
        # If resolve didn't raise, concurrent redemption happened:
        raise ValueError("This invitation code has already been redeemed.")

    # Record audit log
    db.execute(
        """
        INSERT INTO audit_logs (actor_id, action, entity_type, entity_id, created_at)
        VALUES (?, 'redeem_beta_invitation', 'beta_invitation', (SELECT CAST(id AS TEXT) FROM beta_invitations WHERE token_hash=?), ?)
        """,
        (int(user_id), digest, now),
    )
    db.commit()

    row = db.execute("SELECT * FROM beta_invitations WHERE token_hash = ?", (digest,)).fetchone()
    return dict(row) if row else {}
