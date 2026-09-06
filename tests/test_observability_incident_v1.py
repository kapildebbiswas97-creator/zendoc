from __future__ import annotations

from datetime import datetime, timedelta, timezone

from zendoc.agent_alerts import run_proactive_alert_check
from zendoc.db import get_db, now_iso
from zendoc.observability import (
    incident_summary,
    prune_observability,
    request_metrics,
)
from tests.test_milestone1 import api_token, login_web, make_app


def test_request_id_is_returned_and_stored_without_query_string(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    response = client.get(
        "/api/v1/health?symptoms=chest+pain&token=secret-value",
        headers={"X-Request-ID": "trace-test-123"},
    )
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "trace-test-123"

    with app.app_context():
        row = get_db().execute(
            """
            SELECT correlation_id,route_pattern,method,status_code
            FROM request_observations
            WHERE correlation_id='trace-test-123'
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        assert row is not None
        assert row["route_pattern"] == "/api/v1/health"
        assert "symptoms" not in row["route_pattern"]
        assert "secret-value" not in row["route_pattern"]
        assert row["method"] == "GET"
        assert row["status_code"] == 200


def test_bearer_api_actor_is_attributed_without_token_storage(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    token = api_token(client, "observed-api@example.com")

    response = client.get(
        "/api/v1/dashboard",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Request-ID": "bearer-trace-1",
        },
    )
    assert response.status_code == 200

    with app.app_context():
        row = get_db().execute(
            """
            SELECT actor_id,actor_role,route_pattern
            FROM request_observations
            WHERE correlation_id='bearer-trace-1'
            """
        ).fetchone()
        assert row["actor_id"] is not None
        assert row["actor_role"] == "patient"
        assert row["route_pattern"] == "/api/v1/dashboard"

        text_rows = get_db().execute(
            """
            SELECT correlation_id,route_pattern,error_class
            FROM request_observations
            WHERE correlation_id='bearer-trace-1'
            """
        ).fetchall()
        serialized = str([dict(item) for item in text_rows])
        assert token not in serialized


def test_request_metrics_are_aggregate_only(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    client.get("/api/v1/health")
    client.get("/api/v1/health")
    client.get("/missing-observability-test")

    with app.app_context():
        metrics = request_metrics(60)
        assert metrics["total"] >= 3
        assert "slow_routes" in metrics
        assert "error_routes" in metrics
        for route in metrics["slow_routes"]:
            assert "query" not in route
            assert "body" not in route


def test_platform_event_inherits_request_correlation_id(tmp_path):
    app = make_app(tmp_path)

    @app.get("/observability-event-test")
    def observability_event_test():
        from zendoc.event_bus import publish_event

        event = publish_event(
            "ops.trace.test",
            entity_type="test",
            status="info",
            payload={"status": "ok"},
        )
        return {"event_id": event["id"]}

    client = app.test_client()
    response = client.get(
        "/observability-event-test",
        headers={"X-Request-ID": "event-trace-123"},
    )
    assert response.status_code == 200

    with app.app_context():
        row = get_db().execute(
            "SELECT correlation_id FROM platform_events WHERE id=?",
            (response.get_json()["event_id"],),
        ).fetchone()
        assert row["correlation_id"] == "event-trace-123"


def test_observability_owner_endpoint_is_protected(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    denied = client.get("/owner/observability", follow_redirects=False)
    assert denied.status_code in {302, 401, 403}

    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    allowed = client.get("/owner/observability")
    assert allowed.status_code == 200
    payload = allowed.get_json()
    assert "incident" in payload
    assert "requests_60m" in payload
    assert "emergency_60m" in payload


def test_incident_summary_escalates_on_server_errors(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        now = now_iso()
        for index in range(10):
            db.execute(
                """
                INSERT INTO request_observations
                (correlation_id,method,route_pattern,status_code,duration_ms,error_class,created_at)
                VALUES (?, 'GET', '/api/v1/test-failure', 500, 10, 'server_error', ?)
                """,
                (f"error-{index}", now),
            )
        db.commit()

        summary = incident_summary(60)
        assert summary["status"] == "incident"
        assert summary["requests"]["server_errors"] >= 10


def test_emergency_failure_creates_critical_operational_alert(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO platform_events
            (action,entity_type,status,event_type,payload_json,correlation_id,created_at)
            VALUES ('emergency_failure','agent_task','failed','safety.emergency.failed','{}','emergency-test',?)
            """,
            (now_iso(),),
        )
        db.commit()

        run_proactive_alert_check()
        alert = db.execute(
            """
            SELECT severity,category,title
            FROM agent_alerts
            WHERE category='emergency' AND status='active'
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        assert alert is not None
        assert alert["severity"] == "critical"
        assert alert["title"] == "Emergency Flow Failure Detected"


def test_observability_retention_prunes_only_old_metadata(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        old = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat(timespec="seconds")
        recent = now_iso()
        db.execute(
            """
            INSERT INTO request_observations
            (correlation_id,method,route_pattern,status_code,duration_ms,created_at)
            VALUES ('old-trace','GET','/old',200,1,?)
            """,
            (old,),
        )
        db.execute(
            """
            INSERT INTO request_observations
            (correlation_id,method,route_pattern,status_code,duration_ms,created_at)
            VALUES ('recent-trace','GET','/recent',200,1,?)
            """,
            (recent,),
        )
        db.commit()

        result = prune_observability(30)
        assert result["request_observations_deleted"] >= 1
        assert db.execute(
            "SELECT 1 FROM request_observations WHERE correlation_id='old-trace'"
        ).fetchone() is None
        assert db.execute(
            "SELECT 1 FROM request_observations WHERE correlation_id='recent-trace'"
        ).fetchone() is not None


def test_runbooks_do_not_claim_external_integrations_are_live(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    login_web(client, "admin", "admin@example.com", "AdminStrong123")

    response = client.get("/owner/incident-runbooks")
    assert response.status_code == 200
    runbooks = response.get_json()["runbooks"]
    provider = runbooks["provider_integration_outage"]
    text = str(provider).lower()
    assert "never claim" in text
    assert "ambulance" in text
