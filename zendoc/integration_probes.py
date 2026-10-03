"""Non-destructive runtime verification for external ZENDOC integrations.

Configuration presence is not runtime proof. These owner-only probes perform
bounded, read-only connectivity/authentication checks and persist only
non-sensitive evidence. They never send patient data, create payments, book
care, dispatch transport, upload medical records, or deploy code.
"""
from __future__ import annotations

import base64
import json
import os
import smtplib
import socket
import ssl
import time
import urllib.error
import urllib.request
from typing import Any

from flask import current_app

from .database_reliability import readiness_report
from .db import get_db, now_iso
from .email_delivery import email_delivery_status
from .external_execution_guard import require_live_external_connector
from .model_router import (
    HARMLESS_LOCAL_TEST_PROMPT,
    PrivacyClass,
    get_model_router,
)
from .official_connectors import connector_readiness, fetch_data_gov_resource
from .payments import payment_gateway_status
from .places_provider import configured_places_provider, places_configuration_status
from .record_storage import S3CompatibleRecordStorage, get_record_storage
from .security import assert_owner


PROBE_DEFINITIONS = {
    "database": {
        "label": "PostgreSQL / database readiness",
        "automatic_safe": True,
        "may_use_billable_api": False,
    },
    "smtp": {
        "label": "Transactional email / SMTP",
        "automatic_safe": True,
        "may_use_billable_api": False,
    },
    "object_storage": {
        "label": "Durable medical-record object storage",
        "automatic_safe": True,
        "may_use_billable_api": False,
    },
    "razorpay": {
        "label": "Razorpay account connectivity",
        "automatic_safe": True,
        "may_use_billable_api": False,
    },
    "official_public_data": {
        "label": "Official/public data connector",
        "automatic_safe": True,
        "may_use_billable_api": False,
    },
    "turn": {
        "label": "TURN relay transport",
        "automatic_safe": True,
        "may_use_billable_api": False,
    },
    "places": {
        "label": "Live healthcare places discovery",
        "automatic_safe": False,
        "may_use_billable_api": True,
    },
    "ai_runtime": {
        "label": "AI model runtime",
        "automatic_safe": False,
        "may_use_billable_api": True,
    },
}


def ensure_integration_probe_schema() -> None:
    get_db().executescript(
        """
        CREATE TABLE IF NOT EXISTS integration_probe_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            integration_key TEXT NOT NULL,
            status TEXT NOT NULL,
            evidence_code TEXT NOT NULL,
            latency_ms INTEGER NOT NULL DEFAULT 0,
            detail_json TEXT NOT NULL DEFAULT '{}',
            checked_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            checked_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_integration_probe_key_time
            ON integration_probe_runs(integration_key, checked_at, id);
        """
    )


def _safe_detail(value: dict | None) -> dict:
    if not isinstance(value, dict):
        return {}
    safe = {}
    for key, item in value.items():
        key_text = str(key or "")[:80]
        if any(token in key_text.lower() for token in ("secret", "password", "token", "credential", "api_key", "key_id")):
            continue
        if isinstance(item, bool) or item is None:
            safe[key_text] = item
        elif isinstance(item, (int, float)):
            safe[key_text] = item
        elif isinstance(item, str):
            safe[key_text] = item[:300]
        elif isinstance(item, list):
            safe[key_text] = [str(entry)[:120] for entry in item[:12]]
    return safe


def _result(status: str, evidence_code: str, detail: dict | None = None) -> dict:
    return {
        "status": status,
        "evidence_code": evidence_code,
        "detail": _safe_detail(detail),
    }


def _probe_database(_actor: Any) -> dict:
    report = readiness_report()
    if report.get("status") == "ready":
        return _result(
            "working",
            "database_readiness_passed",
            {
                "engine": report.get("engine"),
                "platform": report.get("platform"),
                "persistence_verified": report.get("persistence_verified"),
            },
        )
    return _result(
        "failed",
        "database_readiness_failed",
        {"engine": report.get("engine"), "status": report.get("status")},
    )


