"""Short-lived TURN REST API credentials for authenticated WebRTC users.

ZENDOC never ships the Coturn shared secret to browsers. The web process and
Coturn share one server-side secret and the browser receives only an expiring
username/password pair derived using Coturn's TURN REST API convention.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import os
import re
import time


_HOST_RE = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)


def _actor_id(actor) -> int:
    if actor is None:
        return 0
    try:
        return int(actor["id"])
    except Exception:
        return 0


def _validated_host(value: str) -> str:
    host = str(value or "").strip()
    if not host or "://" in host or "/" in host or "?" in host or "#" in host or "@" in host:
        raise ValueError("TURN public host must be a hostname or IP address only.")
    try:
        parsed = ipaddress.ip_address(host)
        return f"[{host}]" if parsed.version == 6 else host
    except ValueError:
        pass
    if not _HOST_RE.fullmatch(host) or ".." in host:
        raise ValueError("TURN public host is invalid.")
    return host.lower()


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(os.environ.get(name) or default).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def dynamic_turn_ice_servers(actor, *, now: int | float | None = None) -> list[dict]:
    """Return one short-lived Coturn REST credential bundle for an actor."""
    user_id = _actor_id(actor)
    host_raw = str(os.environ.get("ZENDOC_TURN_PUBLIC_HOST") or "").strip()
    secret = str(os.environ.get("ZENDOC_TURN_SHARED_SECRET") or "")
    if not user_id or not host_raw or not secret:
        return []
    if len(secret) < 32:
        raise ValueError("TURN shared secret must be at least 32 characters.")

    host = _validated_host(host_raw)
    port = _bounded_int("ZENDOC_TURN_PORT", 3478, 1, 65535)
    ttl = _bounded_int("ZENDOC_TURN_CREDENTIAL_TTL_SECONDS", 3600, 300, 86400)
    issued_at = int(time.time() if now is None else now)
    expires_at = issued_at + ttl
    username = f"{expires_at}:zendoc-{user_id}"
    digest = hmac.new(
        secret.encode("utf-8"),
        username.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    credential = base64.b64encode(digest).decode("ascii")
    return [{
        "urls": [
            f"turn:{host}:{port}?transport=udp",
            f"turn:{host}:{port}?transport=tcp",
        ],
        "username": username,
        "credential": credential,
        "credentialType": "password",
    }]


def dynamic_turn_status() -> dict:
    host = str(os.environ.get("ZENDOC_TURN_PUBLIC_HOST") or "").strip()
    secret = str(os.environ.get("ZENDOC_TURN_SHARED_SECRET") or "")
    configured = bool(host and len(secret) >= 32)
    return {
        "configured": configured,
        "host_configured": bool(host),
        "shared_secret_configured": len(secret) >= 32,
        "port": _bounded_int("ZENDOC_TURN_PORT", 3478, 1, 65535),
        "credential_ttl_seconds": _bounded_int(
            "ZENDOC_TURN_CREDENTIAL_TTL_SECONDS", 3600, 300, 86400
        ),
        "truth_notice": (
            "Configured means ZENDOC can mint short-lived TURN REST credentials. "
            "A runtime probe and two-device media test are still required to prove public-network relay."
        ),
    }
