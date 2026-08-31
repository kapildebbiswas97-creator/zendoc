"""Truthful infrastructure/provider status used by the owner command center."""
from __future__ import annotations

from flask import current_app

from .notification_providers import notification_provider_status
from .record_storage import get_record_storage
from .telehealth_provider import get_telehealth_provider


def database_status() -> dict:
    engine = str(current_app.config.get("DATABASE_ENGINE") or "sqlite").strip().lower()
    durability = str(current_app.config.get("DATABASE_DURABILITY") or "local_development")
    verified = bool(current_app.config.get("PERSISTENCE_VERIFIED"))
    environment = str(current_app.config.get("ZENDOC_ENV") or "development")

    if environment != "production" and engine == "sqlite":
        return {
            "active": "sqlite",
            "sqlite": "working",
            "status": "working",
            "persistence": "local_development",
            "engine": "SQLite",
            "durability": "development_only",
            "redeploy_verification": "not_applicable",
            "postgresql": "integration_required",
            "message": "Local SQLite is working. It is not evidence of production redeploy durability.",
        }

    if engine == "postgresql":
        return {
            "active": "postgresql",
            "sqlite": "local_development_only",
            "status": "working" if verified else "beta",
            "persistence": "durable" if verified else "integration_required",
            "engine": "PostgreSQL",
            "durability": "durable_configured",
            "redeploy_verification": "verified" if verified else "manual_verification_required",
            "postgresql": "working" if verified else "beta",
            "message": (
                "Managed PostgreSQL is configured and operator-verified."
                if verified
                else "Managed PostgreSQL is configured; run and record the manual restart/redeploy verification before external testing."
            ),
        }

    if durability == "durable_configured":
        return {
            "active": "sqlite",
            "sqlite": "working",
            "status": "working" if verified else "beta",
            "persistence": "durable" if verified else "integration_required",
            "engine": "SQLite",
            "durability": "persistent_mount_configured",
            "redeploy_verification": "verified" if verified else "manual_verification_required",
            "postgresql": "integration_required",
            "message": (
                "Persistent SQLite storage is configured and operator-verified; single-instance limitations apply."
                if verified
                else "A persistent SQLite path is configured, but the mount and redeploy behavior still require manual verification."
            ),
        }

    return {
        "active": "sqlite",
        "sqlite": "unsafe_production_configuration",
        "status": "integration_required",
        "persistence": "integration_required",
        "engine": "SQLite",
        "durability": "unsafe_production_configuration",
        "redeploy_verification": "failed_not_configured",
        "postgresql": "integration_required",
        "message": "Production is using service-local SQLite. Accounts can disappear on restart, spin-down, or redeploy.",
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
