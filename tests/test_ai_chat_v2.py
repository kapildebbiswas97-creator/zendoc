from tests.test_milestone1 import csrf, login_web, make_client, register_web
from zendoc.db import get_db


def _post_chat(client, message, **extra):
    page = client.get("/ai?new=1")
    token = csrf(page.data.decode())
    payload = {"csrf_token": token, "message": message, **extra}
    return client.post("/ai", data=payload, follow_redirects=True)


def test_primary_ai_route_uses_conversation_first_ui(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "chat-v2@example.com", "Chat V2")
    login_web(client, "patient", "chat-v2@example.com")

    page = client.get("/ai?new=1")
    assert page.status_code == 200
    assert b"+ New chat" in page.data
    assert b"Previous chats" in page.data
    assert b"Doctor AI" in page.data
    assert b"Message ZENDOC AI" in page.data


def test_new_chat_creates_separate_conversations(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "patient", "separate-chat@example.com", "Separate Chat")
    login_web(client, "patient", "separate-chat@example.com")

    first = _post_chat(client, "I have a mild cough for two days")
    assert first.status_code == 200

    second_page = client.get("/ai?new=1")
    second_token = csrf(second_page.data.decode())
    second = client.post(
        "/ai",
        data={"csrf_token": second_token, "message": "Help me understand ZENDOC appointments"},
        follow_redirects=True,
    )
    assert second.status_code == 200

    with app.app_context():
        rows = get_db().execute(
            "SELECT id FROM ai_conversations WHERE user_id=(SELECT id FROM users WHERE email_normalized=?) ORDER BY id",
            ("separate-chat@example.com",),
        ).fetchall()
        assert len(rows) == 2


def test_doctor_ai_rejects_unrelated_general_task(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "doctor-scope@example.com", "Doctor Scope")
    login_web(client, "patient", "doctor-scope@example.com")

    page = client.get("/ai?mode=doctor&new=1")
    token = csrf(page.data.decode())
    response = client.post(
        "/ai",
        data={"csrf_token": token, "mode": "doctor", "message": "Write Python code to sort a list"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Doctor AI is reserved for health concerns" in response.data
    assert b"does not diagnose or prescribe" in response.data


def test_legacy_doctor_form_emergency_still_shows_emergency_state(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "doctor-emergency-v2@example.com", "Doctor Emergency")
    login_web(client, "patient", "doctor-emergency-v2@example.com")

    page = client.get("/ai?new=1")
    token = csrf(page.data.decode())
    response = client.post(
        "/ai",
        data={"csrf_token": token, "feature": "doctor", "symptoms": "chest pain and trouble breathing"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Emergency guidance" in response.data
    assert b"Seek urgent care now" in response.data
