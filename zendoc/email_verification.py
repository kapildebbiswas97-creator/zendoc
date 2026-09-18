"""Versioned email ownership verification for public ZENDOC accounts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .auth import normalize_email
from .db import get_db, now_iso
from .security import hash_token, new_token


EMAIL_VERIFY_TOKEN_TYPE = "email_verify"
EMAIL_VERIFY_MINUTES = 24 * 60


def _value(user: Any, key: str, default=None):
    if user is None:
        return default
    if hasattr(user, "keys") and key in user.keys():
        return user[key]
    if isinstance(user, dict):
        return user.get(key, default)
    return default


def ensure_email_verification_schema():
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_email_verifications (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            verified_email TEXT,
            verified_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_email_verification_verified
        ON user_email_verifications(verified_at, user_id)
        """
    )


def email_verification_status(user: Any) -> dict:
    user_id = int(_value(user, "id", 0) or _value(user, "user_id", 0) or 0)
    email = normalize_email(_value(user, "email_normalized") or _value(user, "email") or "")
    if not user_id or not email:
        return {"verified": False, "verified_at": None, "email": email or None}

    ensure_email_verification_schema()
    row = get_db().execute(
        """
        SELECT verified_email,verified_at,created_at,updated_at
        FROM user_email_verifications
        WHERE user_id=?
        """,
        (user_id,),
    ).fetchone()
    verified = bool(
        row
        and row["verified_at"]
        and normalize_email(row["verified_email"]) == email
    )
    return {
        "verified": verified,
        "verified_at": row["verified_at"] if verified else None,
        "email": email,
    }


def issue_email_verification_token(user: Any) -> str:
    user_id = int(_value(user, "id", 0) or _value(user, "user_id", 0) or 0)
    email = normalize_email(_value(user, "email_normalized") or _value(user, "email") or "")
    if not user_id or not email:
        raise ValueError("A valid user and email are required.")

    ensure_email_verification_schema()
    db = get_db()
    now = now_iso()
    db.execute(
        """
        INSERT INTO user_email_verifications
        (user_id,verified_email,verified_at,created_at,updated_at)
        VALUES (?,?,NULL,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
            verified_email=excluded.verified_email,
            verified_at=CASE
                WHEN user_email_verifications.verified_email=excluded.verified_email
                THEN user_email_verifications.verified_at
                ELSE NULL
            END,
            updated_at=excluded.updated_at
        """,
        (user_id, email, now, now),
    )
    db.execute(
        """
        UPDATE api_tokens
        SET revoked_at=?
        WHERE user_id=? AND token_type=? AND revoked_at IS NULL
        """,
        (now, user_id, EMAIL_VERIFY_TOKEN_TYPE),
    )
    token = new_token()
    expires_at = (
        datetime.now(timezone.utc) + timedelta(minutes=EMAIL_VERIFY_MINUTES)
    ).isoformat(timespec="seconds")
    db.execute(
        """
        INSERT INTO api_tokens
        (user_id,token_hash,token_type,expires_at,created_at)
        VALUES (?,?,?,?,?)
        """,
        (user_id, hash_token(token), EMAIL_VERIFY_TOKEN_TYPE, expires_at, now),
    )
    return token


def verify_email_token(token: str) -> dict:
    digest = hash_token(str(token or ""))
    ensure_email_verification_schema()
    db = get_db()
    row = db.execute(
        """
        SELECT t.id token_id,t.user_id,u.email,u.email_normalized,u.active
        FROM api_tokens t
        JOIN users u ON u.id=t.user_id
        WHERE t.token_hash=? AND t.token_type=? AND t.revoked_at IS NULL
          AND t.expires_at IS NOT NULL AND t.expires_at>?
          AND u.active=1
        """,
        (digest, EMAIL_VERIFY_TOKEN_TYPE, now_iso()),
    ).fetchone()
    if not row:
        raise PermissionError("This email-verification link is invalid or expired.")

    email = normalize_email(row["email_normalized"] or row["email"])
    now = now_iso()
    db.execute(
        """
        INSERT INTO user_email_verifications
        (user_id,verified_email,verified_at,created_at,updated_at)
        VALUES (?,?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
            verified_email=excluded.verified_email,
            verified_at=excluded.verified_at,
            updated_at=excluded.updated_at
        """,
        (int(row["user_id"]), email, now, now, now),
    )
    db.execute(
        """
        UPDATE api_tokens
        SET revoked_at=?
        WHERE user_id=? AND token_type=? AND revoked_at IS NULL
        """,
        (now, int(row["user_id"]), EMAIL_VERIFY_TOKEN_TYPE),
    )
    db.commit()
    return {
        "status": "verified",
        "user_id": int(row["user_id"]),
        "email": email,
        "verified_at": now,
    }
