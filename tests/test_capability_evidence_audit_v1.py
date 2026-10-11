"""Regression coverage for ZENDOC's 73-item evidence-gated release inventory."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from zendoc.capability_registry import get_capability_registry
from zendoc.capability_evidence_audit import (
    BETA_ACCEPTANCE_EVIDENCE,
    EXTERNAL_EVIDENCE_REQUIREMENTS,
    FUTURE_BOUNDARIES,
    WORKING_REGRESSION_FILES,
    build_capability_evidence_audit,
)


MANIFEST = Path(__file__).resolve().parents[1] / "docs" / "MUST_PRESERVE_CAPABILITY_MANIFEST.json"


def _manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def test_73_capabilities_have_exactly_one_classification_and_truthful_summary():
    report = build_capability_evidence_audit(_manifest(), get_capability_registry())
    assert report["status"] == "INVENTORY_VALID", report["inventory_errors"]
    assert report["inventory_errors"] == []
    assert report["counts"] == {
        "total_registered_capabilities": 73,
        "working_capabilities": 50,
        "beta_capabilities": 7,
        "integration_required_capabilities": 14,
        "future_capabilities": 2,
    }
    assert len({item["key"] for item in report["capabilities"]}) == 73
    assert report["live_complete"] is False


def test_all_50_working_features_have_an_existing_regression_source_reference():
    report = build_capability_evidence_audit(_manifest(), get_capability_registry())
    working = {
        row["key"]: row
        for row in report["capabilities"]
        if row["baseline_status"] == "WORKING"
    }
    assert len(WORKING_REGRESSION_FILES) == 50
    assert set(working) == set(WORKING_REGRESSION_FILES)
    for key, row in working.items():
        source = WORKING_REGRESSION_FILES[key]
        assert (MANIFEST.parents[1] / source).is_file(), (key, source)
        assert row["regression_tests"] == [source]
        assert row["external_evidence"] == "SOFTWARE_TEST_REFERENCE_ONLY"
    assert report["live_complete"] is False


def test_all_14_external_integrations_need_evidence_not_a_config_flag():
    report = build_capability_evidence_audit(_manifest(), get_capability_registry())
    assert len(EXTERNAL_EVIDENCE_REQUIREMENTS) == 14
    external = {item["key"]: item for item in report["capabilities"] if item["baseline_status"] == "INTEGRATION_REQUIRED"}
    assert set(external) == set(EXTERNAL_EVIDENCE_REQUIREMENTS)
    for row in external.values():
        assert row["required_review"]
        assert row["external_evidence"] in {"PROBE_NOT_VERIFIED", "MANUAL_EVIDENCE_REQUIRED"}
        assert row["external_evidence"] != "RUNTIME_VERIFIED"


def test_all_7_beta_features_require_real_world_acceptance_and_two_future_capabilities_remain_restricted():
    report = build_capability_evidence_audit(_manifest(), get_capability_registry())
    all_caps = {item["key"]: item for item in report["capabilities"]}
    assert len(BETA_ACCEPTANCE_EVIDENCE) == 7
    assert len(FUTURE_BOUNDARIES) == 2
    for key in BETA_ACCEPTANCE_EVIDENCE:
        assert all_caps[key]["baseline_status"] == "BETA"
        assert all_caps[key]["external_evidence"] == "BETA_REAL_WORLD_VALIDATION_PENDING"
        assert all_caps[key]["required_review"]
    for key in FUTURE_BOUNDARIES:
        assert all_caps[key]["runtime_status"] in {"FUTURE", "DISABLED"}
        assert all_caps[key]["external_evidence"] == "FUTURE_RESTRICTED"
    assert all_caps["autonomous_prescribing"]["runtime_status"] in {"FUTURE", "DISABLED"}


def test_fresh_successful_payment_probe_is_partial_not_proof_of_settled_payment():
    now = _now()
    report = build_capability_evidence_audit(
        _manifest(),
        get_capability_registry(),
        now=now,
        latest_probes={
            "razorpay": {
                "status": "working",
                "evidence_code": "provider_account_handshake",
                "checked_at": now.isoformat(),
                "detail": {"configured": True},
            }
        },
    )
    payment = next(item for item in report["capabilities"] if item["key"] == "connected_payments_gateway")
    assert payment["external_evidence"] == "PROBE_PASSED_PARTIAL"
    assert report["live_complete"] is False


def test_database_probe_requires_postgresql_and_real_persistence_evidence():
    now = _now()
    for engine, verified, expected in (
        ("sqlite", True, "PROBE_PASSED_PARTIAL"),
        ("postgresql", False, "PROBE_PASSED_PARTIAL"),
        ("postgresql", True, "RUNTIME_VERIFIED"),
    ):
        report = build_capability_evidence_audit(
            _manifest(),
            get_capability_registry(),
            now=now,
            latest_probes={
                "database": {
                    "status": "working",
                    "evidence_code": "database_readiness_passed",
                    "checked_at": now.isoformat(),
                    "detail": {"engine": engine, "persistence_verified": verified},
                }
            },
        )
        db = next(item for item in report["capabilities"] if item["key"] == "postgresql")
        assert db["external_evidence"] == expected
        assert report["live_complete"] is False


def test_old_probe_unverified_and_registry_env_flags_cannot_claim_live_success():
    now = _now()
    registry = deepcopy(get_capability_registry())
    registry["cloud_llm"]["status"] = "WORKING"
    registry["connected_payments_gateway"]["status"] = "WORKING"
    report = build_capability_evidence_audit(
        _manifest(),
        registry,
        now=now,
        latest_probes={
            "ai_runtime": {
                "status": "working",
                "evidence_code": "some_old_pass",
                "checked_at": (now - timedelta(days=2)).isoformat(),
            },
            "razorpay": {
                "status": "failed",
                "evidence_code": "account_unavailable",
                "checked_at": now.isoformat(),
            },
        },
    )
    caps = {row["key"]: row for row in report["capabilities"]}
    assert caps["cloud_llm"]["external_evidence"] == "PROBE_NOT_VERIFIED"
    assert caps["connected_payments_gateway"]["external_evidence"] == "PROBE_NOT_VERIFIED"
    assert report["live_complete"] is False


def test_inventory_fails_closed_on_wrong_summary_duplicate_or_missing_registry_item():
    manifest = _manifest()
    registry = get_capability_registry()
    altered = deepcopy(manifest)
    altered["summary_metrics"]["total_registered_capabilities"] = 76
    report = build_capability_evidence_audit(altered, registry)
    assert report["status"] == "INVENTORY_INVALID"
    assert any("total_registered_capabilities" in error for error in report["inventory_errors"])

    duplicate = deepcopy(manifest)
    duplicate["feature_classification"]["merged_current_main_working"].append(
        deepcopy(duplicate["feature_classification"]["merged_current_main_working"][0])
    )
    assert any(
        "duplicate capability" in error
        for error in build_capability_evidence_audit(duplicate, registry)["inventory_errors"]
    )

    unlisted_registry = dict(registry)
    unlisted_registry["nonexistent_external_provider"] = {"status": "WORKING"}
    assert any(
        "not documented" in error
        for error in build_capability_evidence_audit(manifest, unlisted_registry)["inventory_errors"]
    )
