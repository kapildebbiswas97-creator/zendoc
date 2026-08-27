from zendoc.db import get_db
from zendoc.intelligence import ZendocIntelligence

from tests.test_milestone1 import api_token, make_client, register_web, login_web, csrf


def test_central_ai_structured_normal_health_question(tmp_path):
    _app, client = make_client(tmp_path)
    token = api_token(client, "central@example.com")
    response = client.post(
        "/api/v1/ai/message",
        json={"message": "I have fever"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json["intent"] == "symptoms"
    assert response.json["emergency"] is False
    assert response.json["follow_up_questions"]
    assert "confirmed diagnosis" in response.json["message"]


def test_central_ai_emergency_stops_normal_flow(tmp_path):
    _app, client = make_client(tmp_path)
    token = api_token(client, "emergency@example.com")
    response = client.post(
        "/api/v1/ai/message",
        json={"message": "I have chest pain and shortness of breath"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json["emergency"] is True
    assert response.json["intent"] == "emergency"
    assert response.json["follow_up_questions"] == []
    assert response.json["specialist"] == "Emergency medicine"


def test_non_emergency_symptom_is_not_emergency(tmp_path):
    _app, client = make_client(tmp_path)
    token = api_token(client, "routine@example.com")
    response = client.post(
        "/api/v1/ai/message",
        json={"message": "I have a mild rash"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json["intent"] == "symptoms"
    assert response.json["emergency"] is False


def test_conversation_follow_up_context(tmp_path):
    _app, client = make_client(tmp_path)
    token = api_token(client, "context@example.com")
    first = client.post(
        "/api/v1/ai/message",
        json={"message": "I have fever"},
        headers={"Authorization": f"Bearer {token}"},
    )
    conversation_id = first.json["conversation_id"]
    second = client.post(
        "/api/v1/ai/message",
        json={"message": "three days", "conversation_id": conversation_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second.status_code == 200
    assert second.json["intent"] == "symptoms"
    assert "timing helps" in second.json["message"]


def test_cross_user_conversation_isolation(tmp_path):
    _app, client = make_client(tmp_path)
    token_one = api_token(client, "one@example.com")
    token_two = api_token(client, "two@example.com")
    first = client.post(
        "/api/v1/ai/message",
        json={"message": "I have fever"},
        headers={"Authorization": f"Bearer {token_one}"},
    )
    stolen_conversation_id = first.json["conversation_id"]
    second = client.post(
        "/api/v1/ai/message",
        json={"message": "three days", "conversation_id": stolen_conversation_id},
        headers={"Authorization": f"Bearer {token_two}"},
    )
    assert second.status_code == 200
    assert second.json["conversation_id"] != stolen_conversation_id


def test_provider_unavailable_uses_deterministic_fallback(monkeypatch):
    monkeypatch.setenv("ZENDOC_AI_PROVIDER", "openai")
    result, _latency = ZendocIntelligence().respond("Help me with my health")
    assert result.provider == "local_fallback"
    assert result.success is False
    assert result.message


def test_ai_message_requires_auth(tmp_path):
    _app, client = make_client(tmp_path)
    response = client.post("/api/v1/ai/message", json={"message": "hello"})
    assert response.status_code == 401


def test_ai_message_rejects_empty_and_very_long_input(tmp_path):
    _app, client = make_client(tmp_path)
    token = api_token(client, "input@example.com")
    empty = client.post(
        "/api/v1/ai/message",
        json={"message": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert empty.status_code == 400
    long_response = client.post(
        "/api/v1/ai/message",
        json={"message": "x" * 5000},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert long_response.status_code == 200
    assert long_response.json["success"] is False


def test_web_central_ai_and_audit_metadata(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "patient", "web-ai@example.com", "AI User")
    login_web(client, "patient", "web-ai@example.com")
    page = client.get("/ai")
    token = csrf(page.data.decode())
    response = client.post(
        "/ai",
        data={"csrf_token": token, "feature": "zendoc_ai", "message": "I need an appointment"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Appointment" in response.data
    with app.app_context():
        row = get_db().execute("SELECT intent, provider, latency_ms FROM ai_interactions WHERE feature='zendoc_ai'").fetchone()
        assert row["intent"] == "appointment"
        assert row["provider"]
        assert row["latency_ms"] is not None


def test_existing_ai_doctor_endpoint_compatibility(tmp_path):
    _app, client = make_client(tmp_path)
    token = api_token(client, "compat@example.com")
    response = client.post(
        "/api/v1/ai/doctor",
        json={"symptoms": "fever and cough"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json["summary"] == "Possible respiratory infection"
