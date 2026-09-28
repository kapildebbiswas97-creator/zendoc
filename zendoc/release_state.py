"""Truthful controlled-release state for pilot/beta UI and diagnostics."""
from __future__ import annotations

from flask import current_app


VALID_RELEASE_CHANNELS = {"development", "pilot", "production"}


def release_state() -> dict:
    channel = str(current_app.config.get("RELEASE_CHANNEL") or "pilot").strip().lower()
    if channel not in VALID_RELEASE_CHANNELS:
        channel = "pilot"

    data_mode = str(current_app.config.get("CONNECTED_CARE_DATA_MODE") or "LIVE").strip().upper()
    label = {
        "development": "Development",
        "pilot": "Production Pilot / Beta",
        "production": "Production",
    }[channel]
    return {
        "channel": channel,
        "label": label,
        "data_mode": data_mode if data_mode in {"LIVE", "DEMO"} else "UNKNOWN",
        "is_pilot": channel == "pilot",
        "is_demo": data_mode == "DEMO",
        "application_version": str(current_app.config.get("APP_VERSION") or "").strip() or None,
        "truth_states": [
            "CONNECTED",
            "UNCONNECTED",
            "EXPERIMENTAL",
            "DEMO / SIMULATED",
        ],
        "truth_notice": (
            "Release labels describe ZENDOC software/runtime mode only. They do not prove that "
            "an external provider, partner, payment, identity, inventory, availability, or "
            "clinical outcome is live or verified."
        ),
    }
