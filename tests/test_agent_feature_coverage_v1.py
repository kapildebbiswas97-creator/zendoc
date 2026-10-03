from zendoc.agent_feature_coverage import (
    FUTURE_GUARDED,
    assert_complete_agent_coverage,
    feature_agent_coverage_snapshot,
)


def test_every_declared_capability_has_explicit_agent_os_owner():
    assert_complete_agent_coverage()
    snapshot = feature_agent_coverage_snapshot()
    assert snapshot["complete"] is True
    assert snapshot["covered_count"] == snapshot["capability_count"]
    assert snapshot["capability_count"] >= 65
    assert snapshot["missing_capabilities"] == []
    assert snapshot["stale_mappings"] == []
    assert snapshot["invalid_mappings"] == []


def test_critical_future_clinical_capability_is_owned_but_not_activated():
    snapshot = feature_agent_coverage_snapshot()
    by_key = {item["capability_key"]: item for item in snapshot["items"]}
    prescribing = by_key["autonomous_prescribing"]
    assert prescribing["primary_agent"] == "MedicationSafetyAgent"
    assert prescribing["safety_agent"] == "SafetyAgent"
    assert prescribing["mode"] == FUTURE_GUARDED
    assert prescribing["capability_status"] == "FUTURE"


def test_high_value_product_features_are_agent_owned():
    snapshot = feature_agent_coverage_snapshot()
    by_key = {item["capability_key"]: item for item in snapshot["items"]}
    expected = {
        "healthcare_finder": "ProviderDiscoveryAgent",
        "appointments": "BookingAgent",
        "health_memory": "HealthMemoryAgent",
        "pharmacy": "PharmacyAgent",
        "medical_transport": "TransportAgent",
        "home_health": "HomeHealthAgent",
        "iot_hub": "IoTAgent",
        "fitness_coach": "FitnessAgent",
        "carefin_engine": "CareFinAgent",
        "connect_messaging": "CommunicationAgent",
        "mental_wellness_private": "CareAgent",
        "connected_payments_gateway": "CommerceAgent",
    }
    for capability, agent in expected.items():
        assert by_key[capability]["primary_agent"] == agent
        assert by_key[capability]["agent_status"] != "disabled"
