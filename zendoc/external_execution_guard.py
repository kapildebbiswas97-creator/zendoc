"""Fail-closed boundary preventing demo/synthetic activity from using live external connectors."""
from __future__ import annotations

from typing import Any

from flask import current_app, g, has_request_context

from .demo_truth import is_synthetic_demo_email


def _value(actor: Any, key: str, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    if isinstance(actor, dict):
        return actor.get(key, default)
    return default


def external_connector_block_reason(
    *,
    actor: Any = None,
    target_email: str | None = None,
) -> str | None:
    mode = str(current_app.config.get("CONNECTED_CARE_DATA_MODE") or "LIVE").strip().upper()
    if mode == "DEMO":
        return "demo_data_mode"

    effective_actor = actor
    if effective_actor is None and has_request_context():
        effective_actor = getattr(g, "user", None)

    actor_email = str(_value(effective_actor, "email") or "").strip()
    if actor_email and is_synthetic_demo_email(actor_email):
        return "synthetic_demo_actor"

    if target_email and is_synthetic_demo_email(target_email):
        return "synthetic_demo_target"

    return None


def require_live_external_connector(
    operation: str,
    *,
    actor: Any = None,
    target_email: str | None = None,
) -> None:
    reason = external_connector_block_reason(actor=actor, target_email=target_email)
    if reason:
        raise RuntimeError(
            f"External connector operation '{str(operation or 'external_action')[:80]}' "
            f"is blocked for demo/synthetic activity ({reason})."
        )
