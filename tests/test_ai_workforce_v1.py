from zendoc.ai_workforce import (
    build_incident_plan,
    intake_failed_events,
    workforce_manifest,
)
from zendoc.db import get_db
from zendoc.event_bus import publish_event
from tests.test_milestone1 import make_app


def test_ai_workforce_contains_full_backend_team_and_owner_release_gate():
    manifest = workforce_manifest()
    ids = {agent["agent_id"] for agent in manifest["agents"]}
    assert {
        "IncidentAgent",
        "EngineeringAgent",
        "RootCauseAgent",
        "RepairAgent",
        "SecurityAgent",
        "TestAgent",
        "QAAgent",
        "InfrastructureAgent",
        "DataAgent",
        "IntegrationAgent",
        "ProductAgent",
        "SupportAgent",
        "CommunicationsAgent",
        "ResearchAgent",
        "ManagerAgent",
        "ReleaseAgent",
        "KnowledgeAgent",
    } <= ids
    approval_stage = next(stage for stage in manifest["incident_pipeline"] if stage["stage"] == "production_approval")
    assert approval_stage["automatic"] is False
    assert approval_stage["gate"] == "configured_owner_approval"


def test_incident_plan_allows_automation_but_not_production_or_clinical_authority():
    plan = build_incident_plan("Find Care returned a gateway error", severity="high")
    assert plan["current_stage"] == "detect_and_classify"
    assert plan["production_approval_required"] is True
    assert plan["arbitrary_code_execution"] is False
    assert plan["secret_access"] is False
    assert plan["clinical_authority"] is False
    assert plan["payment_authority"] is False
    assert plan["emergency_dispatch_authority"] is False


def test_failed_events_are_deduplicated_into_persistent_workforce_cases(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        owner = db.execute(
            "SELECT * FROM users WHERE role='admin' AND active=1 ORDER BY id LIMIT 1"
        ).fetchone()
        event = publish_event(
            "system.test.failure",
            actor=owner,
            entity_type="test_boundary",
            entity_id="find-care",
            status="error",
            error="Synthetic upstream timeout; token=secret-like-value",
            payload={"safe": True},
            agent_name="InfrastructureAgent",
        )

        first = intake_failed_events(owner)
        second = intake_failed_events(owner)

        assert first["created_count"] == 1
        assert second["created_count"] == 0
        assert second["existing_count"] >= 1

        rows = db.execute(
            "SELECT * FROM agent_tasks WHERE task_type='ai_workforce_incident'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["assigned_agent"] == "OperationsAgent"
        assert rows[0]["idempotency_key"] == f"ai-workforce:event:{event['id']}"
