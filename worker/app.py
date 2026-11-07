"""ZENDOC 2.0 — Independent Authenticated Python Worker Service

Provides Whisper Speech-to-Text (ASR) and Medical Document OCR endpoints.
Guarded by HMAC-SHA256 signature verification and timestamp replay protection.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict

from flask import Flask, jsonify, request

from .asr import transcribe_audio_buffer
from .auth import is_timestamp_fresh, verify_worker_hmac
from .ocr import extract_document_data

# Structured logger setup without logging sensitive PHI
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("zendoc.worker")

app = Flask(__name__)

START_TIME = time.time()
MAX_CONTENT_LENGTH = 25 * 1024 * 1024  # 25 MB
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH


def get_worker_secret() -> str:
    """Retrieves worker secret from environment, falling back to default test secret."""
    return os.environ.get("PYTHON_WORKER_SECRET", "dev-worker-secret-do-not-use-in-production")


def authenticate_worker_request() -> tuple[bool, str, int]:
    """Validates the incoming cryptographic authentication headers."""
    timestamp = request.headers.get("X-Zendoc-Timestamp")
    user_id = request.headers.get("X-Zendoc-User-Id")
    received_hmac = request.headers.get("X-Zendoc-Hmac")

    if not timestamp or not user_id or not received_hmac:
        logger.warning("Worker request rejected: Missing security headers.")
        return False, "Missing authentication headers (Timestamp, User-Id, Hmac).", 401

    # 1. Replay window check
    if not is_timestamp_fresh(timestamp, max_age_ms=60_000):
        logger.warning("Worker request rejected: Stale timestamp / replay detected.")
        return False, "Timestamp expired or out of bounds (max age 60s).", 401

    # 2. Cryptographic signature check
    secret = get_worker_secret()
    if not verify_worker_hmac(secret, timestamp, user_id, received_hmac):
        logger.warning("Worker request rejected: Invalid HMAC signature.")
        return False, "Invalid cryptographic HMAC signature.", 401

    return True, "", 200


@app.route("/api/health", methods=["GET"])
def health_check():
    """Unauthenticated health status probe for orchestrators and load balancers."""
    uptime_seconds = round(time.time() - START_TIME, 1)
    return jsonify({
        "status": "ok",
        "service": "zendoc-python-worker",
        "version": "2.0.0",
        "uptime_seconds": uptime_seconds,
        "capabilities": {
            "whisper_asr": True,
            "document_ocr": True,
            "structured_biomarker_extraction": True,
        },
    }), 200


@app.route("/api/asr/transcribe", methods=["POST"])
def asr_transcribe():
    """Authenticated endpoint: transcribes speech audio buffer."""
    is_valid, error_msg, status_code = authenticate_worker_request()
    if not is_valid:
        return jsonify({"error": error_msg, "success": False}), status_code

    content_type = request.headers.get("Content-Type", "audio/webm").split(";")[0].strip()
    data = request.get_data()

    if not data:
        return jsonify({"error": "Empty audio data received.", "success": False}), 400

    logger.info("Processing ASR transcription request (bytes: %d)", len(data))
    result = transcribe_audio_buffer(data, content_type)
    return jsonify(result), 200


@app.route("/api/ocr/extract", methods=["POST"])
def ocr_extract():
    """Authenticated endpoint: extracts text & clinical entities from document."""
    is_valid, error_msg, status_code = authenticate_worker_request()
    if not is_valid:
        return jsonify({"error": error_msg, "success": False}), status_code

    mime_type = request.headers.get("Content-Type", "application/pdf").split(";")[0].strip()
    data = request.get_data()

    if not data:
        return jsonify({"error": "Empty document data received.", "success": False}), 400

    logger.info("Processing document OCR request (bytes: %d, mime: %s)", len(data), mime_type)
    result = extract_document_data(data, mime_type)
    return jsonify(result), 200


@app.route("/api/jobs/<job_id>", methods=["GET"])
def get_job_status(job_id: str):
    """Job status poll endpoint for asynchronous workflows."""
    is_valid, error_msg, status_code = authenticate_worker_request()
    if not is_valid:
        return jsonify({"error": error_msg, "success": False}), status_code

    return jsonify({
        "job_id": job_id,
        "status": "COMPLETED",
        "timestamp": time.time(),
    }), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
