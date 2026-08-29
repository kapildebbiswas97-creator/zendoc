import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from zendoc.agent_approvals import create_approval
from zendoc.agent_task_engine import create_agent_task, execute_safe_task, retry_task
from zendoc.db import get_db, init_db
from zendoc.event_bus import publish_event
from zendoc.model_router import ModelRouter
from zendoc.notification_providers import deliver_notification

from tests.test_milestone1 import login_web, make_client
from tests.test_milestone7 import api_token, headers, login_api, user_id


def owner_token(client):
    response = login_api(client, "admin@example.com", "admin", "AdminStrong123")
    assert response.status_code == 200
    return response.json["token"]


def test_owner_only_admin_registration_and_role_escalation_are_blocked(tmp_path):
    app, client = make_client(tmp_path)
    assert client.get("/register/admin").status_code == 403
    assert client.post(
        "/api/v1/auth/register",
        json={"name": "Attacker", "email": "attacker@example.com", "password": "StrongPass123", "role": "Admin"},
    ).status_code == 403

    patient_token = api_token(client, "role-injection@example.com")
    patient_id = user_id(app, "role-injection@example.com")
    with app.app_context():
        db = get_db()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE users SET role='admin' WHERE id=?", (patient_id,))
        db.rollback()
        db.execute("UPDATE users SET role='patient' WHERE role='admin'")
        db.execute("UPDATE users SET role='admin' WHERE id=?", (patient_id,))
        db.commit()

    assert client.get("/api/v1/admin/infrastructure", headers=headers(patient_token)).status_code == 403
    forged_login = login_api(client, "role-injection@example.com", "admin", "StrongPass123")
    assert forged_login.status_code == 401


