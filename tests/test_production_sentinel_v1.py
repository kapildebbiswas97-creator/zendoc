from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "production-sentinel.yml"


def test_production_sentinel_is_scheduled_and_manual():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'cron: "17 * * * *"' in text
    assert "workflow_dispatch:" in text
    assert "ZENDOC_DEPLOYMENT_URL" in text
    assert "ZENDOC_EXPECTED_COMMIT" in text


def test_production_sentinel_verifies_real_oci_postgres_release():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "scripts/verify_deployment.py" in text
    assert "--require-platform oci" in text
    assert "--require-engine postgresql" in text
    assert "--require-persistence-verified" in text
    assert "scripts/verify_public_launch.py" in text


def test_production_sentinel_manages_incidents_without_sensitive_payloads():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "issues: write" in text
    assert "Production Sentinel: live verification failing" in text
    assert "No credentials, request bodies, medical content, or raw production exceptions" in text
    assert "state: 'closed'" in text
    assert "secrets." not in text


def test_production_sentinel_never_deploys_or_modifies_code():
    text = WORKFLOW.read_text(encoding="utf-8")

    forbidden = (
        "git push",
        "merge_pull_request",
        "vercel deploy",
        "vercel promote",
        "kubectl apply",
        "terraform apply",
        "docker compose up",
    )
    for marker in forbidden:
        assert marker not in text
