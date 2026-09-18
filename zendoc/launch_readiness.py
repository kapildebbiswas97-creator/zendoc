"""First-50-user launch readiness for ZENDOC.

This report distinguishes hard software/deployment blockers from pilot coverage
warnings. It never treats missing providers/geography as a software success, and
it never invents external backup, recovery, or partner readiness.
"""
from __future__ import annotations

from flask import current_app

from .database_reliability import backup_readiness, readiness_report
from .db import get_db
from .demo_truth import synthetic_demo_provider_profile_ids, synthetic_demo_user_ids
from .email_delivery import email_delivery_status
from .record_storage import get_record_storage
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

    demo_user_ids = synthetic_demo_user_ids(db)
    demo_profile_ids = synthetic_demo_provider_profile_ids(db)

    user_rows = db.execute(
        "SELECT id FROM users WHERE active=1 AND role<>'admin'"
    ).fetchall()
    user_count = sum(1 for row in user_rows if int(row["id"]) not in demo_user_ids)

    provider_rows = db.execute(
        "SELECT id,verification_status FROM provider_profiles"
    ).fetchall()
    real_provider_rows = [
        row for row in provider_rows
        if int(row["id"]) not in demo_profile_ids
    ]
    provider_profiles = len(real_provider_rows)
    verified_providers = sum(
        1 for row in real_provider_rows
        if str(row["verification_status"] or "").strip().lower() == "verified"
    )

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
            "PILOT_READY means the checked ZENDOC software/deployment conditions are green. Synthetic competition fixtures are excluded from user/provider counts. "
            "It does not claim that every locality has a connected provider, real-time stock, beds, ambulance dispatch, "
            "or any external partner integration."
        ),
    }



