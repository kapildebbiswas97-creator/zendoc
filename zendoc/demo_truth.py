"""Shared truth helpers for development-only synthetic competition fixtures.

Synthetic demo records are useful for deterministic product demonstrations, but
must never inflate startup traction, provider-network, retention, launch, pilot
or investor evidence.
"""
from __future__ import annotations

from typing import Any

from .db import get_db


SYNTHETIC_DEMO_EMAILS = frozenset({
    "demo-doctor@zendoc.local",
    "demo-patient@zendoc.local",
})
SYNTHETIC_DEMO_LICENSES = frozenset({"DEMO-NOT-A-LICENSE"})


def is_synthetic_demo_email(value: Any) -> bool:
    return str(value or "").strip().lower() in SYNTHETIC_DEMO_EMAILS


def is_synthetic_demo_license(value: Any) -> bool:
    return str(value or "").strip().upper() in SYNTHETIC_DEMO_LICENSES


def synthetic_demo_user_ids(db=None) -> set[int]:
    db = db or get_db()
    placeholders = ",".join("?" for _ in SYNTHETIC_DEMO_EMAILS)
    rows = db.execute(
        f"""
        SELECT id FROM users
        WHERE LOWER(COALESCE(email_normalized,email,'')) IN ({placeholders})
        """,
        sorted(SYNTHETIC_DEMO_EMAILS),
    ).fetchall()
    return {int(row["id"]) for row in rows}


def synthetic_demo_provider_profile_ids(db=None) -> set[int]:
    db = db or get_db()
    demo_users = synthetic_demo_user_ids(db)
    rows = db.execute(
        "SELECT id,user_id,license_identifier FROM provider_profiles"
    ).fetchall()
    return {
        int(row["id"])
        for row in rows
        if (
            int(row["user_id"] or 0) in demo_users
            or is_synthetic_demo_license(row["license_identifier"])
        )
    }


def exclude_synthetic_ids(values, synthetic_ids: set[int]) -> list[int]:
    result = []
    for value in values:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed not in synthetic_ids:
            result.append(parsed)
    return result
