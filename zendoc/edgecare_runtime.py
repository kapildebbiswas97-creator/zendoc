"""Competition-safe EdgeCare runtime profile and benchmark evidence handling.

This module deliberately separates three different truths:
1. a Snapdragon target is declared,
2. the ZENDOC local model runtime is actually reachable, and
3. hardware/NPU measurements have been recorded.

A configured target is never presented as measured hardware acceleration.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


EDGECARE_PROFILE_VERSION = "2026.1"
BENCHMARK_SCHEMA_VERSION = 1
SUPPORTED_EVIDENCE_SOURCES = {
    "local_snapdragon_device",
    "qualcomm_ai_hub_workbench",
    "qualcomm_device_cloud",
}


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_value(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or "").strip()


@dataclass(frozen=True)
class EdgeCareSettings:
    enabled: bool
    target_platform: str
    target_chipset: str
    runtime: str
    execution_provider: str
    language_model: str
    speech_model: str
    benchmark_file: str

    @classmethod
    def from_runtime(cls) -> "EdgeCareSettings":
        return cls(
            enabled=_env_bool("ZENDOC_EDGECARE_ENABLED", False),
            target_platform=_env_value(
                "ZENDOC_EDGECARE_TARGET_PLATFORM", "Snapdragon X Series Windows PC"
            ),
            target_chipset=_env_value(
                "ZENDOC_EDGECARE_TARGET_CHIPSET", "Snapdragon X Elite"
            ),
            runtime=_env_value(
                "ZENDOC_EDGECARE_RUNTIME", "ONNX Runtime / Qualcomm execution provider"
            ),
            execution_provider=_env_value(
                "ZENDOC_EDGECARE_EXECUTION_PROVIDER", "Qualcomm NPU target"
            ),
            language_model=_env_value(
                "ZENDOC_EDGECARE_LANGUAGE_MODEL", "llama_v3_2_3b_instruct_ssd"
            ),
            speech_model=_env_value(
                "ZENDOC_EDGECARE_SPEECH_MODEL", "whisper_small"
            ),
            benchmark_file=_env_value(
                "ZENDOC_EDGECARE_BENCHMARK_FILE", "instance/edgecare_benchmark.json"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "profile_version": EDGECARE_PROFILE_VERSION,
            "target_platform": self.target_platform,
            "target_chipset": self.target_chipset,
            "runtime": self.runtime,
            "execution_provider": self.execution_provider,
            "language_model": self.language_model,
            "speech_model": self.speech_model,
        }


def _bounded_number(value: Any, minimum: float, maximum: float) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < minimum or number > maximum:
        return None
    return round(number, 3)


def _bounded_int(value: Any, minimum: int, maximum: int) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number < minimum or number > maximum:
        return None
    return number


def normalize_benchmark_evidence(payload: Any) -> dict[str, Any] | None:
    """Validate the small, non-clinical benchmark evidence envelope.

    The evidence is intentionally metadata-only. Prompts, patient data, model
    responses, API keys, and hidden reasoning are never accepted here.
    """
    if not isinstance(payload, dict):
        return None
    if payload.get("schema_version") != BENCHMARK_SCHEMA_VERSION:
        return None

    source = str(payload.get("source") or "").strip().lower()
    if source not in SUPPORTED_EVIDENCE_SOURCES:
        return None

    runs = _bounded_int(payload.get("runs"), 1, 10_000)
    success_rate = _bounded_number(payload.get("success_rate"), 0.0, 1.0)
    median_latency_ms = _bounded_number(payload.get("median_latency_ms"), 0.0, 3_600_000.0)
    p95_latency_ms = _bounded_number(payload.get("p95_latency_ms"), 0.0, 3_600_000.0)
    if None in {runs, success_rate, median_latency_ms, p95_latency_ms}:
        return None

    def text(name: str, limit: int = 180) -> str:
        return str(payload.get(name) or "").strip()[:limit]

    measured_at = text("measured_at", 64)
    model = text("model")
    device = text("device")
    chipset = text("chipset")
    runtime = text("runtime")
    execution_provider = text("execution_provider")
    if not all((measured_at, model, device, chipset, runtime, execution_provider)):
        return None

    return {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "source": source,
        "measured_at": measured_at,
        "device": device,
        "chipset": chipset,
        "runtime": runtime,
        "execution_provider": execution_provider,
        "model": model,
        "runs": runs,
        "success_rate": success_rate,
        "median_latency_ms": median_latency_ms,
        "p95_latency_ms": p95_latency_ms,
        "npu_confirmed": bool(payload.get("npu_confirmed", False)),
        "evidence_reference": text("evidence_reference", 300) or None,
    }


def load_benchmark_evidence(base_dir: str | Path, settings: EdgeCareSettings | None = None) -> dict[str, Any] | None:
    settings = settings or EdgeCareSettings.from_runtime()
    root = Path(base_dir).resolve()
    candidate = Path(settings.benchmark_file)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        candidate = candidate.resolve()
        candidate.relative_to(root)
    except (OSError, ValueError):
        return None
    if not candidate.is_file() or candidate.stat().st_size > 64 * 1024:
        return None
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return normalize_benchmark_evidence(payload)


def build_edgecare_status(
    *,
    local_ai_status: dict[str, Any] | None = None,
    settings: EdgeCareSettings | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or EdgeCareSettings.from_runtime()
    local_ai_status = dict(local_ai_status or {})
    evidence = normalize_benchmark_evidence(evidence) if evidence else None

    local_state = str(local_ai_status.get("status") or "not_checked")
    local_ready = local_state == "ready"
    evidence_recorded = evidence is not None
    npu_recorded = bool(evidence and evidence.get("npu_confirmed"))

    if not settings.enabled:
        stage = "disabled"
    elif not local_ready:
        stage = "runtime_verification_required"
    elif not evidence_recorded:
        stage = "benchmark_required"
    elif not npu_recorded:
        stage = "benchmark_recorded_npu_unconfirmed"
    else:
        stage = "npu_measurement_recorded"

    return {
        "name": "ZENDOC EdgeCare AI",
        "profile": settings.to_dict(),
        "readiness_stage": stage,
        "local_ai": {
            "status": local_state,
            "provider": local_ai_status.get("provider"),
            "model": local_ai_status.get("model"),
            "latency_ms": local_ai_status.get("latency_ms"),
        },
        "benchmark": evidence or {
            "status": "not_recorded",
            "message": "No Snapdragon benchmark evidence has been recorded yet.",
        },
        "claims": {
            "snapdragon_target_declared": bool(settings.enabled),
            "local_runtime_ready": local_ready,
            "measurement_recorded": evidence_recorded,
            "npu_measurement_recorded": npu_recorded,
            "independently_verified_by_zendoc": False,
        },
        "safety_boundary": {
            "clinical_diagnosis": False,
            "autonomous_prescribing": False,
            "autonomous_emergency_dispatch": False,
            "model_output_executes_tools": False,
            "benchmark_contains_patient_data": False,
        },
        "truth_note": (
            "A target profile is not proof of Snapdragon/NPU execution. ZENDOC only marks measurements as "
            "recorded when explicit benchmark evidence is present; raw Qualcomm/device evidence should be "
            "kept with the competition submission for reviewer verification."
        ),
    }