def _probe_smtp(actor: Any) -> dict:
    require_live_external_connector("smtp_runtime_probe", actor=actor)
    status = email_delivery_status()
    if not status.get("transactional_email"):
        return _result("integration_required", "smtp_not_configured")

    host = str(current_app.config.get("SMTP_HOST") or "").strip()
    port = int(current_app.config.get("SMTP_PORT") or 587)
    username = str(current_app.config.get("SMTP_USERNAME") or "").strip()
    password = str(current_app.config.get("SMTP_PASSWORD") or "")
    timeout = min(20, max(2, int(current_app.config.get("SMTP_TIMEOUT") or 15)))
    use_ssl = bool(current_app.config.get("SMTP_USE_SSL"))
    use_tls = bool(current_app.config.get("SMTP_USE_TLS")) and not use_ssl

    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    kwargs = {"host": host, "port": port, "timeout": timeout}
    if use_ssl:
        kwargs["context"] = ssl.create_default_context()

    with smtp_class(**kwargs) as client:
        client.ehlo()
        if use_tls:
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
        if username:
            if not password:
                return _result("integration_required", "smtp_password_missing")
            client.login(username, password)
        try:
            client.noop()
        except smtplib.SMTPException:
            pass

    return _result(
        "working",
        "smtp_handshake_authenticated" if username else "smtp_handshake_reachable",
        {"host_configured": True, "port": port, "encrypted": bool(use_ssl or use_tls), "authenticated": bool(username)},
    )


def _probe_object_storage(actor: Any) -> dict:
    require_live_external_connector("object_storage_runtime_probe", actor=actor)
    storage = get_record_storage()
    status = storage.status()
    if not isinstance(storage, S3CompatibleRecordStorage):
        return _result(
            "integration_required",
            "durable_object_storage_not_configured",
            {"provider": status.get("provider"), "storage_status": status.get("status")},
        )

    client, settings = storage._client()
    client.head_bucket(Bucket=settings["bucket"])
    return _result(
        "working",
        "s3_head_bucket_succeeded",
        {
            "provider": storage.name,
            "bucket_configured": True,
            "endpoint_configured": bool(settings.get("endpoint_url")),
            "transport_secure": not settings.get("endpoint_url") or str(settings["endpoint_url"]).lower().startswith("https://"),
        },
    )


