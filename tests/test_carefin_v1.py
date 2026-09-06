import pytest

from zendoc.agent_planner import build_plan
from zendoc.agent_registry import choose_agent_for_intent
from zendoc.carefin_engine import (
    APPROVED,
    CONFIRMED,
    DISCOVERED,
    EVIDENCE_RECEIVED,
    PAID,
    discover_benefits,
    transition_coverage_state,
)
from tests.test_milestone1 import make_app


def test_carefin_west_bengal_discovery_includes_state_and_national_sources():
    result = discover_benefits({
        "state": "West Bengal",
        "age": 42,
        "occupation": "self employed",
        "income_band": "low",
        "desired_categories": ["state_health_scheme", "government_health_assurance"],
    })
    ids = {item["source_id"] for item in result["candidates"]}
    assert "swasthya_sathi" in ids
    assert "pmjay" in ids
    assert result["coverage_confirmed"] is False
    assert all(item["provenance"]["personal_coverage_confirmed"] is False for item in result["candidates"])


def test_carefin_discovery_never_marks_approved_or_paid():
    result = discover_benefits({
        "state": "West Bengal",
        "needs_charitable_support": True,
        "district": "Nadia",
    })
    states = {item["state"] for item in result["candidates"]}
    assert APPROVED not in states
    assert PAID not in states
    assert states <= {DISCOVERED, "POTENTIALLY_ELIGIBLE"}


def test_carefin_uploaded_policy_is_not_authoritative_confirmation():
    with pytest.raises(PermissionError):
        transition_coverage_state(
            source_id="lic",
            current_state=EVIDENCE_RECEIVED,
            target_state=CONFIRMED,
            evidence_type="USER_AUTHORIZED_POLICY",
            authoritative_confirmation=True,
            evidence_reference="policy-upload-1",
        )


def test_carefin_confirmation_requires_authoritative_reference():
    with pytest.raises(PermissionError):
        transition_coverage_state(
            source_id="pmjay",
            current_state=EVIDENCE_RECEIVED,
            target_state=CONFIRMED,
            evidence_type="GOVERNMENT_RESPONSE",
            authoritative_confirmation=True,
        )

    result = transition_coverage_state(
        source_id="pmjay",
        current_state=EVIDENCE_RECEIVED,
        target_state=CONFIRMED,
        evidence_type="GOVERNMENT_RESPONSE",
        authoritative_confirmation=True,
        evidence_reference="official-response-123",
    )
    assert result["state"] == CONFIRMED
    assert result["coverage_confirmed"] is True


def test_carefin_paid_cannot_skip_approval():
    with pytest.raises(ValueError):
        transition_coverage_state(
            source_id="pmjay",
            current_state=CONFIRMED,
            target_state=PAID,
            evidence_type="GOVERNMENT_RESPONSE",
            authoritative_confirmation=True,
            evidence_reference="payment-1",
        )


def test_specialist_registry_maps_new_intents():
    assert choose_agent_for_intent("carefin").identifier == "CareFinAgent"
    assert choose_agent_for_intent("prescription").identifier == "MedicationSafetyAgent"
    assert choose_agent_for_intent("diagnostics").identifier == "DiagnosticsAgent"
    assert choose_agent_for_intent("nutrition").identifier == "NutritionAgent"


def test_planner_routes_carefin_with_metadata(tmp_path):
    app = make_app(tmp_path)
    actor = {"id": 7, "role": "patient", "active": 1, "email": "patient@example.com"}
    with app.app_context():
        plan = build_plan(actor, "Find government schemes and insurance help for hospital treatment")
    data = plan.to_dict()
    assert data["assigned_agent"] == "CareFinAgent"
    assert data["intent"] == "carefin"
    assert data["privacy_class"] == "PERSONAL"
    assert data["steps"][0]["tool_name"] == "discover_carefin_benefits"
    assert "location" in data["required_context"]


def test_planner_emergency_still_precedes_benefits(tmp_path):
    app = make_app(tmp_path)
    actor = {"id": 7, "role": "patient", "active": 1, "email": "patient@example.com"}
    with app.app_context():
        plan = build_plan(actor, "I have chest pain and cannot breathe, also check insurance")
    assert plan.assigned_agent == "SafetyAgent"
    assert plan.intent == "emergency"
    assert plan.privacy_class == "HIGH_RISK"
