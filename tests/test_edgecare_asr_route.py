from io import BytesIO

from zendoc import create_app
from zendoc.edgecare_asr import ASRResult
from tests.test_milestone1 import csrf, register_web


class FakeASR:
    class Settings:
        max_audio_bytes = 1024

    settings = Settings()

    def __init__(self, result):
        self.result = result
        self.calls = []

    def transcribe(self, audio, *, filename, mimetype):
        self.calls.append({"audio": audio, "filename": filename, "mimetype": mimetype})
        return self.result


def make_client(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "edgecare-route.db"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "SECRET_KEY": "edgecare-route-test-secret",
            "ADMIN_EMAIL": "owner@zendoc.local",
            "ADMIN_PASSWORD": "OwnerPassword123!",
            "RATE_LIMIT_PER_MINUTE": 1000,
        }
    )
    return app, app.test_client()


def login_patient(client):
    register_web(client, "patient", "voice@example.com", name="Voice Patient")
    page = client.get("/login")
    token = csrf(page.data.decode())
    response = client.post(
        "/login",
        data={
            "csrf_token": token,
            "email": "voice@example.com",
            "password": "StrongPass123",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    with client.session_transaction() as session_state:
        return session_state["csrf_token"]


def test_edgecare_asr_route_requires_login(tmp_path):
    _app, client = make_client(tmp_path)
    response = client.post(
        "/edgecare/asr/transcribe",
        data={"audio": (BytesIO(b"voice"), "voice.webm")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert response.status_code in {302, 400}


def test_edgecare_asr_route_requires_csrf(tmp_path):
    _app, client = make_client(tmp_path)
    login_patient(client)
    response = client.post(
        "/edgecare/asr/transcribe",
        data={"audio": (BytesIO(b"voice"), "voice.webm")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400


def test_edgecare_asr_route_returns_local_transcript_without_auto_action(tmp_path, monkeypatch):
    _app, client = make_client(tmp_path)
    token = login_patient(client)
    fake = FakeASR(
        ASRResult(
            success=True,
            text="Help me find a cardiologist near Kolkata.",
            provider="local_openai_compatible_asr",
            model="whisper_small",
            latency_ms=42,
        )
    )
    monkeypatch.setattr("zendoc.edgecare_routes.get_edgecare_asr", lambda: fake)

    response = client.post(
        "/edgecare/asr/transcribe",
        data={
            "csrf_token": token,
            "audio": (BytesIO(b"fake-audio"), "voice.webm", "audio/webm"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert response.json["result"]["success"] is True
    assert response.json["result"]["provider"] == "local_openai_compatible_asr"
    assert response.json["result"]["text"] == "Help me find a cardiologist near Kolkata."
    assert len(fake.calls) == 1
    assert fake.calls[0]["audio"] == b"fake-audio"


def test_edgecare_asr_route_maps_runtime_failure_to_service_unavailable(tmp_path, monkeypatch):
    _app, client = make_client(tmp_path)
    token = login_patient(client)
    fake = FakeASR(
        ASRResult(
            success=False,
            text="",
            provider="local_openai_compatible_asr",
            model="whisper_small",
            latency_ms=5,
            error_category="provider_unavailable",
        )
    )
    monkeypatch.setattr("zendoc.edgecare_routes.get_edgecare_asr", lambda: fake)

    response = client.post(
        "/edgecare/asr/transcribe",
        data={
            "csrf_token": token,
            "audio": (BytesIO(b"fake-audio"), "voice.webm", "audio/webm"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 503
    assert response.json["result"]["success"] is False
    assert response.json["result"]["error_category"] == "provider_unavailable"


def test_edgecare_asr_route_rejects_oversized_audio_before_provider_call(tmp_path, monkeypatch):
    _app, client = make_client(tmp_path)
    token = login_patient(client)
    fake = FakeASR(
        ASRResult(True, "unused", "local_openai_compatible_asr", "whisper_small", 1)
    )
    monkeypatch.setattr("zendoc.edgecare_routes.get_edgecare_asr", lambda: fake)

    response = client.post(
        "/edgecare/asr/transcribe",
        data={
            "csrf_token": token,
            "audio": (BytesIO(b"x" * 1025), "voice.webm", "audio/webm"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 413
    assert fake.calls == []
