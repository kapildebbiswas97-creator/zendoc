"""Unit tests for ZENDOC 2.0 Python Worker authentication & API endpoints."""
import os
import time
import pytest

from worker.auth import (
    generate_worker_hmac,
    verify_worker_hmac,
    is_timestamp_fresh,
)
from worker.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_worker_hmac_generation_and_verification():
    secret = "test-secret-key-123"
    timestamp = str(int(time.time() * 1000))
    user_id = "patient-uuid-001"

    token = generate_worker_hmac(secret, timestamp, user_id)
    assert len(token) == 64
    assert verify_worker_hmac(secret, timestamp, user_id, token) is True

    # Tampered signature must fail
    tampered = token[:-2] + "ff"
    assert verify_worker_hmac(secret, timestamp, user_id, tampered) is False

    # Different user must fail
    assert verify_worker_hmac(secret, timestamp, "other-user", token) is False


def test_timestamp_freshness_window():
    now_ms = int(time.time() * 1000)

    # Current timestamp: valid
    assert is_timestamp_fresh(str(now_ms)) is True

    # 30 seconds ago: valid
    assert is_timestamp_fresh(str(now_ms - 30_000)) is True

    # 70 seconds ago: expired (replay attack defense)
    assert is_timestamp_fresh(str(now_ms - 70_000)) is False

    # 10 seconds in the future: clock drift rejected
    assert is_timestamp_fresh(str(now_ms + 10_000)) is False


def test_worker_health_endpoint(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "ok"
    assert data["service"] == "zendoc-python-worker"
    assert data["capabilities"]["whisper_asr"] is True
    assert data["capabilities"]["document_ocr"] is True


def test_worker_asr_unauthorized_without_headers(client):
    res = client.post("/api/asr/transcribe", data=b"fake-audio")
    assert res.status_code == 401
    data = res.get_json()
    assert "Missing authentication headers" in data["error"]


def test_worker_asr_authorized_call(client):
    secret = os.environ.get("PYTHON_WORKER_SECRET", "dev-worker-secret-do-not-use-in-production")
    timestamp = str(int(time.time() * 1000))
    user_id = "patient-uuid-001"
    token = generate_worker_hmac(secret, timestamp, user_id)

    headers = {
        "X-Zendoc-Timestamp": timestamp,
        "X-Zendoc-User-Id": user_id,
        "X-Zendoc-Hmac": token,
        "Content-Type": "audio/webm",
    }
    audio_data = b"RIFF....WAVEfmt ....data...."
    res = client.post("/api/asr/transcribe", data=audio_data, headers=headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert "transcript" in data


def test_worker_ocr_authorized_call(client):
    secret = os.environ.get("PYTHON_WORKER_SECRET", "dev-worker-secret-do-not-use-in-production")
    timestamp = str(int(time.time() * 1000))
    user_id = "patient-uuid-001"
    token = generate_worker_hmac(secret, timestamp, user_id)

    headers = {
        "X-Zendoc-Timestamp": timestamp,
        "X-Zendoc-User-Id": user_id,
        "X-Zendoc-Hmac": token,
        "Content-Type": "application/pdf",
    }
    doc_data = b"%PDF-1.4 Clinical Blood Count Report..."
    res = client.post("/api/ocr/extract", data=doc_data, headers=headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert "extracted_text" in data
    assert "structured_fields" in data
