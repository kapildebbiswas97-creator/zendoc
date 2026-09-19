"""Versioned public policy acceptance records for ZENDOC accounts."""
from __future__ import annotations

from .db import get_db, now_iso


PRIVACY_POLICY_VERSION = "2026-09-19-v2"
TERMS_POLICY_VERSION = "2026-09-19-v2"
COMMUNITY_GUIDELINES_VERSION = "2026-09-19-v1"


def ensure_policy_acceptance_schema():
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_policy_acceptances (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            policy_type TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            accepted_at TEXT NOT NULL,
            source TEXT NOT NULL,
            PRIMARY KEY (user_id, policy_type, policy_version)
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_policy_acceptances_user
        ON user_policy_acceptances(user_id, accepted_at)
        """
    )


def record_registration_policy_acceptance(user_id: int, *, source: str):
    ensure_policy_acceptance_schema()
    accepted_at = now_iso()
    db = get_db()
    for policy_type, policy_version in (
        ("privacy", PRIVACY_POLICY_VERSION),
        ("terms", TERMS_POLICY_VERSION),
    ):
        db.execute(
            """
            INSERT INTO user_policy_acceptances
            (user_id,policy_type,policy_version,accepted_at,source)
            VALUES (?,?,?,?,?)
            ON CONFLICT(user_id,policy_type,policy_version)
            DO UPDATE SET accepted_at=excluded.accepted_at,source=excluded.source
            """,
            (int(user_id), policy_type, policy_version, accepted_at, str(source or "registration")[:80]),
        )


def list_policy_acceptances(user_id: int) -> list[dict]:
    ensure_policy_acceptance_schema()
    rows = get_db().execute(
        """
        SELECT policy_type,policy_version,accepted_at,source
        FROM user_policy_acceptances
        WHERE user_id=?
        ORDER BY accepted_at,policy_type
        """,
        (int(user_id),),
    ).fetchall()
    return [dict(row) for row in rows]


def record_policy_acceptance(user_id: int, policy_type: str, policy_version: str, *, source: str):
    """Record a bounded, versioned acceptance without inventing consent scope."""
    ensure_policy_acceptance_schema()
    clean_type = str(policy_type or "").strip().lower()[:80]
    clean_version = str(policy_version or "").strip()[:80]
    if not clean_type or not clean_version:
        raise ValueError("Policy type and version are required.")
    get_db().execute(
        """
        INSERT INTO user_policy_acceptances
        (user_id,policy_type,policy_version,accepted_at,source)
        VALUES (?,?,?,?,?)
        ON CONFLICT(user_id,policy_type,policy_version)
        DO UPDATE SET accepted_at=excluded.accepted_at,source=excluded.source
        """,
        (
            int(user_id),
            clean_type,
            clean_version,
            now_iso(),
            str(source or "in_app")[:80],
        ),
    )
