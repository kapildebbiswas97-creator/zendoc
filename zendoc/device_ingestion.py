"""Trusted per-device ingestion bridge for health measurements.

This is a vendor-neutral bridge: a linked device gets a revocable, hashed,
one-time-shown ingestion key. The key identifies exactly one user-owned device,
so callers cannot choose an arbitrary patient/device id. Vendor-specific OAuth
or mobile SDK adapters can forward into this boundary without weakening Health
Memory ownership rules.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, g, jsonify, request

from .db import get_db, is_integrity_error, now_iso
from .health_analytics import create_measurement
from .routes import require_api_user
from .security import hash_token


bp = Blueprint("device_ingestion", __name__)
MAX_EVENTS_PER_MINUTE = 120


def ensure_device_ingestion_schema() -> None:
    get_db().executescript(
        """
        CREATE TABLE IF NOT EXISTS device_ingestion_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL REFERENCES health_devices(id) ON DELETE CASCADE,
            key_prefix TEXT NOT NULL,
            key_hash TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            last_used_at TEXT,
            revoked_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_device_ingestion_keys_device
            ON device_ingestion_keys(device_id,status);

        CREATE TABLE IF NOT EXISTS device_ingestion_receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL REFERENCES health_devices(id) ON DELETE CASCADE,
            event_id TEXT NOT NULL,
            metric_id INTEGER NOT NULL REFERENCES health_metrics(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            UNIQUE(device_id,event_id)
        );
        CREATE INDEX IF NOT EXISTS idx_device_ingestion_receipts_device_time
            ON device_ingestion_receipts(device_id,created_at);
        """
    )


def _owned_device(actor, device_id: int):
    row = get_db().execute(
        """
        SELECT d.*,u.role,u.active
        FROM health_devices d
        JOIN users u ON u.id=d.user_id
        WHERE d.id=? AND d.user_id=? AND u.active=1
        """,
        (int(device_id), int(actor["id"])),
    ).fetchone()
    if not row:
        raise LookupError("Device not found for this account.")
    if str(row["role"]) != "patient":
        raise PermissionError("Only patient-owned devices can use device ingestion keys.")
    return row


def issue_device_ingestion_key(actor, device_id: int) -> dict:
    ensure_device_ingestion_schema()
    device = _owned_device(actor, device_id)
    raw = "zd_dev_" + secrets.token_urlsafe(36)
    prefix = raw[:18]
    now = now_iso()
    db = get_db()
    db.execute(
        """
        UPDATE device_ingestion_keys
        SET status='revoked',revoked_at=?
        WHERE device_id=? AND status='active'
        """,
        (now, int(device["id"])),
    )
    cursor = db.execute(
        """
        INSERT INTO device_ingestion_keys
        (device_id,key_prefix,key_hash,status,created_at)
        VALUES (?,?,?,'active',?)
        """,
        (int(device["id"]), prefix, hash_token(raw), now),
    )
    db.commit()
    return {
        "key_id": int(cursor.lastrowid),
        "device_id": int(device["id"]),
        "key_prefix": prefix,
        "ingestion_key": raw,
        "display_notice": (
            "This device key is shown once. ZENDOC stores only its hash. "
            "Rotating the key immediately revokes the previous active key."
        ),
    }


def revoke_device_ingestion_keys(actor, device_id: int) -> dict:
    ensure_device_ingestion_schema()
    device = _owned_device(actor, device_id)
    now = now_iso()
    cursor = get_db().execute(
        """
        UPDATE device_ingestion_keys
        SET status='revoked',revoked_at=COALESCE(revoked_at,?)
        WHERE device_id=? AND status='active'
        """,
        (now, int(device["id"])),
    )
    get_db().commit()
    return {"device_id": int(device["id"]), "revoked_count": int(cursor.rowcount or 0)}


def _authenticate_device_key(raw_key: str):
    token = str(raw_key or "").strip()
    if not token:
        raise PermissionError("Device ingestion key is required.")
    ensure_device_ingestion_schema()
    row = get_db().execute(
        """
        SELECT k.id key_id,k.device_id,k.status,d.user_id,d.device_name,d.device_type,
               d.manufacturer,d.model,d.status device_status,u.role,u.active
        FROM device_ingestion_keys k
        JOIN health_devices d ON d.id=k.device_id
        JOIN users u ON u.id=d.user_id
        WHERE k.key_hash=?
        LIMIT 1
        """,
        (hash_token(token),),
    ).fetchone()
    if not row or str(row["status"]) != "active" or not bool(row["active"]):
        raise PermissionError("Device ingestion key is invalid or inactive.")
    if str(row["role"]) != "patient":
        raise PermissionError("Device ingestion owner is not an active patient account.")
    return row


def _enforce_device_rate_limit(device_id: int) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds")
    count = get_db().execute(
        """
        SELECT COUNT(*) c FROM device_ingestion_receipts
        WHERE device_id=? AND created_at>=?
        """,
        (int(device_id), cutoff),
    ).fetchone()["c"]
    if int(count or 0) >= MAX_EVENTS_PER_MINUTE:
        raise PermissionError("Device ingestion rate limit exceeded.")


def ingest_device_measurement(raw_key: str, payload: dict) -> dict:
    identity = _authenticate_device_key(raw_key)
    _enforce_device_rate_limit(int(identity["device_id"]))

    event_id = str((payload or {}).get("event_id") or "").strip()
    if not event_id or len(event_id) > 160:
        raise ValueError("event_id is required and must be at most 160 characters.")

    db = get_db()
    existing = db.execute(
        """
        SELECT r.metric_id,m.metric_type,m.metric_value,m.unit,m.recorded_at
        FROM device_ingestion_receipts r
        JOIN health_metrics m ON m.id=r.metric_id
        WHERE r.device_id=? AND r.event_id=?
        """,
        (int(identity["device_id"]), event_id),
    ).fetchone()
    if existing:
        return {
            "duplicate": True,
            "device_id": int(identity["device_id"]),
            "metric_id": int(existing["metric_id"]),
            "metric_type": existing["metric_type"],
            "recorded_at": existing["recorded_at"],
        }

    user = db.execute(
        "SELECT * FROM users WHERE id=? AND active=1",
        (int(identity["user_id"]),),
    ).fetchone()
    if not user:
        raise PermissionError("Device owner account is inactive.")

    measurement = {
        "metric_type": (payload or {}).get("metric_type"),
        "value": (payload or {}).get("value", (payload or {}).get("metric_value")),
        "secondary_value": (payload or {}).get("secondary_value"),
        "unit": (payload or {}).get("unit"),
        "recorded_at": (payload or {}).get("recorded_at"),
        "source": "device",
        "notes": (
            f"Trusted device bridge: {str(identity['device_type'] or 'device')[:80]}"
        ),
    }
    metric_id = create_measurement(
        user,
        measurement,
        patient_id=int(identity["user_id"]),
        trusted_source=True,
        commit=False,
    )
    now = now_iso()
    try:
        db.execute(
            """
            INSERT INTO device_ingestion_receipts
            (device_id,event_id,metric_id,created_at)
            VALUES (?,?,?,?)
            """,
            (int(identity["device_id"]), event_id, int(metric_id), now),
        )
    except Exception as exc:
        if is_integrity_error(exc):
            db.rollback()
            duplicate = db.execute(
                """
                SELECT metric_id FROM device_ingestion_receipts
                WHERE device_id=? AND event_id=?
                """,
                (int(identity["device_id"]), event_id),
            ).fetchone()
            if duplicate:
                return {
                    "duplicate": True,
                    "device_id": int(identity["device_id"]),
                    "metric_id": int(duplicate["metric_id"]),
                }
        raise

    db.execute(
        """
        UPDATE health_devices SET status='connected',last_synced_at=?
        WHERE id=?
        """,
        (now, int(identity["device_id"])),
    )
    db.execute(
        "UPDATE device_ingestion_keys SET last_used_at=? WHERE id=?",
        (now, int(identity["key_id"])),
    )
    db.commit()
    return {
        "duplicate": False,
        "device_id": int(identity["device_id"]),
        "metric_id": int(metric_id),
        "metric_type": str(measurement["metric_type"] or ""),
        "recorded_at": str(measurement.get("recorded_at") or now),
        "truth_notice": (
            "The value was accepted from a cryptographically authenticated device bridge. "
            "ZENDOC does not independently certify the sensor, calibration, or clinical meaning."
        ),
    }


@bp.post("/api/v1/iot/devices/<int:device_id>/ingestion-key")
def api_issue_device_ingestion_key(device_id):
    actor, error = require_api_user()
    if error:
        return error
    try:
        return jsonify({"key": issue_device_ingestion_key(actor, device_id)}), 201
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403


@bp.delete("/api/v1/iot/devices/<int:device_id>/ingestion-key")
def api_revoke_device_ingestion_key(device_id):
    actor, error = require_api_user()
    if error:
        return error
    try:
        return jsonify(revoke_device_ingestion_keys(actor, device_id))
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403


@bp.post("/api/v1/iot/ingest")
def api_device_ingest():
    data = request.get_json(silent=True) or {}
    try:
        result = ingest_device_measurement(
            request.headers.get("X-ZENDOC-Device-Key", ""),
            data,
        )
        g.observability_actor = {"id": 0, "role": "device"}
        return jsonify({"measurement": result}), 200 if result.get("duplicate") else 201
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403
    except ValueError as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
