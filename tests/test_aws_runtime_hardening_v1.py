"""Release guardrails for Kiro's AWS audit, checked against the CURRENT release branch.

These tests are static guards, not proof that TLS, TURN, backups or EC2
are running. Real cloud credentials and billing remain owner-controlled.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AWS = ROOT / "deploy" / "aws"


def _read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_application_container_runs_as_unprivileged_user():
    dockerfile = _read("Dockerfile")
    assert "useradd --system --uid 10001" in dockerfile
    assert "USER zendoc:zendoc" in dockerfile
    assert dockerfile.index("USER zendoc:zendoc") < dockerfile.index("CMD [")
    assert "mkdir -p /app/uploads /app/instance" in dockerfile
    assert "chown -R zendoc:zendoc /app/uploads /app/instance" in dockerfile


def test_docker_context_excludes_git_secrets_and_patient_uploads():
    ignore = _read(".dockerignore").splitlines()
    for path in (".git", "**/.env", "**/*.pem", "**/*.sqlite3", "**/uploads", "**/.aws"):
        assert path in ignore


def test_turn_is_off_by_default_and_never_uses_host_network():
    compose = _read("deploy/aws/compose.yaml")
    turn = compose.split("\n  turn:\n", 1)[1].split("\n  caddy:\n", 1)[0]
    assert 'profiles: ["realtime"]' in turn
    assert "network_mode: host" not in turn
    assert "networks:\n      - edge" in turn
    assert "- backend" not in turn
    assert '3478' in turn and '/udp"' in turn and '/tcp"' in turn
    assert '49160' in turn and '49200' in turn
    # Missing TURN opt-in secrets must not break unrelated Compose config,
    # but the TURN entrypoint must still reject startup without credentials.
    assert "ZENDOC_TURN_SHARED_SECRET: ${ZENDOC_TURN_SHARED_SECRET:-}" in turn
    assert "ZENDOC_TURN_EXTERNAL_IP: ${ZENDOC_TURN_EXTERNAL_IP:-}" in turn
    script = _read("deploy/aws/turn-entrypoint.sh")
    assert 'ZENDOC_TURN_SHARED_SECRET:?' in script
    assert 'ZENDOC_TURN_EXTERNAL_IP:?' in script


def test_no_aws_credential_mounts_or_false_backup_upload_claims():
    compose = _read("deploy/aws/compose.yaml")
    backup = compose.split("\n  backup:\n", 1)[1].split("\nvolumes:\n", 1)[0]
    assert "~/.aws" not in backup
    assert "/root/.aws" not in backup
    assert "/var/backups/zendoc:/backups" in backup
    script = _read("scripts/postgres_backup.py")
    assert '"off_instance_copy_verified": False' in script
    assert '"restore_drill_verified": False' in script
    assert "It does not upload" in script


def test_reviewed_aws_gateway_does_not_override_flask_clickjacking_denial():
    caddy = _read("deploy/aws/Caddyfile")
    assert 'respond "Forbidden" 403' in caddy
    assert "X-Frame-Options" not in caddy
    app_headers = _read("zendoc/security_headers.py")
    assert '"X-Frame-Options", "DENY"' in app_headers


def test_stacked_regression_is_fail_closed():
    ci = _read(".github/workflows/stacked-release-regression.yml")
    assert "run: python -m pytest -q" in ci
    assert '|| echo "Tests completed with warnings"' not in ci
    assert "python scripts/ci_postgres_readiness.py" in ci
