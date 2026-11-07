"""ZENDOC 2.0 — Python Worker Cryptographic Authentication Boundary

Implements HMAC-SHA256 signature verification and timestamp replay protection
matching the Next.js server-side cryptographic contract.
"""
from __future__ import annotations

import hashlib
import hmac
import time

MAX_AGE_MS = 60_000  # 60 seconds
MAX_FUTURE_DRIFT_MS = 5_000  # 5 seconds


def generate_worker_hmac(secret: str, timestamp: str, user_id: str) -> str:
    """Computes an HMAC-SHA256 digest over `${timestamp}:${user_id}`."""
    if not secret:
        raise ValueError("Secret key cannot be empty.")
    payload = f"{timestamp}:{user_id}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_worker_hmac(
    secret: str, timestamp: str, user_id: str, received_hmac: str
) -> bool:
    """Validates received HMAC using constant-time digest comparison."""
    if not secret or not received_hmac:
        return False
    expected = generate_worker_hmac(secret, timestamp, user_id)
    return hmac.compare_digest(expected.lower(), received_hmac.strip().lower())


def is_timestamp_fresh(timestamp_str: str, max_age_ms: int = MAX_AGE_MS) -> bool:
    """Checks that timestamp is fresh within max_age_ms and not forged in the distant future."""
    try:
        ts = int(timestamp_str)
        if ts <= 0:
            return False
        now_ms = int(time.time() * 1000)
        age = now_ms - ts
        if age > max_age_ms:
            return False
        if ts - now_ms > MAX_FUTURE_DRIFT_MS:
            return False
        return True
    except (ValueError, TypeError):
        return False
