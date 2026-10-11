"""Exact AWS EC2/OCI deployment identity checks, fully offline."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

from scripts import verify_deployment


ROOT = Path(__file__).resolve().parents[1]


def _healthy_origin(*, platform="aws_ec2", verified=True):
    sha = "c" * 40

    def get_json(url, _timeout):
        if url.endswith("/api/v1/health"):
            return 200, {"status": "ok", "service": "zendoc", "check": "liveness"}
        if url.endswith("/api/v1/ready"):
            return 200, {
                "status": "ready",
                "database": "reachable",
                "database_engine": "postgresql",
                "persistence_verified": verified,
                "migrations": {"ready": True, "missing_migrations": []},
                "schema": {"ready": True, "missing_tables": []},
                "deployment": {
                    "platform": platform,
                    "git_commit": sha,
                    "git_commit_short": sha[:12],
                },
            }
        raise AssertionError("Verifier requested an unexpected URL.")

    return sha, get_json


def _verify(monkeypatch, expected_platform, actual_platform="aws_ec2", persisted=True):
    sha, fake_fetch = _healthy_origin(platform=actual_platform, verified=persisted)
    monkeypatch.setattr(verify_deployment, "get_json", fake_fetch)
    monkeypatch.setattr(sys, "argv", [
        "verify_deployment.py",
        "https://origin.example.test",
        "--expected-commit", sha,
        "--require-platform", expected_platform,
        "--require-engine", "postgresql",
        "--require-persistence-verified",
        "--attempts", "1",
    ])
    return verify_deployment.main()


def test_real_aws_platform_identity_is_accepted_with_exact_git_and_persistence(monkeypatch):
    assert _verify(monkeypatch, "aws_ec2") == 0


def test_oci_platform_check_fails_closed_on_an_aws_origin(monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        _verify(monkeypatch, "oci")
    assert exc.value.code == 1
    assert "Expected deployment platform 'oci'" in capsys.readouterr().err


def test_aws_origin_cannot_pass_without_verified_persistence(monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        _verify(monkeypatch, "aws_ec2", persisted=False)
    assert exc.value.code == 1
    assert "persistence verification is not confirmed" in capsys.readouterr().err


def test_release_workflow_requires_explicit_platform_and_verifies_commit_and_postgres():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "deployment_platform:" in workflow
    assert "ZENDOC_DEPLOYMENT_PLATFORM" in workflow
    assert '--require-platform "$EXPECTED_PLATFORM"' in workflow
    assert 'oci|aws_ec2' in workflow
    assert '--expected-commit' in workflow
    assert '--require-engine postgresql' in workflow
    assert '--require-persistence-verified' in workflow
    assert "--require-platform oci" not in workflow
