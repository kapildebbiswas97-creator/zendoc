"""First-50-user launch readiness for ZENDOC.

This report distinguishes hard software/deployment blockers from pilot coverage
warnings. It never treats missing providers/geography as a software success, and
it never invents external backup, recovery, or partner readiness.
"""
from __future__ import annotations

from pathlib import Path

from flask import current_app

from .database_reliability import backup_readiness, readiness_report
from .db import get_db
from .demo_truth import synthetic_demo_provider_profile_ids, synthetic_demo_user_ids
from .email_delivery import email_delivery_status
from .record_storage import get_record_storage
from .pilot_analytics import pilot_scorecard
from .state_geography_bootstrap import state_coverage_summary



def software_completion_readiness() -> dict:
    """Check only repository-owned/free software completion.

    This intentionally ignores domain purchase, external SMTP/S3/PostgreSQL
    credentials, hosting backup evidence, Google Play review/testing, provider
    coverage, and Snapdragon hardware measurements. Those are separate real-world
    deployment/evidence gates.
    """
    repo_root = Path(current_app.root_path).resolve().parent
    blockers = []
    passed = []

    required_routes = {
        "home": "/",
        "login": "/login",
        "patient_registration": "/register/<role>",
        "dashboard": "/dashboard",
        "finder": "/finder",
        "universal_search": "/universal-search",
        "ai": "/ai",
        "appointments": "/appointments",
        "messages": "/messages",
        "health_summary": "/health-summary",
        "timeline": "/timeline",
        "records": "/records",
        "health": "/health",
        "health_access": "/health-access",
        "family": "/family",
        "videos": "/videos",
        "profile": "/profile",
        "health_hub": "/health-hub",
        "telehealth": "/telehealth",
        "agent_os": "/agent-os",
        "care_continuity": "/care-continuity",
        "privacy": "/privacy",
        "terms": "/terms",
        "medical_disclaimer": "/medical-disclaimer",
        "account_deletion": "/account-deletion",
        "account_export": "/account/export",
        "email_verification": "/verify-email",
        "resend_verification": "/resend-verification",
        "mobile_refresh": "/api/v1/auth/refresh",
        "mobile_account_delete": "/api/v1/account",
        "provider_invitation_accept": "/provider-invitation/accept",
        "provider_invitation_admin": "/admin/provider-invitations",
        "manifest": "/manifest.webmanifest",
        "service_worker": "/sw.js",
        "offline": "/offline",
        "asset_links": "/.well-known/assetlinks.json",
        "showcase": "/showcase",
        "founder_readiness": "/admin/founder-readiness",
        "startup_admin": "/admin/startup",
        "edgecare_admin": "/admin/edgecare",
        "health": "/healthz",
        "readiness": "/api/v1/ready",
    }
    registered = {str(rule.rule) for rule in current_app.url_map.iter_rules()}
    missing_routes = [path for path in required_routes.values() if path not in registered]
    if missing_routes:
        blockers.append({
            "key": "route_contract",
            "message": "One or more required software-completion routes are missing.",
            "detail": {"missing": missing_routes},
        })
    else:
        passed.append({
            "key": "route_contract",
            "message": f"All {len(required_routes)} required public/core/mobile/provider routes are registered.",
        })

    required_files = [
        "zendoc/security_headers.py",
        "zendoc/email_delivery.py",
        "zendoc/email_verification.py",
        "zendoc/account_lifecycle.py",
        "zendoc/account_export.py",
        "zendoc/provider_invitation.py",
        "zendoc/record_storage.py",
        "zendoc/health_memory_rag.py",
        "templates/privacy.html",
        "templates/terms.html",
        "templates/medical_disclaimer.html",
        "templates/account_deletion.html",
        "templates/provider_invitation_accept.html",
        "static/sw.js",
        "static/pwa.js",
        "static/icons/zendoc-192.png",
        "static/icons/zendoc-512.png",
        "static/icons/zendoc-maskable-512.png",
        "scripts/verify_public_launch.py",
        "scripts/verify_record_storage.py",
        "scripts/verify_transactional_email.py",
        "scripts/verify_postgres_backup_restore.py",
        "scripts/verify_android_release.py",
        "scripts/bootstrap_android_twa.ps1",
        "scripts/bootstrap_android_twa.sh",
        "docs/PUBLIC_WEB_AND_PLAY_STORE_RELEASE.md",
        "docs/GOOGLE_PLAY_DATA_SAFETY_DRAFT.md",
        "docs/PLAY_STORE_LISTING_DRAFT.md",
        ".github/workflows/ci.yml",
    ]
    missing_files = [
        relative for relative in required_files
        if not (repo_root / relative).is_file()
    ]
    empty_files = [
        relative for relative in required_files
        if (repo_root / relative).is_file() and (repo_root / relative).stat().st_size == 0
    ]
    if missing_files or empty_files:
        blockers.append({
            "key": "release_artifacts",
            "message": "Required release/security/PWA artifacts are missing or empty.",
            "detail": {"missing": missing_files, "empty": empty_files},
        })
    else:
        passed.append({
            "key": "release_artifacts",
            "message": f"All {len(required_files)} required release/security/PWA artifacts are present and non-empty.",
        })

    required_tests = [
        "tests/test_submission_smoke_matrix_v1.py",
        "tests/test_public_launch_v1.py",
        "tests/test_email_delivery_v1.py",
        "tests/test_email_verification_v1.py",
        "tests/test_policy_acceptance_v1.py",
        "tests/test_public_registration_roles_v1.py",
        "tests/test_provider_invitation_v1.py",
        "tests/test_software_completion_gate_v1.py",
        "tests/test_api_token_lifecycle_v1.py",
        "tests/test_auth_rate_limit_v1.py",
        "tests/test_telehealth_truth_v1.py",
        "tests/test_account_export_v1.py",
        "tests/test_health_memory_rag_v1.py",
        "tests/test_careloop_consent_scope_boundary.py",
        "tests/test_care_action_provider_state_truth.py",
    ]
    missing_tests = [
        relative for relative in required_tests
        if not (repo_root / relative).is_file()
    ]
    if missing_tests:
        blockers.append({
            "key": "regression_contract",
            "message": "One or more required regression test files are missing.",
            "detail": {"missing": missing_tests},
        })
    else:
        passed.append({
            "key": "regression_contract",
            "message": f"All {len(required_tests)} required launch/privacy/safety regression files are present.",
        })

    config_contract = {
        "PUBLIC_RELEASE_REQUIRED": "PUBLIC_RELEASE_REQUIRED" in current_app.config,
        "AUTH_RATE_LIMIT_PER_MINUTE": int(current_app.config.get("AUTH_RATE_LIMIT_PER_MINUTE") or 0) > 0,
        "API_ACCESS_TOKEN_MINUTES": 5 <= int(current_app.config.get("API_ACCESS_TOKEN_MINUTES") or 0) <= 1440,
        "API_REFRESH_TOKEN_DAYS": 1 <= int(current_app.config.get("API_REFRESH_TOKEN_DAYS") or 0) <= 180,
        "EMAIL_PROVIDER": "EMAIL_PROVIDER" in current_app.config,
        "STORAGE_PROVIDER": "STORAGE_PROVIDER" in current_app.config,
        "BACKUP_VERIFIED": "BACKUP_VERIFIED" in current_app.config,
        "ANDROID_PACKAGE_NAME": "ANDROID_PACKAGE_NAME" in current_app.config,
    }
    failed_config = [key for key, ok in config_contract.items() if not ok]
    if failed_config:
        blockers.append({
            "key": "configuration_contract",
            "message": "One or more required launch/security configuration controls are absent or invalid.",
            "detail": {"failed": failed_config},
        })
    else:
        passed.append({
            "key": "configuration_contract",
            "message": "Public-release, auth-token, storage, backup, email and Android configuration controls are present.",
        })

    workflow_path = repo_root / ".github" / "workflows" / "ci.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8", errors="replace") if workflow_path.is_file() else ""
    workflow_requirements = {
        "manual_dispatch": "workflow_dispatch:" in workflow_text,
        "competition_branch": "competition/edgecare-ai-2026" in workflow_text,
        "public_launch_tests": "tests/test_public_launch_v1.py" in workflow_text,
        "email_verification_tests": "tests/test_email_verification_v1.py" in workflow_text,
        "provider_invitation_tests": "tests/test_provider_invitation_v1.py" in workflow_text,
        "mobile_token_tests": "tests/test_api_token_lifecycle_v1.py" in workflow_text,
    }
    workflow_missing = [key for key, ok in workflow_requirements.items() if not ok]
    if workflow_missing:
        blockers.append({
            "key": "ci_contract",
            "message": "The Production Gate is missing one or more required exact-head validation hooks.",
            "detail": {"missing": workflow_missing},
        })
    else:
        passed.append({
            "key": "ci_contract",
            "message": "Production Gate includes competition-branch/manual validation and the critical public-launch regressions.",
        })

    status = "SOFTWARE_IMPLEMENTATION_COMPLETE" if not blockers else "SOFTWARE_IMPLEMENTATION_INCOMPLETE"
    return {
        "status": status,
        "target": "repository_owned_free_software_scope",
        "blockers": blockers,
        "passed": passed,
        "route_count": len(required_routes),
        "artifact_count": len(required_files),
        "regression_file_count": len(required_tests),
        "validation_status": "EXACT_HEAD_CI_STILL_REQUIRED",
        "truth_notice": (
            "SOFTWARE_IMPLEMENTATION_COMPLETE means the checked repository-owned software contract is present. "
            "It does not mean the exact commit passed CI, nor does it prove live domain/SMTP/S3/PostgreSQL backup, "
            "provider coverage, Google Play approval, regulatory approval, or Snapdragon/NPU measurements."
        ),
    }



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

    recovery_email = email_delivery_status()
    if not recovery_email.get("transactional_email"):
        warnings.append({
            "key": "password_recovery",
            "message": "Transactional email is not configured, so password recovery remains integration-required.",
            "detail": recovery_email,
        })
    else:
        passed.append({
            "key": "password_recovery",
            "message": "Transactional email is configured for password recovery.",
        })

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

    if not bool(current_app.config.get("PUBLIC_RELEASE_REQUIRED")):
        blockers.append({
            "key": "public_startup_guard",
            "message": (
                "ZENDOC_PUBLIC_RELEASE_REQUIRED must be true for a public launch so startup fails closed "
                "when required production controls are missing."
            ),
        })
    else:
        passed.append({
            "key": "public_startup_guard",
            "message": "Strict public-release startup guard is enabled.",
        })

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
    elif not (
        bool(current_app.config.get("SMTP_USE_TLS"))
        or bool(current_app.config.get("SMTP_USE_SSL"))
    ):
        blockers.append({
            "key": "transactional_email_transport",
            "message": "Public transactional email must use SMTP TLS or SSL.",
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
            "message": "Transactional email is configured, encrypted and marked verified.",
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
    elif storage.get("transport_secure") is False:
        blockers.append({
            "key": "durable_record_storage_transport",
            "message": "Public medical-record object storage must use HTTPS transport.",
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
            "message": "Durable record storage is configured, encrypted in transit and marked verified.",
        })

    required_routes = {
        "privacy": "/privacy",
        "terms": "/terms",
        "medical_disclaimer": "/medical-disclaimer",
        "account_deletion": "/account-deletion",
        "account_export": "/account/export",
        "mobile_account_export": "/api/v1/account/export",
        "mobile_account_delete": "/api/v1/account",
        "verify_email": "/verify-email",
        "resend_verification": "/resend-verification",
        "provider_invitation_accept": "/provider-invitation/accept",
        "provider_invitation_admin": "/admin/provider-invitations",
        "mobile_token_refresh": "/api/v1/auth/refresh",
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
            "message": "Privacy, terms, deletion/export, verification, controlled onboarding, mobile auth, PWA and health routes are registered.",
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