def public_launch_readiness() -> dict:
    """Readiness gate for opening ZENDOC to ordinary public web/mobile users.

    This gate is stricter than the first-50 pilot report. It requires durable
    persistence, real password-recovery delivery, durable medical-record storage,
    an HTTPS public base URL, and the public privacy/deletion/PWA routes.
    """
    pilot = first50_launch_readiness()
    blockers = []
    warnings = []
    passed = []

    environment = str(current_app.config.get("ZENDOC_ENV") or "development").lower()
    public_base_url = str(current_app.config.get("PUBLIC_BASE_URL") or "").strip().rstrip("/")

    if environment != "production":
        blockers.append({
            "key": "production_environment",
            "message": "Public launch must run with ZENDOC_ENV=production.",
        })
    else:
        passed.append({"key": "production_environment", "message": "Production mode is active."})

    if not public_base_url:
        blockers.append({
            "key": "public_base_url",
            "message": "ZENDOC_PUBLIC_BASE_URL is not configured.",
        })
    elif not public_base_url.lower().startswith("https://"):
        blockers.append({
            "key": "public_base_url",
            "message": "Public launch URL must use HTTPS.",
        })
    else:
        passed.append({
            "key": "public_base_url",
            "message": f"HTTPS public base URL configured: {public_base_url}",
        })

    database = pilot.get("database") or {}
    if database.get("status") != "ready":
        blockers.append({
            "key": "database",
            "message": "Database readiness is not green.",
        })
    elif environment == "production" and not bool(current_app.config.get("PERSISTENCE_VERIFIED")):
        blockers.append({
            "key": "persistence",
            "message": "Production persistence has not been explicitly verified.",
        })
    else:
        passed.append({
            "key": "persistence",
            "message": "Database and persistence readiness are green.",
        })

    email = email_delivery_status()
    if not email.get("transactional_email"):
        blockers.append({
            "key": "transactional_email",
            "message": (
                "Transactional email is required for public password recovery "
                "and off-app account-deletion confirmation."
            ),
            "detail": email,
        })
    elif not bool(current_app.config.get("EMAIL_VERIFIED")):
        blockers.append({
            "key": "transactional_email",
            "message": (
                "Transactional SMTP is configured but has not been marked verified "
                "after a real delivery smoke test."
            ),
            "detail": email,
        })
    else:
        passed.append({
            "key": "transactional_email",
            "message": "Transactional email is configured and marked verified.",
        })

    if not bool(current_app.config.get("BACKUP_VERIFIED")):
        blockers.append({
            "key": "backup_recovery",
            "message": (
                "Public healthcare launch requires a verified database backup/restore or PITR process. "
                "Set ZENDOC_BACKUP_VERIFIED=true only after a real recovery test for this deployment."
            ),
        })
    else:
        passed.append({
            "key": "backup_recovery",
            "message": "Database backup/recovery has been marked verified for this deployment.",
        })

    storage = get_record_storage().status()
    storage_provider = str(storage.get("provider") or "unknown")
    if storage_provider == "local":
        blockers.append({
            "key": "durable_record_storage",
            "message": (
                "Local filesystem medical-record storage is not acceptable for a public hosted launch. "
                "Configure and verify S3-compatible durable object storage."
            ),
            "detail": storage,
        })
    elif storage.get("status") == "integration_required":
        blockers.append({
            "key": "durable_record_storage",
            "message": "Durable medical-record storage is not fully configured.",
            "detail": storage,
        })
    elif not bool(current_app.config.get("STORAGE_VERIFIED")):
        blockers.append({
            "key": "durable_record_storage",
            "message": (
                "Durable object storage is configured but has not been marked verified after a real "
                "save/read/delete smoke test."
            ),
            "detail": storage,
        })
    else:
        passed.append({
            "key": "durable_record_storage",
            "message": "Durable record storage is configured and marked verified.",
        })

    required_routes = {
        "privacy": "/privacy",
        "terms": "/terms",
        "medical_disclaimer": "/medical-disclaimer",
        "account_deletion": "/account-deletion",
        "account_export": "/account/export",
        "manifest": "/manifest.webmanifest",
        "service_worker": "/sw.js",
        "health": "/healthz",
    }
    registered = {str(rule.rule) for rule in current_app.url_map.iter_rules()}
    missing_routes = [path for path in required_routes.values() if path not in registered]
    if missing_routes:
        blockers.append({
            "key": "public_launch_routes",
            "message": "Required public launch routes are missing.",
            "detail": {"missing": missing_routes},
        })
    else:
        passed.append({
            "key": "public_launch_routes",
            "message": "Privacy, terms, deletion, PWA and health routes are registered.",
        })

    if not str(current_app.config.get("SUPPORT_EMAIL") or "").strip():
        warnings.append({
            "key": "support_contact",
            "message": "ZENDOC_SUPPORT_EMAIL is not configured for public user support.",
        })
    else:
        passed.append({
            "key": "support_contact",
            "message": "Public support contact is configured.",
        })

    connected_mode = str(current_app.config.get("CONNECTED_CARE_DATA_MODE") or "LIVE").strip().upper()
    if connected_mode == "DEMO":
        blockers.append({
            "key": "connected_care_demo_mode",
            "message": "Public launch cannot run with ZENDOC_CONNECTED_CARE_DATA_MODE=DEMO.",
        })
    else:
        passed.append({
            "key": "connected_care_live_mode",
            "message": "Connected Care is not using synthetic DEMO operational data.",
        })

    telehealth_provider = str(current_app.config.get("TELEHEALTH_PROVIDER") or "local_demo").strip().lower()
    if telehealth_provider == "local_demo":
        blockers.append({
            "key": "telehealth_demo_mode",
            "message": (
                "Public launch cannot use TELEHEALTH_PROVIDER=local_demo. "
                "Use internal_chat for real in-app chat only, or configure a verified external media provider."
            ),
        })
    elif telehealth_provider == "internal_chat":
        passed.append({
            "key": "telehealth_mode",
            "message": "Telehealth is configured for real in-app chat only; voice/video remain unavailable.",
        })
    else:
        warnings.append({
            "key": "telehealth_mode",
            "message": (
                f"Telehealth provider '{telehealth_provider}' must be independently verified before "
                "claiming voice/video or external consultation fulfilment."
            ),
        })

    package_name = str(current_app.config.get("ANDROID_PACKAGE_NAME") or "").strip()
    fingerprint = str(current_app.config.get("ANDROID_SHA256_CERT_FINGERPRINT") or "").strip()
    if package_name and not fingerprint:
        warnings.append({
            "key": "android_asset_links",
            "message": "Android package is configured but signing-certificate fingerprint is missing.",
        })
    elif package_name and fingerprint:
        passed.append({
            "key": "android_asset_links",
            "message": "Android Digital Asset Links configuration is present.",
        })
    else:
        warnings.append({
            "key": "android_packaging",
            "message": "Android package/signing configuration is not set yet; web launch can still proceed.",
        })

    # Carry hard pilot blockers into the public gate because public launch must
    # never be weaker than the first-50 operational gate.
    for item in pilot.get("blockers") or []:
        blockers.append({
            "key": f"pilot_{item.get('key')}",
            "message": item.get("message"),
        })

    status = "PUBLIC_LAUNCH_BLOCKED" if blockers else "PUBLIC_LAUNCH_READY_WITH_WARNINGS" if warnings else "PUBLIC_LAUNCH_READY"
    return {
        "status": status,
        "target": "public_web_and_mobile",
        "blockers": blockers,
        "warnings": warnings,
        "passed": passed,
        "pilot_status": pilot.get("status"),
        "email": email,
        "record_storage": storage,
        "public_base_url": public_base_url or None,
        "truth_notice": (
            "PUBLIC_LAUNCH_READY means only that the checked software/deployment controls are present and configured. "
            "It does not prove legal/regulatory approval, clinical effectiveness, external provider coverage, "
            "Snapdragon/NPU execution, or Google Play review approval."
        ),
    }