def _probe_razorpay(actor: Any) -> dict:
    require_live_external_connector("razorpay_runtime_probe", actor=actor)
    status = payment_gateway_status()
    key_id = str(os.environ.get("ZENDOC_RAZORPAY_KEY_ID") or "").strip()
    key_secret = str(os.environ.get("ZENDOC_RAZORPAY_KEY_SECRET") or "")
    if not key_id or not key_secret:
        return _result(
            "integration_required",
            "razorpay_checkout_credentials_missing",
            {"webhook_configured": bool(status.get("webhook_configured"))},
        )

    auth = base64.b64encode((key_id + ":" + key_secret).encode()).decode()
    request = urllib.request.Request(
        "https://api.razorpay.com/v1/orders?count=1",
        headers={"Authorization": "Basic " + auth, "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        raw = response.read(262145)
        if len(raw) > 262144:
            raise RuntimeError("Razorpay probe response exceeded the bounded limit.")
        payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Razorpay probe returned an invalid response.")
    return _result(
        "working" if status.get("webhook_configured") else "degraded",
        "razorpay_credentials_authenticated",
        {
            "checkout_authenticated": True,
            "webhook_configured": bool(status.get("webhook_configured")),
            "webhook_delivery_verified": False,
        },
    )


def _probe_official_public_data(actor: Any) -> dict:
    require_live_external_connector("official_data_runtime_probe", actor=actor)
    readiness = connector_readiness("data_gov_hospitals")
    if not readiness.get("ready_for_fetch"):
        return _result(
            "integration_required",
            "official_data_connector_not_configured",
            {"missing_config": readiness.get("missing_config") or []},
        )

    fetched = fetch_data_gov_resource("data_gov_hospitals", limit=1, offset=0)
    return _result(
        "working",
        "official_data_fetch_succeeded",
        {
            "record_count": fetched.get("record_count"),
            "upstream_count": fetched.get("upstream_count"),
            "upstream_total": fetched.get("upstream_total"),
            "source_id": fetched.get("source_id"),
        },
    )


def _parse_turn_endpoint(raw_url: str) -> tuple[str, str, int]:
    value = str(raw_url or "").strip()
    if ":" not in value:
        raise ValueError("Invalid ICE server URL.")
    scheme, remainder = value.split(":", 1)
    scheme = scheme.lower()
    if scheme not in {"turn", "turns"}:
        raise ValueError("TURN runtime probe requires a turn: or turns: URL.")
    endpoint = remainder.lstrip("/").split("?", 1)[0]
    if not endpoint:
        raise ValueError("TURN server host is missing.")

    default_port = 5349 if scheme == "turns" else 3478
    if endpoint.startswith("[") and "]" in endpoint:
        host = endpoint[1:endpoint.index("]")]
        suffix = endpoint[endpoint.index("]") + 1:]
        port = int(suffix[1:]) if suffix.startswith(":") and suffix[1:] else default_port
    elif endpoint.count(":") == 1:
        host, raw_port = endpoint.rsplit(":", 1)
        port = int(raw_port) if raw_port else default_port
    else:
        host, port = endpoint, default_port
    if not host or port < 1 or port > 65535:
        raise ValueError("TURN server endpoint is invalid.")
    return scheme, host, port


def _probe_turn(actor: Any) -> dict:
    require_live_external_connector("turn_runtime_probe", actor=actor)
    raw = str(os.environ.get("ZENDOC_WEBRTC_ICE_SERVERS_JSON") or "").strip()
    if not raw:
        return _result("integration_required", "turn_not_configured")
    try:
        servers = json.loads(raw)
    except json.JSONDecodeError:
        return _result("failed", "turn_configuration_invalid_json")
    if not isinstance(servers, list):
        return _result("failed", "turn_configuration_invalid")

    turn_urls = []
    has_username = False
    has_credential = False
    for item in servers[:8]:
        if not isinstance(item, dict):
            continue
        urls = item.get("urls")
        values = [urls] if isinstance(urls, str) else urls if isinstance(urls, list) else []
        for value in values:
            if str(value).startswith(("turn:", "turns:")):
                turn_urls.append(str(value))
        has_username = has_username or bool(str(item.get("username") or "").strip())
        has_credential = has_credential or bool(str(item.get("credential") or "").strip())

    if not turn_urls:
        return _result("integration_required", "turn_relay_url_missing")

    scheme, host, port = _parse_turn_endpoint(turn_urls[0])
    with socket.create_connection((host, port), timeout=6) as connection:
        if scheme == "turns":
            context = ssl.create_default_context()
            with context.wrap_socket(connection, server_hostname=host):
                pass

    credentials_present = bool(has_username and has_credential)
    return _result(
        "degraded",
        "turn_transport_reachable_auth_unverified",
        {
            "scheme": scheme,
            "host_configured": True,
            "port": port,
            "credentials_present": credentials_present,
            "two_device_media_test_required": True,
        },
    )


def _probe_places(actor: Any) -> dict:
    require_live_external_connector("places_runtime_probe", actor=actor)
    config = places_configuration_status()
    provider = configured_places_provider()
    result = provider.search(
        {
            "category": "hospital",
            "specialty": "",
            "location": "Kalyani",
            "search_text": "",
            "latitude": None,
            "longitude": None,
            "radius_km": 5,
        }
    )
    if not result.available:
        return _result(
            "failed",
            "places_provider_unavailable",
            {"source": result.source, "configured_provider": config.get("configured_provider")},
        )
    return _result(
        "working",
        "places_search_succeeded",
        {
            "source": result.source,
            "configured_provider": config.get("configured_provider"),
            "effective_provider": config.get("effective_provider"),
            "result_count": len(result.results or []),
        },
    )


def _probe_ai_runtime(actor: Any) -> dict:
    require_live_external_connector("ai_runtime_probe", actor=actor)
    router = get_model_router()
    local_configured = router.slm.is_configured()
    cloud_configured = router.cloud.is_configured()

    if local_configured:
        health = router.slm.health()
        if str(health.get("status") or "").lower() in {"working", "ready", "healthy"}:
            return _result(
                "working",
                "local_ai_health_succeeded",
                {"provider": health.get("provider"), "model": health.get("model"), "latency_ms": health.get("latency_ms")},
            )

    if cloud_configured:
        response = router.cloud.complete(
            HARMLESS_LOCAL_TEST_PROMPT,
            "Return a concise JSON-safe operational sentence only.",
            task_type="owner_operational_summary",
            privacy_class=PrivacyClass.PUBLIC,
        )
        if response.success:
            return _result(
                "working",
                "cloud_ai_inference_succeeded",
                {"provider": response.provider, "model": response.model, "latency_ms": response.latency_ms},
            )
        return _result(
            "failed",
            "cloud_ai_inference_failed",
            {"provider": response.provider, "model": response.model, "error_category": response.error_category},
        )

    return _result(
        "degraded",
        "deterministic_ai_fallback_only",
        {
            "local_ai_configured": local_configured,
            "cloud_ai_configured": cloud_configured,
            "deterministic_safety_available": True,
            "local_fallback_available": True,
        },
    )


_PROBES = {
    "database": _probe_database,
    "smtp": _probe_smtp,
    "object_storage": _probe_object_storage,
    "razorpay": _probe_razorpay,
    "official_public_data": _probe_official_public_data,
    "turn": _probe_turn,
    "places": _probe_places,
    "ai_runtime": _probe_ai_runtime,
}


def run_integration_probe(actor: Any, integration_key: str) -> dict:
    assert_owner(actor)
    key = str(integration_key or "").strip().lower()
    if key not in _PROBES:
        raise LookupError("Unsupported integration probe.")

    ensure_integration_probe_schema()
    started = time.perf_counter()
    try:
        outcome = _PROBES[key](actor)
    except Exception as exc:
        outcome = _result(
            "failed",
            "runtime_probe_failed",
            {"error_category": type(exc).__name__},
        )

    latency_ms = max(0, int((time.perf_counter() - started) * 1000))
    detail = _safe_detail(outcome.get("detail"))
    cursor = get_db().execute(
        """
        INSERT INTO integration_probe_runs
        (integration_key,status,evidence_code,latency_ms,detail_json,checked_by,checked_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (
            key,
            str(outcome.get("status") or "failed")[:40],
            str(outcome.get("evidence_code") or "runtime_probe_failed")[:120],
            latency_ms,
            json.dumps(detail, separators=(",", ":"), sort_keys=True),
            int(actor["id"]),
            now_iso(),
        ),
    )
    get_db().commit()
    return {
        "id": int(cursor.lastrowid),
        "integration_key": key,
        "label": PROBE_DEFINITIONS[key]["label"],
        "status": str(outcome.get("status") or "failed"),
        "evidence_code": str(outcome.get("evidence_code") or "runtime_probe_failed"),
        "latency_ms": latency_ms,
        "detail": detail,
        "checked_at": now_iso(),
    }


def latest_probe_results() -> dict[str, dict]:
    ensure_integration_probe_schema()
    rows = get_db().execute(
        """
        SELECT p.*
        FROM integration_probe_runs p
        JOIN (
            SELECT integration_key,MAX(id) latest_id
            FROM integration_probe_runs
            GROUP BY integration_key
        ) latest ON latest.latest_id=p.id
        ORDER BY p.integration_key
        """
    ).fetchall()
    result = {}
    for row in rows:
        item = dict(row)
        try:
            detail = json.loads(item.pop("detail_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            detail = {}
        item["detail"] = _safe_detail(detail)
        result[str(item["integration_key"])] = item
    return result


def integration_probe_snapshot() -> dict:
    latest = latest_probe_results()
    items = []
    for key, definition in PROBE_DEFINITIONS.items():
        last = latest.get(key)
        items.append(
            {
                "key": key,
                "label": definition["label"],
                "automatic_safe": bool(definition["automatic_safe"]),
                "may_use_billable_api": bool(definition["may_use_billable_api"]),
                "last": last,
            }
        )
    verified = sum(1 for item in items if item["last"] and item["last"].get("status") == "working")
    failing = sum(1 for item in items if item["last"] and item["last"].get("status") == "failed")
    return {
        "items": items,
        "verified_count": verified,
        "failing_count": failing,
        "total_count": len(items),
        "truth_notice": (
            "A runtime probe proves only the bounded check named by its evidence code. "
            "It does not replace end-to-end user testing, provider contracts, webhook delivery, settlement, "
            "clinical verification, real ambulance dispatch, or two-device WebRTC testing."
        ),
    }


def run_automatic_safe_probes(actor: Any) -> list[dict]:
    """Run only non-billable, non-mutating probes; opt-in at the worker boundary."""
    assert_owner(actor)
    results = []
    for key, definition in PROBE_DEFINITIONS.items():
        if not definition["automatic_safe"]:
            continue
        results.append(run_integration_probe(actor, key))
    return results
