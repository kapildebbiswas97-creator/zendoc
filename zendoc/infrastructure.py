"""Truthful infrastructure/provider status used by the owner command center."""
from __future__ import annotations

from flask import current_app

from .notification_providers import notification_provider_status
from .record_storage import get_record_storage
from .telehealth_provider import get_telehealth_provider


def database_status() -> dict:
    database_url = str(current_app.config.get("DATABASE_URL") or "").strip()
    if database_url.startswith(("postgresql://", "postgres://")):
        return {
            "active": "sqlite",
            "sqlite": "working",
            "postgresql": "integration_required",
            "message": "DATABASE_URL detected; install/test the PostgreSQL driver and production migrations before switching.",
        }
    return {
        "active": "sqlite",
        "sqlite": "working",
        "postgresql": "integration_required",
        "message": "SQLite is active locally. PostgreSQL production adapter remains Integration Required.",
    }


def realtime_status() -> dict:
    provider = str(current_app.config.get("REALTIME_PROVIDER") or "polling").strip().lower()
    if provider == "polling":
        return {
            "provider": "authenticated_event_polling",
            "status": "working",
            "external_websocket": "integration_required",
        }
    return {"provider": provider, "status": "integration_required"}


def infrastructure_status() -> dict:
    return {
        "database": database_status(),
        "medical_record_storage": get_record_storage().status(),
        "notifications": notification_provider_status(),
        "realtime": realtime_status(),
        "telehealth": get_telehealth_provider().status(),
    }
