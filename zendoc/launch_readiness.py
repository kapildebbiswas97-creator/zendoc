"""First-50-user launch readiness for ZENDOC.

This report distinguishes hard software/deployment blockers from pilot coverage
warnings. It never treats missing providers/geography as a software success, and
it never invents external backup, recovery, or partner readiness.
"""
from __future__ import annotations

from flask import current_app

from .database_reliability import backup_readiness, readiness_report
from .db import get_db
from .pilot_analytics import pilot_scorecard
from .state_geography_bootstrap import state_coverage_summary


def first50_launch_readiness() -> dict:
    db = get_db()
    database = readiness_report()
    backup = backup_readiness()
    pilot = pilot_scorecard()

    blockers = []
    warnings = []
    passed = []

    if database.get("status") != "ready":
        blockers.append({
            "key": "database_readiness",
            "message": "Database/schema/migration readiness is not green.",
            "detail": database,
        })
    else:
        passed.append({"key": "database_readiness", "message": "Database readiness is green."})

    if current_app.config.get("ZENDOC_ENV") == "production" and not bool(current_app.config.get("PERSISTENCE_VERIFIED")):
        blockers.append({
            "key": "persistence",
            "message": "Production persistence has not been verified.",
        })
    elif bool(current_app.config.get("PERSISTENCE_VERIFIED")):
        passed.append({"key": "persistence", "message": "Persistence is marked verified."})

    if backup.get("status") == "NOT_READY":
        blockers.append({
            "key": "backup",
            "message": "Local database backup path is not ready.",
            "detail": backup,
        })
    elif backup.get("status") == "INTEGRATION_REQUIRED":
        warnings.append({
            "key": "backup",
            "message": "PostgreSQL backup/PITR must be verified in the hosting platform; ZENDOC cannot verify external backups from the app.",
            "detail": backup,
        })
    else:
        passed.append({"key": "backup", "message": "Local backup readiness is available."})

    if current_app.config.get("PASSWORD_RECOVERY_MODE") != "integrated":
        warnings.append({
            "key": "password_recovery",
            "message": "Password-reset delivery is not integrated. First users may require controlled owner-assisted recovery.",
        })
    else:
        passed.append({"key": "password_recovery", "message": "Password recovery delivery is integrated."})

    user_count = int(db.execute("SELECT COUNT(*) c FROM users WHERE active=1 AND role<>'admin'").fetchone()["c"])
    verified_providers = int(db.execute(
        "SELECT COUNT(*) c FROM provider_profiles WHERE verification_status='verified'"
    ).fetchone()["c"])
    provider_profiles = int(db.execute("SELECT COUNT(*) c FROM provider_profiles").fetchone()["c"])

    if verified_providers == 0:
        warnings.append({
            "key": "verified_provider_coverage",
            "message": "No verified providers are available yet. Patient discovery may return public-directory records but not connected verified care.",
        })
    else:
        passed.append({
            "key": "verified_provider_coverage",
            "message": f"{verified_providers} verified provider profile(s) are available.",
        })

    geography = {}
    for slug in ("west_bengal", "assam", "uttar_pradesh"):
        coverage = state_coverage_summary(slug)
        geography[slug] = coverage
        if not coverage.get("loaded"):
            warnings.append({
                "key": f"geography_{slug}",
                "message": f"{coverage['state']['name']} official geography has not yet been loaded into this database.",
            })
        elif int(coverage.get("counts", {}).get("district", 0)) == 0:
            warnings.append({
                "key": f"geography_{slug}",
                "message": f"{coverage['state']['name']} exists but has no district coverage yet.",
            })
        else:
            passed.append({
                "key": f"geography_{slug}",
                "message": (
                    f"{coverage['state']['name']} geography loaded: "
                    f"{coverage['counts'].get('district', 0)} district(s), "
                    f"{coverage['counts'].get('subdivision', 0)} sub-district(s), "
                    f"{coverage['counts'].get('village', 0)} village(s)."
                ),
            })

    reliability_signal = next(
        (item for item in pilot.get("signals", []) if item.get("key") == "request_reliability"),
        None,
    )
    if reliability_signal and reliability_signal.get("status") == "ATTENTION":
        blockers.append({
            "key": "recent_request_reliability",
            "message": reliability_signal.get("message"),
        })
    elif reliability_signal:
        passed.append({
            "key": "recent_request_reliability",
            "message": reliability_signal.get("message"),
        })

    for key in ("pharmacy_freshness", "diagnostic_freshness", "pharmacy_response", "consultation_response"):
        signal = next((item for item in pilot.get("signals", []) if item.get("key") == key), None)
        if signal and signal.get("status") == "ATTENTION":
            warnings.append({
                "key": key,
                "message": signal.get("message"),
            })

    if blockers:
        status = "BLOCKED"
    elif warnings:
        status = "PILOT_READY_WITH_WARNINGS"
    else:
        status = "PILOT_READY"

    return {
        "status": status,
        "target": "first_50_users",
        "blockers": blockers,
        "warnings": warnings,
        "passed": passed,
        "counts": {
            "active_non_admin_users": user_count,
            "provider_profiles": provider_profiles,
            "verified_providers": verified_providers,
        },
        "geography": geography,
        "database": database,
        "backup": backup,
        "pilot_signals": pilot.get("signals", []),
        "truth_notice": (
            "PILOT_READY means the checked ZENDOC software/deployment conditions are green. "
            "It does not claim that every locality has a connected provider, real-time stock, beds, ambulance dispatch, "
            "or any external partner integration."
        ),
    }
