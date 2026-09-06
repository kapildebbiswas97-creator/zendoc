from __future__ import annotations

from pathlib import Path

from zendoc import create_app
from zendoc.database_reliability import REQUIRED_MIGRATIONS, REQUIRED_TABLES
from zendoc.db import get_db
from tests.test_milestone1 import make_app


CRITICAL_FILES = (
    ".github/workflows/ci.yml",
    "scripts/ci_postgres_readiness.py",
    "scripts/ci_secret_scan.py",
    "scripts/verify_deployment.py",
    ".github/dependabot.yml",
    "render.yaml",
    "zendoc/database_reliability.py",
    "zendoc/observability.py",
    "tests/test_security_hardening_v3.py",
    "tests/test_provider_permission_matrix_v1.py",
    "tests/test_provider_tenancy_v1.py",
    "tests/test_provider_resource_tenancy_v1.py",
    "tests/test_workflow_state_integrity_v1.py",
    "tests/test_concurrency_integrity_v1.py",
    "tests/test_database_reliability_v1.py",
    "tests/test_observability_incident_v1.py",
)


def test_release_gate_files_exist():
    root = Path(__file__).resolve().parents[1]
    missing = [path for path in CRITICAL_FILES if not (root / path).exists()]
    assert missing == []


def test_required_migration_manifest_includes_security_reliability_stages():
    expected = {
        "post_submission_provider_tenancy_v1",
        "post_submission_provider_resource_tenancy_v1",
        "post_submission_concurrency_v1",
        "post_submission_request_fingerprints_v1",
        "post_submission_observability_v1",
    }
    assert expected.issubset(set(REQUIRED_MIGRATIONS))


def test_required_table_manifest_includes_release_critical_tables():
    expected = {
        "provider_organizations",
        "organization_memberships",
        "appointment_slot_claims",
        "request_observations",
        "integration_health_checks",
    }
    assert expected.issubset(set(REQUIRED_TABLES))


def test_readiness_routes_and_owner_ops_are_registered(tmp_path):
    app = make_app(tmp_path)
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/api/v1/health" in rules
    assert "/api/v1/ready" in rules
    assert "/api/v1/readiness" in rules
    assert "/owner/database-readiness" in rules
    assert "/owner/observability" in rules
    assert "/owner/incident-runbooks" in rules


def test_release_gate_migrations_are_applied_in_fresh_database(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        versions = {
            str(row["version"])
            for row in get_db().execute("SELECT version FROM schema_migrations").fetchall()
        }
        assert set(REQUIRED_MIGRATIONS).issubset(versions)


def test_ci_workflow_contains_all_blocking_jobs():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for job in (
        "critical-safety-security:",
        "full-sqlite-tests:",
        "postgres-production-smoke:",
        "static-security:",
        "release-readiness:",
        "deployment-verification:",
    ):
        assert job in workflow
    assert "needs:" in workflow
    assert "pip-audit" in workflow
    assert "bandit" in workflow
    assert "scripts/ci_secret_scan.py" in workflow
    assert "scripts/ci_postgres_readiness.py" in workflow


def test_production_config_does_not_require_external_ai_or_maps_for_boot():
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": ":memory:",
            "SECRET_KEY": "release-gate-test-secret",
            "ADMIN_EMAIL": "release-owner@example.invalid",
            "ADMIN_PASSWORD": "ReleaseGateStrong123",
            "CREATE_DEV_ADMIN": False,
            "PLACES_PROVIDER": "none",
            "VIDEO_PROVIDER": "none",
            "LOCAL_AI_ENABLED": False,
        }
    )
    assert app.config["PLACES_PROVIDER"] == "none"
    assert app.config["VIDEO_PROVIDER"] == "none"
    assert app.config["LOCAL_AI_ENABLED"] is False


def test_render_uses_readiness_health_check():
    root = Path(__file__).resolve().parents[1]
    render = (root / "render.yaml").read_text(encoding="utf-8")
    assert "healthCheckPath: /api/v1/ready" in render
    assert "ZENDOC_PERSISTENCE_VERIFIED" in render


def test_dependabot_covers_python_and_github_actions():
    root = Path(__file__).resolve().parents[1]
    config = (root / ".github/dependabot.yml").read_text(encoding="utf-8")
    assert "package-ecosystem: pip" in config
    assert "package-ecosystem: github-actions" in config


def test_deployment_verifier_is_wired_to_optional_main_cd_job():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "deployment-verification:" in workflow
    assert "vars.ZENDOC_DEPLOYMENT_URL" in workflow
    assert 'python scripts/verify_deployment.py' in workflow
