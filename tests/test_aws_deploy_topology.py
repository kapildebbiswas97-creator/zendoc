"""Static AWS deployment safety guardrails (do not need a live AWS account)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AWS = ROOT / "deploy" / "aws"


def test_aws_files_present():
    for path in ("compose.yaml", "Caddyfile", ".env.example", "backup.Dockerfile", "turn-entrypoint.sh"):
        assert (AWS / path).is_file()


def test_aws_postgresql_is_private():
    compose = (AWS / "compose.yaml").read_text(encoding="utf-8")
    db = compose.split("\n  db:\n", 1)[1].split("\n  web:\n", 1)[0]
    assert "\n    ports:" not in db
    assert "\n  backend:\n    internal: true" in compose


def test_aws_fails_closed_and_identifies_platform():
    compose = (AWS / "compose.yaml").read_text(encoding="utf-8")
    assert "ZENDOC_DEPLOYMENT_PLATFORM: aws_ec2" in compose
    assert 'ZENDOC_REQUIRE_DURABLE_DATABASE: "true"' in compose
    assert "ZENDOC_PUBLIC_RELEASE_REQUIRED: " in compose
    assert "ZENDOC_PERSISTENCE_VERIFIED: " in compose
    assert "ZENDOC_BACKUP_VERIFIED: " in compose
    caddy = (AWS / "Caddyfile").read_text(encoding="utf-8")
    assert "X-Zendoc-Gateway-Token" in caddy
    assert 'respond "Forbidden" 403' in caddy
    assert "web:8000" in caddy
