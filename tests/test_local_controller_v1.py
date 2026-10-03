import json

from zendoc.capability_registry import get_capability_registry
from zendoc.db import get_db
from zendoc.local_controller import (
    execute_safe_local_controller_command,
    local_controller_snapshot,
    local_model_fleet_snapshot,
    preview_local_controller_command,
)
from tests.test_milestone1 import api_token, make_app


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



def test_local_model_fleet_rejects_malformed_and_oversized_configuration(monkeypatch):
    monkeypatch.setenv("ZENDOC_LOCAL_MODEL_FLEET_JSON", "{not-json")
    malformed = local_model_fleet_snapshot()
    assert malformed["auxiliary_models"][0]["error_category"] == "invalid_json"

    monkeypatch.setenv(
        "ZENDOC_LOCAL_MODEL_FLEET_JSON",
        json.dumps([
            {
                "id": f"aux-{index}",
                "provider": "ollama",
                "model": "example-model",
                "roles": ["summarization"],
            }
            for index in range(9)
        ]),
    )
    oversized = local_model_fleet_snapshot()
    assert oversized["auxiliary_models"][0]["error_category"] == "fleet_limit_exceeded"
    assert oversized["resource_limits"]["max_auxiliary_models"] == 8
    assert oversized["resource_limits"]["max_auxiliary_attempts_per_command"] == 2


def test_local_model_fleet_rejects_unsafe_endpoint_and_loose_boolean(monkeypatch):
    monkeypatch.setenv(
        "ZENDOC_LOCAL_MODEL_FLEET_JSON",
        json.dumps([
            {
                "id": "unsafe-remote",
                "provider": "ollama",
                "base_url": "https://example.com",
                "model": "example-model",
                "roles": ["operations_analysis"],
            },
            {
                "id": "loose-bool",
                "provider": "ollama",
                "base_url": "http://127.0.0.1:11434",
                "model": "example-model",
                "roles": ["operations_analysis"],
                "allow_private_network": "false",
            },
        ]),
    )
    fleet = local_model_fleet_snapshot()["auxiliary_models"]
    assert fleet[0]["error_category"] == "unsafe_provider_url"
    assert fleet[1]["error_category"] == "invalid_profile_settings"


def test_local_controller_routes_specialized_advisory_to_matching_auxiliary(tmp_path, monkeypatch):
    calls = []

    class FakeProvider:
        def __init__(self, settings):
            self.settings = settings

        def infer(self, request):
            calls.append((self.settings.model, request.task_type, request.max_output_tokens))
            return type(
                "Result",
                (),
                {
                    "success": True,
                    "provider": "local_ollama",
                    "model": self.settings.model,
                    "output": {"text": "bounded auxiliary analysis", "data": {}},
                    "error_category": None,
                    "latency_ms": 3,
                },
            )()

    monkeypatch.setattr(
        "zendoc.local_controller.create_local_ai_provider",
        lambda settings: FakeProvider(settings),
    )
    monkeypatch.setenv(
        "ZENDOC_LOCAL_MODEL_FLEET_JSON",
        json.dumps([
            {
                "id": "language-local",
                "provider": "ollama",
                "model": "language-model",
                "roles": ["translation"],
                "priority": 1,
            },
            {
                "id": "ops-local",
                "provider": "ollama",
                "model": "ops-model",
                "roles": ["operations_analysis"],
                "priority": 5,
                "max_output_tokens": 256,
            },
        ]),
    )
    app = make_app(tmp_path)
    with app.app_context():
        owner = _owner(get_db())
        result = preview_local_controller_command(
            owner,
            "Inspect release deployment evidence for Vercel and OCI",
        )
    advisory = result["model_advisory"]
    assert result["intent"] == "release_control"
    assert advisory["routing_reason"] == "local_auxiliary_role"
    assert advisory["selected_profile_id"] == "ops-local"
    assert advisory["selected_role"] == "operations_analysis"
    assert advisory["text"] == "bounded auxiliary analysis"
    assert calls == [("ops-model", "owner_operational_summary", 256)]


def test_local_controller_auxiliary_failure_falls_back_without_cloud(tmp_path, monkeypatch):
    class FailingProvider:
        def infer(self, request):
            return type(
                "Result",
                (),
                {
                    "success": False,
                    "provider": "local_ollama",
                    "model": "ops-model",
                    "output": {},
                    "error_category": "provider_unavailable",
                    "latency_ms": 1,
                },
            )()

    monkeypatch.setattr(
        "zendoc.local_controller.create_local_ai_provider",
        lambda settings: FailingProvider(),
    )
    monkeypatch.setenv(
        "ZENDOC_LOCAL_MODEL_FLEET_JSON",
        json.dumps([
            {
                "id": "ops-local",
                "provider": "ollama",
                "model": "ops-model",
                "roles": ["operations_analysis"],
            }
        ]),
    )
    monkeypatch.setenv("ZENDOC_LOCAL_AI_ENABLED", "0")
    monkeypatch.delenv("ZENDOC_LOCAL_AI_MODEL", raising=False)
    app = make_app(tmp_path)
    with app.app_context():
        owner = _owner(get_db())
        result = preview_local_controller_command(owner, "Inspect release deployment status")
    advisory = result["model_advisory"]
    assert advisory["provider"] == "local_fallback"
    assert advisory["fallback_used"] is True
    assert advisory["attempts"][0]["error_category"] == "provider_unavailable"
    assert advisory["selected_profile_id"] is None


def test_local_controller_api_rejects_non_owner(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    token = api_token(client, "local-controller-patient@example.com")
    response = client.get(
        "/api/v1/admin/local-controller/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
