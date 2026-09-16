"""Local-only speech-to-text adapter for the ZENDOC EdgeCare competition layer.

The adapter is deliberately narrow:
- audio is sent only to a configured local/private endpoint allowed by the
  existing ZENDOC local-provider URL policy;
- no transcript is persisted here;
- no model output can execute tools or healthcare actions;
- configured Snapdragon targets are not treated as proof of NPU execution.
"""
from __future__ import annotations

import json
import os
import secrets
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .local_ai_provider import validate_local_provider_url


SUPPORTED_AUDIO_MIMETYPES = {
    "audio/webm",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp4",
    "audio/ogg",
    "video/webm",  # MediaRecorder may label audio-only WebM this way.
}
DEFAULT_MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_TRANSCRIPT_CHARS = 5_000
MAX_RESPONSE_BYTES = 256 * 1024


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


@dataclass(frozen=True)
class EdgeCareASRSettings:
    enabled: bool
    provider: str
    base_url: str
    model: str
    timeout: int
    max_audio_bytes: int
    allow_private_network: bool = False

    @classmethod
    def from_runtime(cls) -> "EdgeCareASRSettings":
        return cls(
            enabled=_env_bool("ZENDOC_EDGECARE_ASR_ENABLED", False),
            provider=str(os.environ.get("ZENDOC_EDGECARE_ASR_PROVIDER", "openai_compatible") or "").strip().lower(),
            base_url=str(os.environ.get("ZENDOC_EDGECARE_ASR_BASE_URL", "http://127.0.0.1:8001") or "").strip().rstrip("/"),
            model=str(os.environ.get("ZENDOC_EDGECARE_SPEECH_MODEL", "whisper_small") or "").strip(),
            timeout=_env_int("ZENDOC_EDGECARE_ASR_TIMEOUT", 30, 1, 120),
            max_audio_bytes=_env_int(
                "ZENDOC_EDGECARE_ASR_MAX_AUDIO_BYTES",
                DEFAULT_MAX_AUDIO_BYTES,
                64 * 1024,
                10 * 1024 * 1024,
            ),
            allow_private_network=_env_bool("ZENDOC_EDGECARE_ASR_ALLOW_PRIVATE_NETWORK", False),
        )

    def validated_base_url(self) -> str:
        return validate_local_provider_url(self.base_url, self.allow_private_network)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "timeout": self.timeout,
            "max_audio_bytes": self.max_audio_bytes,
        }


@dataclass
class ASRResult:
    success: bool
    text: str
    provider: str
    model: str
    latency_ms: int
    error_category: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "text": self.text,
            "provider": self.provider,
            "model": self.model,
            "latency_ms": max(0, int(self.latency_ms or 0)),
            "error_category": self.error_category,
        }


