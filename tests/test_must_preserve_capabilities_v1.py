"""
ZENDOC Must-Preserve Capability Regression Test Suite v1.
Guarantees that no core route, blueprint, capability, safety gate, or data model
is deleted, disabled, shrunk, or silently regressed as ZENDOC expands.
"""
from __future__ import annotations

import json
import os
import pytest
from zendoc import create_app
from zendoc.capability_registry import get_capability_registry
from zendoc.database_reliability import REQUIRED_TABLES, REQUIRED_MIGRATIONS


MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "MUST_PRESERVE_CAPABILITY_MANIFEST.json")


def load_manifest() -> dict:
    assert os.path.exists(MANIFEST_PATH), f"Manifest file missing: {MANIFEST_PATH}"
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_manifest_structure_and_baseline():
    manifest = load_manifest()
    assert manifest["manifest_version"] == "2.0.0"
    assert manifest["verified_baseline"]["commit"] == "a2c97383fe95a394bcb64a1ec14e52ba7e262944"
    assert manifest["verified_baseline"]["branch"] == "main"
    assert len(manifest["integrated_prs"]) >= 2
    pr_numbers = {p["pr_number"] for p in manifest["integrated_prs"]}
    assert 116 in pr_numbers
    assert 123 in pr_numbers


def test_all_baseline_blueprints_registered():
    manifest = load_manifest()
    expected_blueprints = set(manifest["blueprints_inventory"])
    app = create_app()
    registered_blueprints = set(app.blueprints.keys())

    missing = expected_blueprints - registered_blueprints
    assert not missing, f"Missing blueprints that must be preserved: {missing}"
    assert len(registered_blueprints) >= 56


def test_database_schema_and_migrations_preserved():
    manifest = load_manifest()
    expected_tables = set(manifest["database_schema_inventory"]["tables"])
    expected_migrations = set(manifest["database_schema_inventory"]["migrations"])

    for req_table in REQUIRED_TABLES:
        assert req_table in expected_tables, f"Critical table {req_table} missing from schema manifest"

    for req_mig in REQUIRED_MIGRATIONS:
        assert req_mig in expected_migrations, f"Critical migration {req_mig} missing from migrations manifest"

    assert len(expected_tables) >= 157
    assert len(expected_migrations) >= 18


def test_truthful_status_model_invariants():
    manifest = load_manifest()
    allowed_states = set(manifest["truth_status_model"]["allowed_states"])
    capabilities = get_capability_registry()

    for key, cap in capabilities.items():
        assert cap["status"] in allowed_states, (
            f"Capability {key} has invalid status {cap['status']}; must be one of {allowed_states}"
        )

    # Invariant: autonomous prescribing MUST be FUTURE or DISABLED
    assert capabilities["autonomous_prescribing"]["status"] in {"FUTURE", "DISABLED"}
    assert "legally restricted" in capabilities["autonomous_prescribing"]["label"].lower()
    assert "legally valid doctor workflow" in capabilities["autonomous_prescribing"]["description"].lower()

    # Invariant: proprietary SLM must be FUTURE
    assert capabilities["zendoc_proprietary_slm"]["status"] == "FUTURE"
    assert "has not trained a proprietary" in capabilities["zendoc_proprietary_slm"]["description"].lower()


def test_critical_platform_layers_active():
    manifest = load_manifest()
    layers = manifest["platform_layers"]
    assert "patient_platform" in layers
    assert "health_memory_2" in layers
    assert "find_care_2" in layers
    assert "provider_os" in layers
    assert "care_os" in layers
    assert "agent_os" in layers
    assert "medication_pharmacy_os" in layers
    assert "interoperability_os" in layers
    assert "network_sites" in layers
    assert "automation_engine" in layers
