from io import BytesIO

from zendoc.edgecare_demo_asr_server import create_edgecare_demo_asr_app


class FakeTranscriber:
    def __init__(self, text="local transcript"):
        self.text = text
        self.paths = []

    def transcribe_file(self, path: str) -> str:
        self.paths.append(path)
        return self.text


def make_client(text="local transcript", max_audio_bytes=1024):
    transcriber = FakeTranscriber(text)
    app = create_edgecare_demo_asr_app(
        transcriber,
        model_id="whisper_small",
        max_audio_bytes=max_audio_bytes,
    )
    app.config["TESTING"] = True
    return app.test_client(), transcriber


def test_health_and_model_list_never_claim_npu():
    client, _ = make_client()

    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json["status"] == "ready"
    assert health.json["npu_confirmed"] is False

    models = client.get("/v1/models")
    assert models.status_code == 200
    assert models.json["data"][0]["id"] == "whisper_small"


def test_transcription_returns_editable_text_and_no_npu_claim():
    client, transcriber = make_client("hello from local speech")

    response = client.post(
        "/v1/audio/transcriptions",
        data={
            "model": "whisper_small",
            "file": (BytesIO(b"fake-audio"), "voice.webm", "audio/webm"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert response.json["text"] == "hello from local speech"
    assert response.json["npu_confirmed"] is False
    assert response.headers["Cache-Control"] == "no-store"
    assert len(transcriber.paths) == 1


def test_rejects_wrong_model():
    client, _ = make_client()
    response = client.post(
        "/v1/audio/transcriptions",
        data={
            "model": "wrong-model",
            "file": (BytesIO(b"fake-audio"), "voice.webm", "audio/webm"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 404


def test_rejects_missing_audio():
    client, _ = make_client()
    response = client.post(
        "/v1/audio/transcriptions",
        data={"model": "whisper_small"},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400


def test_rejects_unsupported_mimetype():
    client, _ = make_client()
    response = client.post(
        "/v1/audio/transcriptions",
        data={
            "model": "whisper_small",
            "file": (BytesIO(b"not-audio"), "voice.txt", "text/plain"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 400


def test_rejects_oversized_audio():
    client, _ = make_client(max_audio_bytes=8)
    response = client.post(
        "/v1/audio/transcriptions",
        data={
            "model": "whisper_small",
            "file": (BytesIO(b"0123456789"), "voice.webm", "audio/webm"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 413


def test_empty_transcript_is_not_reported_as_success():
    client, _ = make_client("")
    response = client.post(
        "/v1/audio/transcriptions",
        data={
            "model": "whisper_small",
            "file": (BytesIO(b"fake-audio"), "voice.webm", "audio/webm"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