class EdgeCareASR:
    """OpenAI-compatible local ASR adapter with strict input bounds."""

    def __init__(self, settings: EdgeCareASRSettings | None = None):
        self.settings = settings or EdgeCareASRSettings.from_runtime()

    def configuration_status(self) -> dict[str, Any]:
        settings = self.settings
        if not settings.enabled:
            return {
                "status": "disabled",
                "provider": settings.provider or None,
                "model": settings.model or None,
                "message": "EdgeCare local speech recognition is disabled.",
            }
        if settings.provider != "openai_compatible":
            return {
                "status": "configuration_error",
                "provider": settings.provider or None,
                "model": settings.model or None,
                "message": "Unsupported EdgeCare ASR provider.",
                "error_category": "invalid_provider",
            }
        if not settings.model:
            return {
                "status": "integration_required",
                "provider": settings.provider,
                "model": None,
                "message": "EdgeCare ASR model is not configured.",
                "error_category": "model_not_configured",
            }
        try:
            settings.validated_base_url()
        except ValueError:
            return {
                "status": "configuration_error",
                "provider": settings.provider,
                "model": settings.model,
                "message": "EdgeCare ASR URL was rejected by the local/private endpoint policy.",
                "error_category": "unsafe_provider_url",
            }
        return {
            "status": "configured",
            "provider": settings.provider,
            "model": settings.model,
            "message": "EdgeCare local ASR is configured; runtime readiness has not been checked.",
        }

    def status(self, check_health: bool = False) -> dict[str, Any]:
        configured = self.configuration_status()
        if configured["status"] != "configured" or not check_health:
            return configured

        started = time.perf_counter()
        try:
            data = self._request_json(f"{self.settings.validated_base_url()}/v1/models", timeout=min(self.settings.timeout, 5))
            models = data.get("data")
            if not isinstance(models, list):
                raise ValueError("malformed_response")
            installed = {str(item.get("id") or "").strip() for item in models if isinstance(item, dict)}
            if self.settings.model not in installed:
                return {
                    "status": "model_missing",
                    "provider": self.settings.provider,
                    "model": self.settings.model,
                    "latency_ms": self._elapsed(started),
                    "message": "Local ASR server is online, but the configured speech model is missing.",
                    "error_category": "model_missing",
                }
            return {
                "status": "ready",
                "provider": self.settings.provider,
                "model": self.settings.model,
                "latency_ms": self._elapsed(started),
                "message": "Local ASR server and configured speech model are ready.",
            }
        except Exception as exc:
            category = self._classify(exc)
            return {
                "status": "unavailable" if category != "malformed_response" else "malformed_response",
                "provider": self.settings.provider,
                "model": self.settings.model,
                "latency_ms": self._elapsed(started),
                "message": "Local ASR runtime is unavailable or returned an invalid health response.",
                "error_category": category,
            }

    def transcribe(self, audio: bytes, *, filename: str = "voice.webm", mimetype: str = "audio/webm") -> ASRResult:
        started = time.perf_counter()
        status = self.configuration_status()
        if status["status"] != "configured":
            return self._failure(started, status.get("error_category") or status["status"])

        content_type = str(mimetype or "").split(";", 1)[0].strip().lower()
        if content_type not in SUPPORTED_AUDIO_MIMETYPES:
            return self._failure(started, "unsupported_audio_type")
        if not audio:
            return self._failure(started, "empty_audio")
        if len(audio) > self.settings.max_audio_bytes:
            return self._failure(started, "audio_too_large")

        safe_filename = "voice.webm"
        suffix = str(filename or "").rsplit(".", 1)
        if len(suffix) == 2 and suffix[1].lower() in {"webm", "wav", "mp3", "mpeg", "mp4", "ogg"}:
            safe_filename = f"voice.{suffix[1].lower()}"

        try:
            boundary = f"zendoc-{secrets.token_hex(16)}"
            body = self._multipart_body(boundary, audio, safe_filename, content_type)
            request = urllib.request.Request(
                f"{self.settings.validated_base_url()}/v1/audio/transcriptions",
                data=body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Accept": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=self.settings.timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError("response_too_large")
            data = json.loads(raw.decode("utf-8"))
            text = str(data.get("text") or "").strip() if isinstance(data, dict) else ""
            if not text:
                raise ValueError("malformed_response")
            return ASRResult(
                True,
                text[:MAX_TRANSCRIPT_CHARS],
                "local_openai_compatible_asr",
                self.settings.model,
                self._elapsed(started),
            )
        except Exception as exc:
            return self._failure(started, self._classify(exc))

    def _multipart_body(self, boundary: str, audio: bytes, filename: str, mimetype: str) -> bytes:
        line = b"\r\n"
        chunks = [
            f"--{boundary}".encode(), line,
            b'Content-Disposition: form-data; name="model"', line, line,
            self.settings.model.encode("utf-8"), line,
            f"--{boundary}".encode(), line,
            f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode("utf-8"), line,
            f"Content-Type: {mimetype}".encode("utf-8"), line, line,
            audio, line,
            f"--{boundary}--".encode(), line,
        ]
        return b"".join(chunks)

    @staticmethod
    def _elapsed(started: float) -> int:
        return max(0, int((time.perf_counter() - started) * 1000))

    def _failure(self, started: float, category: str) -> ASRResult:
        return ASRResult(
            False,
            "",
            "local_openai_compatible_asr",
            self.settings.model or "not_configured",
            self._elapsed(started),
            category,
        )

    @staticmethod
    def _classify(exc: Exception) -> str:
        if isinstance(exc, urllib.error.HTTPError):
            return "model_missing" if exc.code == 404 else "provider_error"
        if isinstance(exc, (urllib.error.URLError, TimeoutError)):
            return "provider_unavailable"
        value = str(exc)
        if value in {"malformed_response", "response_too_large"}:
            return value
        if isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError)):
            return "malformed_response"
        return "provider_error"

    @staticmethod
    def _request_json(url: str, timeout: int) -> dict[str, Any]:
        request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("response_too_large")
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("malformed_response")
        return data


def get_edgecare_asr(settings: EdgeCareASRSettings | None = None) -> EdgeCareASR:
    return EdgeCareASR(settings)
