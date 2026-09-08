"""Security-first B2B API client foundation for ZENDOC.

This module does not expose patient or clinical data. It provides partner
identity, hashed API keys, explicit scopes, expiry/revocation, and rate
limiting so future partner APIs have a safe authentication foundation.
"""
from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .db import get_db, now_iso
from .security import assert_owner, hash_token


CLIENT_STATUSES = {"active", "suspended", "revoked"}
ALLOWED_SCOPES = {
    "public_directory.read",
    "provider_profile.read",
    "provider_availability.read",
    "pilot_metrics.read",
}
DEFAULT_SCOPES = {"public_directory.read"}


def create_business_api_client(actor: Any, data: dict) -> dict:
    assert_owner(actor)
    name = str(data.get("name") or "").strip()
    client_type = str(data.get("client_type") or "").strip().lower()
    if not name:
        raise ValueError("name is required.")
    if not client_type:
        raise ValueError("client_type is required.")

    scopes = _normalize_scopes(data.get("allowed_scopes") or list(DEFAULT_SCOPES))
    rate_limit = int(data.get("rate_limit_per_minute") or 60)
    if rate_limit < 1 or rate_limit > 1000:
        raise ValueError("rate_limit_per_minute must be between 1 and 1000.")

    pilot_id = data.get("pilot_id")
    if pilot_id not in (None, ""):
        pilot_id = int(pilot_id)
        pilot = get_db().execute("SELECT id FROM institution_pilots WHERE id=?", (pilot_id,)).fetchone()
        if not pilot:
            raise ValueError("pilot_id does not reference an existing institution pilot.")
    else:
        pilot_id = None

    now = now_iso()
    cursor = get_db().execute(
        """
        INSERT INTO business_api_clients
        (client_uid,name,client_type,pilot_id,status,allowed_scopes_json,rate_limit_per_minute,created_by,created_at,updated_at)
        VALUES (?,?,?,?, 'active', ?,?,?,?,?)
        """,
        (
            f"client_{uuid.uuid4().hex[:20]}",
            name,
            client_type,
            pilot_id,
            json.dumps(sorted(scopes), separators=(",", ":")),
            rate_limit,
            int(actor["id"]),
            now,
            now,
        ),
    )
    get_db().commit()
    return get_business_api_client(int(cursor.lastrowid))


def issue_business_api_key(
    actor: Any,
    client_id: int,
    *,
    expires_in_days: int | None = 90,
) -> dict:
    assert_owner(actor)
    client = get_business_api_client(client_id)
    if client["status"] != "active":
        raise ValueError("API keys may only be issued for active clients.")

    if expires_in_days is None:
        expires_at = None
    else:
        days = int(expires_in_days)
        if days < 1 or days > 3650:
            raise ValueError("expires_in_days must be between 1 and 3650.")
        expires_at = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds")

    raw_secret = "zd_biz_" + secrets.token_urlsafe(32)
    prefix = raw_secret[:16]
    now = now_iso()
    cursor = get_db().execute(
        """
        INSERT INTO business_api_keys
        (client_id,key_prefix,key_hash,status,expires_at,created_by,created_at)
        VALUES (?,?,?,'active',?,?,?)
        """,
        (
            int(client_id),
            prefix,
            hash_token(raw_secret),
            expires_at,
            int(actor["id"]),
            now,
        ),
    )
    get_db().commit()
    return {
        "key_id": int(cursor.lastrowid),
        "client_id": int(client_id),
        "key_prefix": prefix,
        "api_key": raw_secret,
        "expires_at": expires_at,
        "display_notice": "This secret is shown once. ZENDOC stores only its hash.",
    }


def revoke_business_api_key(actor: Any, key_id: int) -> dict:
    assert_owner(actor)
    db = get_db()
    row = db.execute("SELECT * FROM business_api_keys WHERE id=?", (int(key_id),)).fetchone()
    if not row:
        raise LookupError(f"Business API key #{key_id} not found.")
    now = now_iso()
    db.execute(
        "UPDATE business_api_keys SET status='revoked',revoked_at=? WHERE id=?",
        (now, int(key_id)),
    )
    db.commit()
    return {"key_id": int(key_id), "status": "revoked", "revoked_at": now}


