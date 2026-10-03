from pathlib import Path
from types import SimpleNamespace

from zendoc import operations_digest
from tests.test_milestone1 import make_app


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy" / "oci" / "compose.yaml"
WORKER = ROOT / "scripts" / "run_operations_worker.py"


def test_oci_operations_worker_runs_on_private_backend_only():
    text = COMPOSE.read_text(encoding="utf-8")
    worker = text.split("  ops-worker:", 1)[1].split("\n  caddy:", 1)[0]

    assert 'command: ["python", "scripts/run_operations_worker.py"]' in worker
    assert "restart: unless-stopped" in worker
    assert "ZENDOC_OPS_CYCLE_SECONDS" in worker
    assert "ZENDOC_OPS_DIGEST_EMAIL" in worker
    assert "- backend" in worker
    assert "- edge" not in worker
    assert "ports:" not in worker
    assert "expose:" not in worker


def test_operations_worker_has_no_code_deploy_or_arbitrary_execution_path():
    text = WORKER.read_text(encoding="utf-8").lower()
    forbidden = (
        "subprocess",
        "os.system",
        "git push",
        "git merge",
        "vercel deploy",
        "vercel promote",
        "kubectl",
        "terraform",
        "shell=true",
    )
    for marker in forbidden:
        assert marker not in text


def test_owner_operations_cycle_emits_bounded_in_app_digest(monkeypatch, tmp_path):
    app = make_app(tmp_path)
    deliveries = []

    monkeypatch.setattr(
        operations_digest,
        "run_safe_operations_automation",
        lambda _actor: {
            "requeued_count": 2,
            "waiting_human_or_approval": 1,
            "permanent_or_exhausted_failures": 0,
            "safety": {
                "moves_money": False,
                "prescribes": False,
                "dispatches_emergency": False,
                "arbitrary_execution": False,
            },
        },
    )
    monkeypatch.setattr(
        operations_digest,
        "integration_readiness_snapshot",
        lambda: {"ready_count": 5, "total_count": 8, "external_blocker_count": 3},
    )
    monkeypatch.setattr(
        operations_digest,
        "ingestion_freshness_report",
        lambda _actor, recent_batch_limit=20: {
            "source_count": 4,
            "sources": [{"source_id": "official_source", "refresh_priority": "P0"}],
        },
    )
    monkeypatch.setattr(
        operations_digest,
        "readiness_report",
        lambda: {"status": "ready"},
    )
    monkeypatch.setattr(
        operations_digest,
        "list_alerts",
        lambda *_args, **_kwargs: [{"severity": "high"}],
    )
    monkeypatch.setattr(operations_digest, "_recent_digest_exists", lambda *_args, **_kwargs: False)

    def fake_delivery(user_id, title, message, channel="in_app", template_type=None):
        deliveries.append({
            "user_id": user_id,
            "title": title,
            "message": message,
            "channel": channel,
            "template_type": template_type,
        })
        return SimpleNamespace(to_dict=lambda: {"channel": channel, "status": "delivered"})

    monkeypatch.setattr(operations_digest, "deliver_notification", fake_delivery)

    with app.app_context():
        from zendoc.db import get_db

        owner = get_db().execute(
            "SELECT * FROM users WHERE email='admin@example.com'"
        ).fetchone()
        result = operations_digest.run_owner_operations_cycle(owner, email_owner=False)

    assert result["status"] == "completed"
    assert result["digest_created"] is True
    assert result["active_alert_count"] == 1
    assert result["integration_blocker_count"] == 3
    assert result["urgent_data_source_count"] == 1
    assert len(deliveries) == 1
    assert deliveries[0]["channel"] == "in_app"
    assert deliveries[0]["template_type"] == operations_digest.DIGEST_TEMPLATE
    assert "No autonomous prescribing" in deliveries[0]["message"]