def test_m8_migration_schema_and_single_owner_index(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        db = get_db()
        tables = {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"agent_tasks", "agent_task_attempts", "agent_alerts", "model_execution_logs", "notification_deliveries", "schema_migrations"} <= tables
        approval_columns = {row["name"] for row in db.execute("PRAGMA table_info(agent_approvals)")}
        assert {"task_id", "risk_level", "approver_user_id", "expires_at", "created_at", "resolved_by"} <= approval_columns
        event_columns = {row["name"] for row in db.execute("PRAGMA table_info(platform_events)")}
        assert {"event_type", "payload_json", "correlation_id", "idempotency_key"} <= event_columns
        assert db.execute("SELECT 1 FROM schema_migrations WHERE version='m8_agent_platform_v1'").fetchone()
        assert db.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_users_single_admin'").fetchone()

        # Simulate the exact M7 table shapes and verify additive M8 upgrade ordering.
        db.executescript(
            """
            DROP TABLE agent_approvals;
            CREATE TABLE agent_approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER REFERENCES agent_runs(id) ON DELETE CASCADE,
                actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                operation_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                requested_at TEXT NOT NULL,
                decided_at TEXT,
                decision_note TEXT
            );
            DROP INDEX idx_platform_events_idempotency;
            DROP TABLE platform_events;
            CREATE TABLE platform_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                agent_name TEXT,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT,
                status TEXT NOT NULL DEFAULT 'info',
                error TEXT,
                approval_state TEXT NOT NULL DEFAULT 'not_required',
                duration_ms INTEGER,
                created_at TEXT NOT NULL
            );
            DELETE FROM schema_migrations WHERE version='m8_agent_platform_v1';
            """
        )
        init_db()
        assert {"task_id", "risk_level", "created_at"} <= {row["name"] for row in db.execute("PRAGMA table_info(agent_approvals)")}
        assert {"event_type", "payload_json", "idempotency_key"} <= {row["name"] for row in db.execute("PRAGMA table_info(platform_events)")}
        assert db.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_platform_events_idempotency'").fetchone()


def test_model_router_truthful_unconfigured_slm_and_persistent_fallback_log(tmp_path, monkeypatch):
    app, client = make_client(tmp_path)
    for key in ("ZENDOC_SLM_ENABLED", "ZENDOC_SLM_MODEL", "ZENDOC_AI_PROVIDER", "ZENDOC_AI_API_KEY", "ZENDOC_AI_MODEL"):
        monkeypatch.delenv(key, raising=False)
    patient_id = user_id(app, "admin@example.com")
    with app.app_context():
        router = ModelRouter()
        assert router.status()["local_slm"]["message"] == "Local SLM integration ready — model not configured."
        response = router.route("hello", intent="general", actor_id=patient_id)
        assert response.provider == "local_fallback"
        assert response.success is True
        log = get_db().execute("SELECT * FROM model_execution_logs ORDER BY id DESC LIMIT 1").fetchone()
        assert log["provider"] == "local_fallback"
        assert log["actor_id"] == patient_id

    status = client.get("/api/v1/admin/model-router", headers=headers(owner_token(client)))
    assert status.status_code == 200
    assert status.json["local_slm"]["status"] == "integration_required"


def test_agent_and_tool_registries_are_permission_filtered_and_have_no_arbitrary_execution(tmp_path):
    _app, client = make_client(tmp_path)
    patient = api_token(client, "registry-patient@example.com")
    tools = client.get("/api/v1/agent/tools", headers=headers(patient)).json["tools"]
    names = {tool["name"] for tool in tools}
    assert "get_platform_summary" not in names
    assert not {"execute_shell", "execute_arbitrary_sql", "eval_python", "run_any_command"} & names
    agents = client.get("/api/v1/agent/registry", headers=headers(patient)).json["agents"]
    assert "OperationsAgent" not in {agent["identifier"] for agent in agents}


def test_core_agent_plans_executes_and_persists_owner_summary(tmp_path):
    app, client = make_client(tmp_path)
    token = owner_token(client)
    response = client.post(
        "/api/v1/agent/message",
        json={"message": "Give me today's operations summary"},
        headers=headers(token),
    )
    assert response.status_code == 200
    assert response.json["intent"] == "platform_health"
    assert response.json["plan"]["assigned_agent"] == "OperationsAgent"
    assert response.json["plan"]["steps"][0]["tool_name"] == "get_platform_summary"
    with app.app_context():
        task = get_db().execute("SELECT * FROM agent_tasks WHERE id=?", (response.json["task_id"],)).fetchone()
        assert task["status"] == "completed"
        assert task["attempt_count"] == 1
        assert task["duration_ms"] is not None
        call = get_db().execute("SELECT * FROM agent_tool_calls WHERE run_id=?", (response.json["run_id"],)).fetchone()
        assert call["tool_name"] == "get_platform_summary"


def test_consent_plan_waits_for_human_and_never_executes_share_tool(tmp_path):
    app, client = make_client(tmp_path)
    token = api_token(client, "consent-plan@example.com")
    response = client.post(
        "/api/v1/agent/message",
        json={"message": "share medical record with doctor"},
        headers=headers(token),
    )
    assert response.status_code == 200
    assert response.json["requires_confirmation"] is True
    assert response.json["plan"]["steps"] == []
    with app.app_context():
        task = get_db().execute("SELECT status,attempt_count FROM agent_tasks WHERE id=?", (response.json["task_id"],)).fetchone()
        assert dict(task) == {"status": "waiting_human", "attempt_count": 0}
        assert get_db().execute("SELECT COUNT(*) c FROM agent_tool_calls WHERE run_id=?", (response.json["run_id"],)).fetchone()["c"] == 0


def test_emergency_is_deterministic_first_and_does_not_invoke_model(tmp_path):
    app, client = make_client(tmp_path)
    token = api_token(client, "emergency-m8@example.com")
    response = client.post("/api/v1/agent/message", json={"message": "I have chest pain"}, headers=headers(token))
    assert response.status_code == 200
    assert response.json["intent"] == "emergency"
    assert response.json["plan"]["assigned_agent"] == "SafetyAgent"
    assert response.json["plan"]["steps"] == []
    with app.app_context():
        task = get_db().execute("SELECT status,assigned_agent FROM agent_tasks WHERE id=?", (response.json["task_id"],)).fetchone()
        assert task["status"] == "completed"
        assert task["assigned_agent"] == "SafetyAgent"
        assert get_db().execute("SELECT COUNT(*) c FROM model_execution_logs").fetchone()["c"] == 0


def test_agent_task_idempotency_bounded_execution_and_retry_classification(tmp_path):
    app, client = make_client(tmp_path)
    token = owner_token(client)
    body = {"task_type": "proactive_alert_check", "idempotency_key": "owner-alert-scan-1"}
    first = client.post("/api/v1/admin/agent/tasks", json=body, headers=headers(token))
    second = client.post("/api/v1/admin/agent/tasks", json=body, headers=headers(token))
    assert first.status_code == second.status_code == 201
    assert first.json["task"]["id"] == second.json["task"]["id"]
    executed = client.post(f"/api/v1/agent/tasks/{first.json['task']['id']}/execute", headers=headers(token))
    assert executed.status_code == 200
    assert executed.json["task"]["status"] == "completed"
    assert client.post(f"/api/v1/agent/tasks/{first.json['task']['id']}/execute", headers=headers(token)).status_code == 400

    with app.app_context():
        owner = dict(get_db().execute("SELECT * FROM users WHERE role='admin'").fetchone())
        failed = create_agent_task("proactive_alert_check", owner["id"], "OperationsAgent", actor=owner)

        def timeout(_task):
            raise TimeoutError("provider timeout")

        failed = execute_safe_task(failed["id"], owner, handler_fn=timeout)
        assert failed["last_error_category"] == "timeout"
        assert retry_task(failed["id"], owner)["status"] == "queued"


def test_agent_tasks_and_realtime_events_are_user_scoped(tmp_path):
    app, client = make_client(tmp_path)
    first_token = api_token(client, "scope-one@example.com")
    second_token = api_token(client, "scope-two@example.com")
    result = client.post("/api/v1/agent/message", json={"message": "check my unread messages"}, headers=headers(first_token)).json
    task_id = result["task_id"]
    assert client.get(f"/api/v1/agent/tasks/{task_id}", headers=headers(second_token)).status_code == 403
    assert all(task["id"] != task_id for task in client.get("/api/v1/agent/tasks", headers=headers(second_token)).json["tasks"])
    assert client.get("/api/v1/events", headers=headers(second_token)).json["events"] == []
    owner_events = client.get("/api/v1/events", headers=headers(owner_token(client))).json["events"]
    assert any(event["entity_id"] == str(task_id) for event in owner_events)


def test_owner_approval_engine_rejects_patient_and_transitions_linked_task(tmp_path):
    app, client = make_client(tmp_path)
    patient = api_token(client, "approval-patient@example.com")
    doctor = api_token(client, "approval-doctor@example.com", role="doctor")
    owner = owner_token(client)
    with app.app_context():
        owner_row = dict(get_db().execute("SELECT * FROM users WHERE role='admin'").fetchone())
        task = create_agent_task(
            "proactive_alert_check", owner_row["id"], "OperationsAgent", risk_level="owner_approval", actor=owner_row
        )
        approval = create_approval(owner_row["id"], "retry_platform_task", "Retry bounded operational scan", task_id=task["id"])
        doctor_approval = create_approval(
            user_id(app, "approval-patient@example.com"),
            "review_care_action",
            "Doctor review required",
            risk_level="doctor_approval",
            approver_user_id=user_id(app, "approval-doctor@example.com"),
        )
        get_db().execute("UPDATE agent_tasks SET status='waiting_approval' WHERE id=?", (task["id"],))
        get_db().commit()
    denied = client.post(
        f"/api/v1/admin/approvals/{approval['id']}/decision",
        json={"decision": "approved"}, headers=headers(patient),
    )
    assert denied.status_code == 403
    approved = client.post(
        f"/api/v1/admin/approvals/{approval['id']}/decision",
        json={"decision": "approved", "note": "Owner reviewed"}, headers=headers(owner),
    )
    assert approved.status_code == 200
    assert approved.json["approval"]["resolved_by"] is not None
    with app.app_context():
        assert get_db().execute("SELECT status FROM agent_tasks WHERE id=?", (task["id"],)).fetchone()["status"] == "queued"
    assert client.post(
        f"/api/v1/admin/approvals/{approval['id']}/decision", json={"decision": "rejected"}, headers=headers(owner)
    ).status_code == 400
    assert client.post(
        f"/api/v1/agent/approvals/{doctor_approval['id']}/decision", json={"decision": "approved"}, headers=headers(patient)
    ).status_code == 403
    doctor_decision = client.post(
        f"/api/v1/agent/approvals/{doctor_approval['id']}/decision", json={"decision": "approved"}, headers=headers(doctor)
    )
    assert doctor_decision.status_code == 200
    assert doctor_decision.json["approval"]["resolved_by"] == user_id(app, "approval-doctor@example.com")


def test_proactive_alerts_are_owner_only_and_deduplicated(tmp_path):
    app, client = make_client(tmp_path)
    patient = api_token(client, "alerts-patient@example.com")
    owner = owner_token(client)
    with app.app_context():
        owner_row = get_db().execute("SELECT * FROM users WHERE role='admin'").fetchone()
        approval = create_approval(owner_row["id"], "old_action", "Old waiting action")
        old = (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat(timespec="seconds")
        get_db().execute("UPDATE agent_approvals SET created_at=? WHERE id=?", (old, approval["id"]))
        get_db().commit()
    assert client.post("/api/v1/admin/alerts/check", headers=headers(patient)).status_code == 403
    first = client.post("/api/v1/admin/alerts/check", headers=headers(owner))
    second = client.post("/api/v1/admin/alerts/check", headers=headers(owner))
    assert len(first.json["created_alerts"]) == 1
    assert second.json["created_alerts"] == []
    alert_id = first.json["created_alerts"][0]["id"]
    assert client.post(f"/api/v1/admin/alerts/{alert_id}/acknowledge", headers=headers(owner)).json["alert"]["status"] == "acknowledged"
    assert client.post(f"/api/v1/admin/alerts/{alert_id}/resolve", headers=headers(owner)).json["alert"]["status"] == "resolved"


def test_event_bus_redacts_secrets_and_is_idempotent(tmp_path):
    app, client = make_client(tmp_path)
    token = api_token(client, "event-redact@example.com")
    with app.app_context():
        actor = dict(get_db().execute("SELECT * FROM users WHERE email_normalized='event-redact@example.com'").fetchone())
        first = publish_event(
            "security.test.recorded", actor=actor, entity_type="security_test", payload={"password": "never-store", "safe": "ok"}, idempotency_key="security-test-1"
        )
        second = publish_event(
            "security.test.recorded", actor=actor, entity_type="security_test", payload={"password": "different"}, idempotency_key="security-test-1"
        )
        assert first["id"] == second["id"]
    events = client.get("/api/v1/events", headers=headers(token)).json["events"]
    event = next(item for item in events if item["id"] == first["id"])
    assert event["payload"] == {"password": "[redacted]", "safe": "ok"}


def test_notification_provider_records_real_in_app_and_truthful_external_delivery(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        patient_id = get_db().execute("SELECT id FROM users WHERE role='admin'").fetchone()["id"]
        in_app = deliver_notification(patient_id, "Test", "In-app delivered")
        external = deliver_notification(patient_id, "Test", "SMS requested", channel="sms")
        get_db().commit()
        assert in_app.status == "sent"
        assert external.status == "integration_required"
        assert get_db().execute("SELECT COUNT(*) c FROM notifications WHERE user_id=?", (patient_id,)).fetchone()["c"] == 1
        assert get_db().execute("SELECT status FROM notification_deliveries WHERE id=?", (external.delivery_id,)).fetchone()["status"] == "integration_required"


def test_capability_infrastructure_and_command_center_truthfulness(tmp_path):
    _app, client = make_client(tmp_path)
    owner = owner_token(client)
    capabilities = client.get("/api/v1/capabilities", headers=headers(owner)).json["capabilities"]
    assert capabilities["local_slm"]["status"] == "INTEGRATION_REQUIRED"
    assert capabilities["local_slm"]["description"] == "Local SLM integration ready — model not configured."
    assert capabilities["postgresql"]["status"] == "INTEGRATION_REQUIRED"
    assert capabilities["zendoc_proprietary_slm"]["status"] == "FUTURE"
    infrastructure = client.get("/api/v1/admin/infrastructure", headers=headers(owner)).json
    assert infrastructure["database"]["active"] == "sqlite"
    assert infrastructure["medical_record_storage"]["status"] == "working"
    assert infrastructure["realtime"]["status"] == "working"
    assert infrastructure["telehealth"]["status"] == "beta"

    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    page = client.get("/admin/agent-command-center")
    assert page.status_code == 200
    assert b"Owner Command Center 2.0" in page.data
    assert b"Run alert scan" in page.data
    assert b"Local SLM integration ready" in page.data


def test_m8_routes_require_authentication(tmp_path):
    _app, client = make_client(tmp_path)
    for path in (
        "/api/v1/capabilities",
        "/api/v1/agent/registry",
        "/api/v1/agent/tools",
        "/api/v1/agent/tasks",
        "/api/v1/agent/approvals",
        "/api/v1/events",
        "/api/v1/admin/model-router",
        "/api/v1/admin/infrastructure",
        "/api/v1/admin/approvals",
        "/api/v1/admin/alerts",
    ):
        assert client.get(path).status_code == 401
