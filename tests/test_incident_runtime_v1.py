import json

import pytest

from zendoc.ai_workforce import intake_failed_events
from zendoc.db import get_db
from zendoc.event_bus import publish_event
from zendoc.incident_runtime import (
    advance_incident_case,
    incident_runtime_snapshot,
    record_owner_production_approval,
)
from zendoc.operations_automation import run_safe_operations_automation
from tests.test_milestone1 import make_app


def _owner(db):
    row = db.execute("SELECT * FROM users WHERE role='admin' AND active=1 ORDER BY id LIMIT 1").fetchone()
    assert row is not None
    return row


def _incident(app):
    with app.app_context():
        db = get_db()
        owner = _owner(db)
        event = publish_event(
            "system.runtime.failure",
            actor=owner,
            entity_type="route",
            entity_id="/finder",
            status="error",
            error="Synthetic upstream timeout token=secret-value",
            payload={"route": "/finder", "status_code": 500},
            agent_name="InfrastructureAgent",
        )
        intake_failed_events(owner)
        row = db.execute(
            "SELECT id FROM agent_tasks WHERE task_type='ai_workforce_incident' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return int(row["id"]), int(event["id"])


def _preproduction_evidence():
    return {
        "reproduce": {
            "verified": True,
            "reproduced": True,
            "source_ref": "sandbox://repro/incident-1",
            "summary": "Failure reproduced in an isolated test boundary.",
        },
        "root_cause": {
            "verified": True,
            "source_ref": "analysis://root-cause/incident-1",
            "summary": "Evidence-backed root cause isolated.",
            "root_cause": "A bounded synthetic adapter failure caused the reproduced error path.",
        },
        "repair_proposal": {
            "source_ref": "git://proposal/incident-1",
            "summary": "Minimal repair prepared for review.",
            "change_ref": "commit:deadbeef",
            "regression_plan": "Run the targeted regression, critical suite, full suite and preview verification.",
        },
        "security_review": {
            "passed": True,
            "source_ref": "ci://security/incident-1",
            "summary": "Security review passed for the proposed repair.",
        },
        "regression_tests": {
            "passed": True,
            "source_ref": "ci://tests/incident-1",
            "summary": "Targeted and required regression tests passed.",
        },
        "preview_qa": {
            "passed": True,
            "source_ref": "preview://qa/incident-1",
            "summary": "Preview journey verification passed.",
        },
    }


def test_safe_operations_auto_classifies_incident_but_stops_for_reproduction_evidence(tmp_path):
    app = make_app(tmp_path)
    task_id, _event_id = _incident(app)
    with app.app_context():
        db = get_db()
        owner = _owner(db)
        result = run_safe_operations_automation(owner)
        assert result["workforce_cases_advanced"] >= 1
        snapshot = incident_runtime_snapshot(owner, task_id)
        assert snapshot["task_status"] == "waiting_human"
        assert snapshot["runtime"]["stages"]["detect_and_classify"]["status"] == "completed"
        assert snapshot["runtime"]["current_stage"] == "reproduce"
        assert snapshot["runtime"]["blocker"] == "EVIDENCE_REQUIRED"
        assert snapshot["safety"]["production_promotion_executed"] is False


def test_incident_pipeline_requires_evidence_and_stops_at_owner_production_gate(tmp_path):
    app = make_app(tmp_path)
    task_id, _event_id = _incident(app)
    with app.app_context():
        db = get_db()
        owner = _owner(db)

        initial = advance_incident_case(owner, task_id)
        assert initial["runtime"]["current_stage"] == "reproduce"
        with pytest.raises(ValueError):
            advance_incident_case(
                owner,
                task_id,
                evidence={
                    "reproduce": {
                        "verified": True,
                        "reproduced": False,
                        "source_ref": "sandbox://negative",
                        "summary": "Could not reproduce.",
                    }
                },
            )

        gated = advance_incident_case(owner, task_id, evidence=_preproduction_evidence())
        assert gated["task_status"] == "waiting_approval"
        assert gated["runtime"]["current_stage"] == "production_approval"
        assert gated["runtime"]["owner_approval_recorded"] is False
        assert gated["runtime"]["production_promotion_executed"] is False
        assert gated["runtime"]["stages"]["release_evidence"]["status"] == "completed"


def test_owner_approval_records_gate_but_never_deploys_and_post_release_health_closes_case(tmp_path):
    app = make_app(tmp_path)
    task_id, _event_id = _incident(app)
    with app.app_context():
        db = get_db()
        owner = _owner(db)
        advance_incident_case(owner, task_id, evidence=_preproduction_evidence())

        approved = record_owner_production_approval(
            owner,
            task_id,
            approval_reference="owner-approval://incident-1",
        )
        assert approved["task_status"] == "waiting_human"
        assert approved["runtime"]["current_stage"] == "post_release_verify"
        assert approved["runtime"]["owner_approval_recorded"] is True
        assert approved["runtime"]["production_promotion_executed"] is False

        closed = advance_incident_case(
            owner,
            task_id,
            evidence={
                "post_release_verify": {
                    "health_ok": True,
                    "ready_ok": True,
                    "deployed_commit": "abc123",
                    "deployment_url": "https://example.invalid",
                    "source_ref": "health://deployment/abc123",
                    "summary": "Live health and readiness probes matched the deployed commit.",
                }
            },
        )
        assert closed["task_status"] == "completed"
        assert closed["runtime"]["current_stage"] is None
        assert closed["runtime"]["post_release_verified"] is True
        assert closed["runtime"]["knowledge_record"]["contains_raw_health_content"] is False
        assert closed["runtime"]["knowledge_record"]["contains_secrets"] is False


def test_incident_metadata_does_not_store_secret_like_event_text_verbatim(tmp_path):
    app = make_app(tmp_path)
    task_id, _event_id = _incident(app)
    with app.app_context():
        db = get_db()
        owner = _owner(db)
        advance_incident_case(owner, task_id)
        row = db.execute("SELECT metadata_json FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
        metadata = json.loads(row["metadata_json"])
        runtime_text = json.dumps(metadata["incident_runtime"], sort_keys=True)
        assert "secret-value" not in runtime_text
