"""Privacy helpers for operational/audit logging.

User-facing records may retain user content where the product requires it.
Operational logs should retain only the minimum metadata needed to debug,
audit authorization, and measure reliability.
"""
from __future__ import annotations

import hashlib
import re

_SECRET_PATTERNS = (
    re.compile(r"(?i)bearer\s+[a-z0-9._~+\-/]+=*"),
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+"),
)
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")

SENSITIVE_PAYLOAD_KEYS = {
    "email", "phone", "mobile", "address", "delivery_address", "pickup_address",
    "destination_address", "symptom", "symptoms", "diagnosis", "diagnosis_notes",
    "prescription", "prescriptions", "medication", "medicine", "medical_record",
    "medical_records", "report", "reports", "notes", "message", "prompt", "query",
    "context", "raw_text", "input_text", "output_text",
}


def redact_operational_text(value, limit=500):
    """Redact credentials/contact data from unavoidable operational text."""
    if value is None:
        return None
    text = str(value)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[redacted]", text)
    text = _EMAIL_RE.sub("[redacted-email]", text)
    text = _PHONE_RE.sub("[redacted-phone]", text)
    return text[: max(0, int(limit))]


def summarize_user_content(value, *, label="user_input"):
    """Return non-reversible metadata instead of raw user/clinical content."""
    text = str(value or "")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{label};chars={len(text)};sha256={digest}"


def safe_payload(value, depth=0):
    """Recursively minimize event payloads while preserving IDs/status metadata."""
    if depth > 4:
        return "[truncated]"
    if isinstance(value, dict):
        clean = {}
        for key, item in list(value.items())[:40]:
            key_text = str(key)[:80]
            normalized = key_text.strip().lower()
            if normalized.endswith("_id") or normalized in {"id", "status", "intent", "role", "count", "task_id", "tool_count"}:
                clean[key_text] = safe_payload(item, depth + 1)
            elif normalized in SENSITIVE_PAYLOAD_KEYS or any(
                marker in normalized for marker in ("password", "token", "secret", "api_key", "authorization", "cookie")
            ):
                clean[key_text] = "[redacted]"
            else:
                clean[key_text] = safe_payload(item, depth + 1)
        return clean
    if isinstance(value, (list, tuple)):
        return [safe_payload(item, depth + 1) for item in list(value)[:40]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_operational_text(value, 300)
