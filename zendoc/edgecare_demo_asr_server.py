"""Local CPU speech-to-text bridge for EdgeCare demo development.

This module intentionally does NOT claim Qualcomm/NPU execution. It provides the
same small OpenAI-compatible HTTP surface consumed by :mod:`zendoc.edgecare_asr`
so the full ZENDOC voice workflow can be exercised on an ordinary development
machine before a real Snapdragon/Qualcomm runtime is available.

The optional ``faster-whisper`` dependency is loaded only when the real demo
transcriber is constructed. Production ZENDOC and the normal test suite do not
need to install or download a speech model.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Protocol

from flask import Flask, jsonify, request


DEFAULT_MODEL_ID = "whisper_small"
DEFAULT_SOURCE_MODEL = "small"
DEFAULT_MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_TRANSCRIPT_CHARS = 5_000
_ALLOWED_SUFFIXES = {".webm", ".wav", ".mp3", ".mpeg", ".mp4", ".ogg", ".m4a"}
_ALLOWED_MIMETYPES = {
    "audio/webm",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp4",
    "audio/ogg",
    "audio/x-m4a",
    "video/webm",
    "application/octet-stream",
}


class DemoTranscriber(Protocol):
    def transcribe_file(self, path: str) -> str: ...


class FasterWhisperDemoTranscriber:
    """CPU/GPU development transcriber used only for local demonstration.

    This backend is a convenience path for proving ZENDOC's browser -> local
    ASR -> editable transcript flow. It is not Qualcomm benchmark evidence.
    """

    def __init__(
        self,
        source_model: str = DEFAULT_SOURCE_MODEL,
        *,
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover - depends on optional package
            raise RuntimeError(
                "faster-whisper is not installed. Install requirements-edgecare-demo.txt first."
            ) from exc

        self.source_model = source_model
        self.device = device
        self.compute_type = compute_type
        self._model = WhisperModel(source_model, device=device, compute_type=compute_type)

    def transcribe_file(self, path: str) -> str:
        segments, _info = self._model.transcribe(
            path,
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        text = " ".join(str(segment.text or "").strip() for segment in segments).strip()
        return text[:MAX_TRANSCRIPT_CHARS]


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _safe_suffix(filename: str | None) -> str:
    suffix = Path(str(filename or "voice.webm")).suffix.lower()
    return suffix if suffix in _ALLOWED_SUFFIXES else ".webm"


def create_edgecare_demo_asr_app(
    transcriber: DemoTranscriber | None = None,
    *,
    model_id: str | None = None,
    max_audio_bytes: int | None = None,
) -> Flask:
    """Create a loopback-only OpenAI-compatible ASR development service."""

    resolved_model_id = (model_id or os.environ.get("EDGECARE_DEMO_ASR_MODEL_ID") or DEFAULT_MODEL_ID).strip()
    if not resolved_model_id:
        raise ValueError("EdgeCare demo ASR model id must not be empty.")

    resolved_max = max_audio_bytes or _bounded_env_int(
        "EDGECARE_DEMO_ASR_MAX_AUDIO_BYTES",
        DEFAULT_MAX_AUDIO_BYTES,
        64 * 1024,
        10 * 1024 * 1024,
    )

    if transcriber is None:
        transcriber = FasterWhisperDemoTranscriber(
            (os.environ.get("EDGECARE_DEMO_ASR_SOURCE_MODEL") or DEFAULT_SOURCE_MODEL).strip(),
            device=(os.environ.get("EDGECARE_DEMO_ASR_DEVICE") or "cpu").strip(),
            compute_type=(os.environ.get("EDGECARE_DEMO_ASR_COMPUTE_TYPE") or "int8").strip(),
        )

    app = Flask("zendoc_edgecare_demo_asr")
    # Multipart framing adds a small amount of overhead; enforce the exact audio
    # byte limit separately after parsing the upload.
    app.config["MAX_CONTENT_LENGTH"] = resolved_max + (1024 * 1024)

    @app.after_request
    def _privacy_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.errorhandler(413)
    def _too_large(_error):
        return jsonify({"error": {"code": 413, "message": "Audio clip is too large."}}), 413

    @app.get("/healthz")
    def healthz():
        return jsonify(
            {
                "status": "ready",
                "model": resolved_model_id,
                "backend": "faster_whisper_local_demo",
                "npu_confirmed": False,
            }
        )

    @app.get("/v1/models")
    def list_models():
        return jsonify(
            {
                "object": "list",
                "data": [
                    {
                        "id": resolved_model_id,
                        "object": "model",
                        "owned_by": "zendoc-local-demo",
                    }
                ],
            }
        )

    @app.post("/v1/audio/transcriptions")
    def transcriptions():
        requested_model = str(request.form.get("model") or "").strip()
        if requested_model != resolved_model_id:
            return jsonify({"error": {"code": 404, "message": "Requested speech model is not available."}}), 404

        upload = request.files.get("file")
        if upload is None:
            return jsonify({"error": {"code": 400, "message": "Missing audio file."}}), 400

        mimetype = str(upload.mimetype or "application/octet-stream").split(";", 1)[0].strip().lower()
        if mimetype not in _ALLOWED_MIMETYPES:
            return jsonify({"error": {"code": 400, "message": "Unsupported audio type."}}), 400

        audio = upload.stream.read(resolved_max + 1)
        if not audio:
            return jsonify({"error": {"code": 400, "message": "Audio file is empty."}}), 400
        if len(audio) > resolved_max:
            return jsonify({"error": {"code": 413, "message": "Audio clip is too large."}}), 413

        temp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(prefix="zendoc-edgecare-", suffix=_safe_suffix(upload.filename), delete=False) as handle:
                handle.write(audio)
                temp_path = handle.name

            transcript = str(transcriber.transcribe_file(temp_path) or "").strip()[:MAX_TRANSCRIPT_CHARS]
            if not transcript:
                return jsonify({"error": {"code": 422, "message": "No speech could be transcribed."}}), 422

            # Do not echo filenames, raw audio metadata, or internal model traces.
            return jsonify(
                {
                    "text": transcript,
                    "model": resolved_model_id,
                    "backend": "faster_whisper_local_demo",
                    "npu_confirmed": False,
                }
            )
        except Exception:
            # Avoid leaking local paths, model internals, or transcript fragments.
            return jsonify({"error": {"code": 503, "message": "Local demo speech runtime failed."}}), 503
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    return app


def run_edgecare_demo_asr() -> None:
    """Start the development bridge on loopback only."""

    port = _bounded_env_int("EDGECARE_DEMO_ASR_PORT", 8001, 1024, 65535)
    app = create_edgecare_demo_asr_app()
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":  # pragma: no cover
    run_edgecare_demo_asr()
