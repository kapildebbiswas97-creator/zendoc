from zendoc.agent_fleet import automation_manifest, get_fleet_agent, list_fleet_agents


def test_specialized_agent_fleet_contains_core_domains():
    ids = {agent["agent_id"] for agent in list_fleet_agents()}
    assert {
        "SafetyAgent",
        "CareFinAgent",
        "ProviderDiscoveryAgent",
        "BookingAgent",
        "CommerceAgent",
        "HealthMemoryAgent",
        "PreventionAgent",
        "LifecycleAgent",
        "LearningAgent",
        "MedicationSafetyAgent",
        "PharmacyAgent",
        "DiagnosticsAgent",
        "DoctorAgent",
        "FamilyCareAgent",
        "IoTAgent",
        "NutritionAgent",
        "ModelImprovementAgent",
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


def test_booking_agent_is_autonomous_only_until_confirmation():
    agent = get_fleet_agent("BookingAgent")
    assert agent["automation_level"] == "AUTOMATIC_UNTIL_CONFIRMATION"
    assert "explicit_user_confirmation_before_booking" in agent["human_gates"]
    assert "finalize_without_confirmation" in agent["forbidden"]
    assert "execute_payment" in agent["forbidden"]


def test_commerce_agent_separates_commercial_and_clinical_authority():
    agent = get_fleet_agent("CommerceAgent")
    assert "clinical_commerce_separation" in agent["deterministic_first"]
    assert "hidden_sponsored_ranking" in agent["forbidden"]
    assert "execute_payment" in agent["forbidden"]


def test_model_improvement_agent_cannot_self_promote_or_deploy():
    agent = get_fleet_agent("ModelImprovementAgent")
    assert agent["automation_level"] == "AUTOMATIC_SANDBOX_ONLY"
    assert "configured_owner_review_before_promotion" in agent["human_gates"]
    assert "self_promote_model" in agent["forbidden"]
    assert "deploy_production" in agent["forbidden"]
    assert "disable_safety" in agent["forbidden"]


def test_automation_manifest_is_truthful():
    manifest = automation_manifest()
    assert manifest["agent_count"] >= 18
    assert "SafetyAgent" in manifest["automatic_agents"]
    assert "BookingAgent" in manifest["human_gated_agents"]
    assert "PharmacyAgent" in manifest["human_gated_agents"]
    assert "ModelImprovementAgent" in manifest["human_gated_agents"]