def authenticate_business_api_key(
    raw_key: str,
    *,
    required_scope: str | None = None,
    endpoint: str = "",
    method: str = "GET",
) -> dict:
    token = str(raw_key or "").strip()
    if not token:
        raise PermissionError("Business API key is required.")
    db = get_db()
    row = db.execute(
        """
        SELECT k.*,c.name client_name,c.client_uid,c.client_type,c.status client_status,
               c.allowed_scopes_json,c.rate_limit_per_minute,c.pilot_id
        FROM business_api_keys k
        JOIN business_api_clients c ON c.id=k.client_id
        WHERE k.key_hash=?
        LIMIT 1
        """,
        (hash_token(token),),
    ).fetchone()
    if not row or row["status"] != "active" or row["client_status"] != "active":
        raise PermissionError("Business API key is invalid or inactive.")

    if row["expires_at"]:
        expires = _parse_time(row["expires_at"])
        if expires <= datetime.now(timezone.utc):
            raise PermissionError("Business API key has expired.")

    try:
        scopes = set(json.loads(row["allowed_scopes_json"] or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        scopes = set()
    if required_scope and required_scope not in scopes:
        raise PermissionError("Business API client does not have the required scope.")

    _enforce_rate_limit(int(row["client_id"]), int(row["rate_limit_per_minute"] or 60))
    identity = {
        "client_id": int(row["client_id"]),
        "client_uid": row["client_uid"],
        "client_name": row["client_name"],
        "client_type": row["client_type"],
        "pilot_id": row["pilot_id"],
        "key_id": int(row["id"]),
        "scopes": sorted(scopes),
        "rate_limit_per_minute": int(row["rate_limit_per_minute"] or 60),
    }
    _record_usage(identity, endpoint=endpoint, method=method, status_code=200)
    return identity


def business_api_self_usage(identity: dict, *, days: int = 30) -> dict:
    days = max(1, min(int(days or 30), 365))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    db = get_db()
    rows = db.execute(
        """
        SELECT endpoint,method,status_code,created_at
        FROM business_api_usage
        WHERE client_id=? AND created_at>=?
        ORDER BY created_at DESC
        """,
        (int(identity["client_id"]), cutoff),
    ).fetchall()

    endpoint_counts: dict[str, int] = {}
    for row in rows:
        endpoint = str(row["endpoint"] or "")
        endpoint_counts[endpoint] = endpoint_counts.get(endpoint, 0) + 1

    return {
        "client_uid": identity["client_uid"],
        "window_days": days,
        "request_count": len(rows),
        "rate_limit_per_minute": int(identity["rate_limit_per_minute"]),
        "scopes": list(identity["scopes"]),
        "endpoint_counts": endpoint_counts,
        "recent_requests": [dict(row) for row in rows[:50]],
        "truth_notice": (
            "Usage is scoped to this authenticated API client only. No other partner's usage is exposed."
        ),
    }


def list_business_api_clients(actor: Any) -> list[dict]:
    assert_owner(actor)
    rows = get_db().execute(
        "SELECT id FROM business_api_clients ORDER BY created_at DESC"
    ).fetchall()
    return [get_business_api_client(int(row["id"])) for row in rows]


def get_business_api_client(client_id: int) -> dict:
    row = get_db().execute(
        "SELECT * FROM business_api_clients WHERE id=?",
        (int(client_id),),
    ).fetchone()
    if not row:
        raise LookupError(f"Business API client #{client_id} not found.")
    item = dict(row)
    try:
        item["allowed_scopes"] = json.loads(item.pop("allowed_scopes_json") or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        item["allowed_scopes"] = []
    keys = get_db().execute(
        """
        SELECT id,key_prefix,status,expires_at,created_at,revoked_at
        FROM business_api_keys
        WHERE client_id=?
        ORDER BY created_at DESC
        """,
        (int(client_id),),
    ).fetchall()
    item["keys"] = [dict(row) for row in keys]
    return item


def business_api_metrics(actor: Any) -> dict:
    assert_owner(actor)
    db = get_db()
    clients = db.execute("SELECT status FROM business_api_clients").fetchall()
    keys = db.execute("SELECT status,expires_at FROM business_api_keys").fetchall()
    usage_30d = db.execute(
        """
        SELECT COUNT(*) c FROM business_api_usage
        WHERE created_at>=?
        """,
        ((datetime.now(timezone.utc) - timedelta(days=30)).isoformat(timespec="seconds"),),
    ).fetchone()["c"]
    return {
        "client_count": len(clients),
        "active_clients": sum(1 for row in clients if row["status"] == "active"),
        "active_keys": sum(1 for row in keys if row["status"] == "active"),
        "requests_last_30_days": int(usage_30d or 0),
        "truth_notice": (
            "Business API clients currently authenticate only to explicitly scoped endpoints. "
            "No patient or clinical API scope exists in this foundation."
        ),
    }


def _normalize_scopes(value: Any) -> set[str]:
    if isinstance(value, str):
        scopes = {item.strip() for item in value.split(",") if item.strip()}
    elif isinstance(value, (list, tuple, set)):
        scopes = {str(item).strip() for item in value if str(item).strip()}
    else:
        scopes = set()
    invalid = scopes - ALLOWED_SCOPES
    if invalid:
        raise ValueError(f"Unsupported business API scopes: {', '.join(sorted(invalid))}")
    return scopes or set(DEFAULT_SCOPES)


def _enforce_rate_limit(client_id: int, limit: int):
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds")
    count = get_db().execute(
        "SELECT COUNT(*) c FROM business_api_usage WHERE client_id=? AND created_at>=?",
        (int(client_id), cutoff),
    ).fetchone()["c"]
    if int(count or 0) >= int(limit):
        raise PermissionError("Business API rate limit exceeded.")


def _record_usage(identity: dict, *, endpoint: str, method: str, status_code: int):
    get_db().execute(
        """
        INSERT INTO business_api_usage
        (client_id,key_id,endpoint,method,status_code,created_at)
        VALUES (?,?,?,?,?,?)
        """,
        (
            int(identity["client_id"]),
            int(identity["key_id"]),
            str(endpoint or "")[:300],
            str(method or "GET")[:16].upper(),
            int(status_code),
            now_iso(),
        ),
    )
    get_db().commit()


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
