import pytest

from zendoc.interoperability_gateway import (
    BLOCKED_BY_AUTHORIZATION,
    EXTERNAL_CREDENTIAL_REQUIRED,
    PARTNER_CONTRACT_REQUIRED,
    SOFTWARE_COMPLETE_LIVE_VERIFICATION,
    VERIFIED_WORKING,
    build_exchange_plan,
    interoperability_manifest,
    interoperability_readiness_snapshot,
)
from zendoc.personal_agents import route_personal_agent
from tests.test_milestone1 import login_web, make_client


def _clear_interop_env(monkeypatch):
    snapshot = interoperability_readiness_snapshot()
    names = set()
    for adapter in snapshot["adapters"]:
        names.update(adapter["required_config"])
        names.update(adapter["partner_config"])
        names.add(adapter["authorization_flag"])
        names.add(adapter["verification_flag"])
        names.add(adapter["failed_verification_flag"])
    for name in names:
        monkeypatch.delenv(name, raising=False)


def test_interoperability_manifest_is_provider_neutral_and_truth_bounded(monkeypatch):
    _clear_interop_env(monkeypatch)
    manifest = interoperability_manifest()

    assert manifest["provider_neutral"] is True
    assert manifest["network_neutral"] is True
    assert manifest["fhir_versions"] == ["R4", "R5"]
    assert {
        "Patient",
        "Practitioner",
        "Organization",
        "Appointment",
        "CarePlan",
        "Observation",
        "DiagnosticReport",
        "MedicationRequest",
        "Consent",
        "Provenance",
        "AuditEvent",
        "Coverage",
        "Claim",
        "Device",
    } <= set(manifest["resource_types"])
    assert manifest["live_exchange_enabled"] is False

    states = {item["key"]: item["truth_state"] for item in manifest["adapters"]}
    assert states["generic_fhir"] == EXTERNAL_CREDENTIAL_REQUIRED
    assert states["tefca_network"] == PARTNER_CONTRACT_REQUIRED
    assert states["ehds_myhealth_eu"] == PARTNER_CONTRACT_REQUIRED
    assert all(item["external_action_executed"] is False for item in manifest["adapters"])


def test_adapter_needs_authorization_and_live_verification_after_configuration(monkeypatch):
    _clear_interop_env(monkeypatch)
    monkeypatch.setenv("ZENDOC_FHIR_BASE_URL", "https://fhir.example.test")
    monkeypatch.setenv("ZENDOC_FHIR_CLIENT_ID", "client-id")

    row = next(
        item for item in interoperability_readiness_snapshot()["adapters"]
        if item["key"] == "generic_fhir"
    )
    assert row["truth_state"] == BLOCKED_BY_AUTHORIZATION

    monkeypatch.setenv("ZENDOC_FHIR_AUTHORIZED", "true")
    row = next(
        item for item in interoperability_readiness_snapshot()["adapters"]
        if item["key"] == "generic_fhir"
    )
    assert row["truth_state"] == SOFTWARE_COMPLETE_LIVE_VERIFICATION

    monkeypatch.setenv("ZENDOC_FHIR_VERIFIED", "true")
    row = next(
        item for item in interoperability_readiness_snapshot()["adapters"]
        if item["key"] == "generic_fhir"
    )
    assert row["truth_state"] == VERIFIED_WORKING


def test_exchange_plan_never_executes_or_expands_permissions(monkeypatch):
    _clear_interop_env(monkeypatch)
    actor = {"id": 42, "role": "patient", "active": 1}
    plan = build_exchange_plan(
        actor,
        adapter_key="generic_fhir",
        resource_type="DiagnosticReport",
        direction="export",
    )
    assert plan["patient_id"] == 42
    assert plan["minimum_necessary_scope"] is True
    assert plan["provenance_required"] is True
    assert plan["audit_required"] is True
    assert plan["consent_or_legal_authority_required"] is True
    assert plan["human_confirmation_required"] is True
    assert plan["permission_expansion"] is False
    assert plan["execution_mode"] == "PLAN_ONLY"
    assert plan["external_action_executed"] is False
    assert plan["live_exchange_permitted_by_this_plan"] is False


def test_patient_cannot_plan_exchange_for_another_patient(monkeypatch):
    _clear_interop_env(monkeypatch)
    with pytest.raises(PermissionError):
        build_exchange_plan(
            {"id": 7, "role": "patient", "active": 1},
            adapter_key="generic_fhir",
            resource_type="Observation",
            direction="import",
            patient_id=8,
        )


def test_personal_agent_routes_interoperability_to_specialist():
    route = route_personal_agent(
        {"id": 42, "role": "patient", "active": 1},
        "health_interoperability",
    )
    assert route["delegated_agent"] == "InteroperabilityAgent"
    assert "get_interoperability_capabilities" in route["candidate_tools"]
    assert "prepare_interoperability_exchange_plan" in route["candidate_tools"]
    assert route["permission_expansion"] is False


def test_authenticated_interoperability_api_is_read_only(monkeypatch, tmp_path):
    _clear_interop_env(monkeypatch)
    _app, client = make_client(tmp_path)
    login_web(client, "patient", "patient@example.com", "PatientStrong123")

    response = client.get("/api/v1/interoperability")
    assert response.status_code == 200
    data = response.get_json()
    assert data["provider_neutral"] is True
    assert data["live_exchange_enabled"] is False

    response = client.post(
        "/api/v1/interoperability/plan",
        json={
            "adapter_key": "generic_fhir",
            "resource_type": "referral",
            "direction": "export",
        },
    )
    assert response.status_code == 200
    plan = response.get_json()
    assert plan["resource_type"] == "ServiceRequest"
    assert plan["external_action_executed"] is False
    assert plan["execution_mode"] == "PLAN_ONLY"
