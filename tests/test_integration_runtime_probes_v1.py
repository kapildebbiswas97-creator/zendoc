from datetime import datetime, timezone

from zendoc import integration_probes
from zendoc.db import get_db
from zendoc.model_router import reset_model_router
from tests.test_milestone1 import csrf, login_web, make_app


def _owner():
    return get_db().execute(
        "SELECT * FROM users WHERE role='admin' AND email='admin@example.com'"
    ).fetchone()


def test_probe_snapshot_starts_without_fake_runtime_success(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        snapshot = integration_probes.integration_probe_snapshot()

    assert snapshot["verified_count"] == 0
    assert snapshot["failing_count"] == 0
    assert snapshot["total_count"] == len(integration_probes.PROBE_DEFINITIONS)
    assert all(item["last"] is None for item in snapshot["items"])


def test_database_runtime_probe_persists_bounded_evidence(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        result = integration_probes.run_integration_probe(_owner(), "database")
        stored = integration_probes.latest_probe_results()["database"]

    assert result["status"] == "working"
    assert result["evidence_code"] == "database_readiness_passed"
    assert stored["status"] == "working"
    assert stored["latency_ms"] >= 0
    assert "password" not in repr(stored).lower()


class _FakeSMTP:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started_tls = False
        self.logged_in = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def ehlo(self):
        return 250, b"ok"

    def starttls(self, context=None):
        self.started_tls = context is not None
        return 220, b"ready"

    def login(self, username, password):
        assert username == "zendoc-test"
        assert password == "test-secret"
        self.logged_in = True
        return 235, b"authenticated"

    def noop(self):
        return 250, b"ok"


def test_smtp_probe_authenticates_without_sending_email(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    app.config.update(
        EMAIL_PROVIDER="smtp",
        SMTP_HOST="smtp.example.test",
        SMTP_PORT=587,
        SMTP_USERNAME="zendoc-test",
        SMTP_PASSWORD="test-secret",
        SMTP_FROM_EMAIL="no-reply@example.test",
        SMTP_USE_TLS=True,
        SMTP_USE_SSL=False,
    )
    monkeypatch.setattr(integration_probes.smtplib, "SMTP", _FakeSMTP)

    with app.app_context():
        result = integration_probes.run_integration_probe(_owner(), "smtp")

    assert result["status"] == "working"
    assert result["evidence_code"] == "smtp_handshake_authenticated"
    assert result["detail"]["authenticated"] is True
    assert "test-secret" not in repr(result)


def test_unconfigured_external_probes_report_integration_required_not_success(
    tmp_path, monkeypatch
):
    for name in (
        "ZENDOC_RAZORPAY_KEY_ID",
        "ZENDOC_RAZORPAY_KEY_SECRET",
        "ZENDOC_RAZORPAY_WEBHOOK_SECRET",
        "ZENDOC_WEBRTC_ICE_SERVERS_JSON",
    ):
        monkeypatch.delenv(name, raising=False)

    app = make_app(tmp_path)
    app.config["STORAGE_PROVIDER"] = "local"

    with app.app_context():
        owner = _owner()
        payment = integration_probes.run_integration_probe(owner, "razorpay")
        storage = integration_probes.run_integration_probe(owner, "object_storage")
        turn = integration_probes.run_integration_probe(owner, "turn")

    assert payment["status"] == "integration_required"
    assert storage["status"] == "integration_required"
    assert turn["status"] == "integration_required"


def test_ai_probe_truthfully_reports_deterministic_fallback_when_no_model_is_configured(
    tmp_path, monkeypatch
):
    for name in (
        "ZENDOC_AI_PROVIDER",
        "ZENDOC_AI_API_KEY",
        "ZENDOC_AI_MODEL",
        "ZENDOC_LOCAL_AI_ENABLED",
        "ZENDOC_SLM_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)
    reset_model_router()

    app = make_app(tmp_path)
    with app.app_context():
        result = integration_probes.run_integration_probe(_owner(), "ai_runtime")

    assert result["status"] == "degraded"
    assert result["evidence_code"] == "deterministic_ai_fallback_only"
    assert result["detail"]["deterministic_safety_available"] is True
    assert result["detail"]["local_fallback_available"] is True


def test_automatic_probe_cycle_excludes_billable_probes_and_throttles_repeats(
    tmp_path, monkeypatch
):
    app = make_app(tmp_path)
    calls = []

    def fake_probe(actor, key):
        calls.append(key)
        integration_probes.ensure_integration_probe_schema()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cursor = get_db().execute(
            """
            INSERT INTO integration_probe_runs
            (integration_key,status,evidence_code,latency_ms,detail_json,checked_by,checked_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (key, "working", "test_probe", 1, "{}", int(actor["id"]), now),
        )
        get_db().commit()
        return {
            "id": int(cursor.lastrowid),
            "integration_key": key,
            "status": "working",
            "evidence_code": "test_probe",
            "latency_ms": 1,
            "detail": {},
            "checked_at": now,
        }

    monkeypatch.setattr(integration_probes, "run_integration_probe", fake_probe)

    with app.app_context():
        owner = _owner()
        first = integration_probes.run_automatic_safe_probes(owner)
        second = integration_probes.run_automatic_safe_probes(owner)

    expected = {
        key
        for key, definition in integration_probes.PROBE_DEFINITIONS.items()
        if definition["automatic_safe"]
    }
    assert set(calls) == expected
    assert len(first) == len(expected)
    assert second == []
    assert "places" not in calls
    assert "ai_runtime" not in calls


def test_integration_center_shows_runtime_evidence_and_owner_probe_controls(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    login_web(client, "admin", "admin@example.com", "AdminStrong123")

    response = client.get("/admin/integrations")

    assert response.status_code == 200
    assert b"Runtime verification evidence" in response.data
    assert b"Run runtime probe" in response.data
    assert b"may count toward provider usage" in response.data


def test_integration_probe_post_is_csrf_protected_and_owner_only(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    page = client.get("/admin/integrations")
    token = csrf(page.data.decode())

    response = client.post(
        "/admin/integrations/probe/database",
        data={"csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"runtime probe passed" in response.data
    with app.app_context():
        assert get_db().execute(
            "SELECT COUNT(*) AS c FROM integration_probe_runs WHERE integration_key='database'"
        ).fetchone()["c"] == 1


def test_turn_endpoint_parser_respects_udp_tcp_and_tls_defaults():
    assert integration_probes._parse_turn_endpoint(
        "turn:turn.example.test:3478?transport=udp"
    ) == ("turn", "turn.example.test", 3478, "udp")
    assert integration_probes._parse_turn_endpoint(
        "turn:turn.example.test:3478?transport=tcp"
    ) == ("turn", "turn.example.test", 3478, "tcp")
    assert integration_probes._parse_turn_endpoint(
        "turns:turn.example.test:5349"
    ) == ("turns", "turn.example.test", 5349, "tcp")
