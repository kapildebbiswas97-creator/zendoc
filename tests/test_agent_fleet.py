from zendoc.agent_fleet import automation_manifest, get_fleet_agent, list_fleet_agents


def test_specialized_agent_fleet_contains_core_domains():
    ids = {agent["agent_id"] for agent in list_fleet_agents()}
    assert {
        "SafetyAgent",
        "CareFinAgent",
        "ProviderDiscoveryAgent",
        "HealthMemoryAgent",
        "MedicationSafetyAgent",
        "PharmacyAgent",
        "DiagnosticsAgent",
        "DoctorAgent",
        "FamilyCareAgent",
        "IoTAgent",
        "NutritionAgent",
        "OperationsAgent",
    } <= ids


def test_carefin_agent_cannot_fabricate_coverage():
    agent = get_fleet_agent("CareFinAgent")
    assert "fabricate_approval" in agent["forbidden"]
    assert "official_or_partner_confirmation_for_coverage" in agent["human_gates"]


def test_pharmacy_agent_requires_confirmation():
    agent = get_fleet_agent("PharmacyAgent")
    assert "explicit_user_confirmation" in agent["human_gates"]
    assert "submit_without_confirmation" in agent["forbidden"]


def test_automation_manifest_is_truthful():
    manifest = automation_manifest()
    assert manifest["agent_count"] >= 10
    assert "SafetyAgent" in manifest["automatic_agents"]
    assert "PharmacyAgent" in manifest["human_gated_agents"]
