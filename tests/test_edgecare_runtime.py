from zendoc.edgecare_runtime import (
    EdgeCareSettings,
    build_edgecare_status,
    normalize_benchmark_evidence,
)


def _settings(enabled=True):
    return EdgeCareSettings(
        enabled=enabled,
        target_platform="Snapdragon X Series Windows PC",
        target_chipset="Snapdragon X Elite",
        runtime="ONNX Runtime / Qualcomm execution provider",
        execution_provider="Qualcomm NPU target",
        language_model="llama_v3_2_3b_instruct_ssd",
        speech_model="whisper_small",
        benchmark_file="instance/edgecare_benchmark.json",
    )


def _evidence(npu_confirmed=False):
    return {
        "schema_version": 1,
        "source": "qualcomm_ai_hub_workbench",
        "measured_at": "2026-09-15T10:00:00+05:30",
        "device": "Snapdragon X Elite CRD",
        "chipset": "Snapdragon X Elite",
        "runtime": "Qualcomm AI Runtime",
        "execution_provider": "HTP/NPU",
        "model": "llama_v3_2_3b_instruct_ssd",
        "runs": 10,
        "success_rate": 1.0,
        "median_latency_ms": 100.0,
        "p95_latency_ms": 150.0,
        "npu_confirmed": npu_confirmed,
        "evidence_reference": "test-fixture-only",
    }


def test_declared_snapdragon_target_is_not_counted_as_measurement():
    status = build_edgecare_status(
        local_ai_status={"status": "ready", "provider": "local_openai_compatible"},
        settings=_settings(),
        evidence=None,
    )

    assert status["readiness_stage"] == "benchmark_required"
    assert status["claims"]["snapdragon_target_declared"] is True
    assert status["claims"]["local_runtime_ready"] is True
    assert status["claims"]["measurement_recorded"] is False
    assert status["claims"]["npu_measurement_recorded"] is False


def test_runtime_must_be_ready_before_edgecare_is_ready_for_benchmark():
    status = build_edgecare_status(
        local_ai_status={"status": "model_missing"},
        settings=_settings(),
        evidence=None,
    )

    assert status["readiness_stage"] == "runtime_verification_required"
    assert status["claims"]["local_runtime_ready"] is False


def test_benchmark_can_be_recorded_without_claiming_npu_execution():
    status = build_edgecare_status(
        local_ai_status={"status": "ready"},
        settings=_settings(),
        evidence=_evidence(npu_confirmed=False),
    )

    assert status["readiness_stage"] == "benchmark_recorded_npu_unconfirmed"
    assert status["claims"]["measurement_recorded"] is True
    assert status["claims"]["npu_measurement_recorded"] is False


def test_confirmed_npu_evidence_reaches_measured_stage():
    status = build_edgecare_status(
        local_ai_status={"status": "ready"},
        settings=_settings(),
        evidence=_evidence(npu_confirmed=True),
    )

    assert status["readiness_stage"] == "npu_measurement_recorded"
    assert status["claims"]["npu_measurement_recorded"] is True
    assert status["claims"]["independently_verified_by_zendoc"] is False


def test_benchmark_rejects_unknown_evidence_source():
    evidence = _evidence(npu_confirmed=True)
    evidence["source"] = "my_laptop_guess"

    assert normalize_benchmark_evidence(evidence) is None


def test_benchmark_rejects_impossible_metrics():
    evidence = _evidence()
    evidence["success_rate"] = 1.5

    assert normalize_benchmark_evidence(evidence) is None


def test_disabled_profile_never_claims_snapdragon_target():
    status = build_edgecare_status(
        local_ai_status={"status": "ready"},
        settings=_settings(enabled=False),
        evidence=_evidence(npu_confirmed=True),
    )

    assert status["readiness_stage"] == "disabled"
    assert status["claims"]["snapdragon_target_declared"] is False
