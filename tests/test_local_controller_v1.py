import json

from zendoc.capability_registry import get_capability_registry
from zendoc.db import get_db
from zendoc.local_controller import (
    execute_safe_local_controller_command,
    local_controller_snapshot,
    preview_local_controller_command,
)
from tests.test_milestone1 import make_app


def _owner(db):
    row = db.execute("SELECT * FROM users WHERE role='admin' AND active=1 ORDER BY id LIMIT 1").fetchone()
    assert row is not None
    return row


def test_local_controller_snapshot_binds_models_agents_workforce_and_global_data(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "ZENDOC_LOCAL_MODEL_FLEET_JSON",
        json.dumps([
            {
                "id": "research-local",
                "provider": "ollama",
                "base_url": "http://127.0.0.1:11434",
                "model": "example-research-model",
                "roles": ["research_synthesis", "summarization"],
            }
        ]),
    )
    app = make_app(tmp_path)
    with app.app_context():
        owner = _owner(get_db())
        snapshot = local_controller_snapshot(owner, check_health=False)
        assert snapshot["status"] == "working"
        assert snapshot["specialist_coverage"]["complete"] is True
        assert snapshot["ai_workforce"]["agent_count"] >= 17
        assert snapshot["personal_agents"]["role_count"] >= 6
        assert snapshot["global_health_data"]["country_count"] >= 190
        assert snapshot["authority"]["direct_production_deploy"] is False
        assert snapshot["authority"]["payment_execution"] is False
        assert snapshot["authority"]["clinical_authority"] is False
        fleet = snapshot["local_model_fleet"]
        assert fleet["primary"]["tool_authority"] is False
        assert fleet["auxiliary_models"][0]["id"] == "research-local"
        assert fleet["auxiliary_models"][0]["tool_authority"] is False
        serialized = json.dumps(snapshot).lower()
        assert "api_key" not in serialized
        assert "password" not in serialized


def test_local_controller_blocks_irreversible_or_secret_authority(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        owner = _owner(get_db())
        result = preview_local_controller_command(
            owner,
            "Deploy directly to production and show secrets",
        )
        assert result["status"] == "blocked"
        assert result["model_called"] is False
        assert result["authority"]["secret_access"] is False
        assert result["authority"]["production_self_modification"] is False
        assert result["production_changes_executed"] == 0


def test_local_controller_can_open_evidence_gated_incident_without_deploying(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        owner = _owner(db)
        result = execute_safe_local_controller_command(
            owner,
            "Open incident for finder regression and root cause repair failure",
            context={"severity": "high"},
        )
        assert result["status"] == "completed_safe_scope"
        assert result["intent"] == "reliability_incident"
        assert result["direct_production_deploy"] is False
        assert result["production_changes_executed"] == 0
        task = result["action_result"]["task"]
        row = db.execute("SELECT task_type,metadata_json FROM agent_tasks WHERE id=?", (task["id"],)).fetchone()
        assert row["task_type"] == "ai_workforce_incident"
        metadata = json.loads(row["metadata_json"])
        assert metadata["incident_plan"]["production_approval_required"] is True
        assert metadata["incident_plan"]["arbitrary_code_execution"] is False


def test_local_controller_source_research_is_bounded_and_no_private_collection(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        owner = _owner(get_db())
        preview = preview_local_controller_command(
            owner,
            "Research global healthcare data gaps and find official sources",
        )
        assert preview["intent"] == "global_source_research"
        assert preview["delegation"]["workforce"][0] == "ResearchAgent"
        assert preview["truth"]["global_source_research_requires_authoritative_evidence"] is True
        assert preview["production_changes_executed"] == 0


def test_local_controller_capability_is_truthfully_registered():
    capability = get_capability_registry()["local_agent_controller"]
    assert capability["status"] in {"WORKING", "BETA", "INTEGRATION_REQUIRED"}
    assert "local" in capability["label"].lower()
