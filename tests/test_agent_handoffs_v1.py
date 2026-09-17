from zendoc.agent_handoffs import handoff_for_intent, handoff_manifest


def test_booking_handoff_keeps_discovery_booking_care_and_memory_separate():
    chain = handoff_for_intent("appointment_booking")
    agents = [stage["agent"] for stage in chain]
    assert agents == [
        "SafetyAgent",
        "ProviderDiscoveryAgent",
        "BookingAgent",
        "CareAgent",
        "HealthMemoryAgent",
    ]
    booking = next(stage for stage in chain if stage["agent"] == "BookingAgent")
    assert booking["gate"] == "explicit_user_confirmation"
    care = next(stage for stage in chain if stage["agent"] == "CareAgent")
    assert care["gate"] == "provider_confirmation"


def test_pharmacy_handoff_requires_medication_guard_and_user_confirmation():
    chain = handoff_for_intent("pharmacy")
    agents = [stage["agent"] for stage in chain]
    assert "MedicationSafetyAgent" in agents
    pharmacy = next(stage for stage in chain if stage["agent"] == "PharmacyAgent")
    assert pharmacy["gate"] == "explicit_user_confirmation"


def test_lifecycle_handoff_never_skips_explicit_life_stage_and_consent():
    chain = handoff_for_intent("lifecycle")
    lifecycle = next(stage for stage in chain if stage["agent"] == "LifecycleAgent")
    family = next(stage for stage in chain if stage["agent"] == "FamilyCareAgent")
    assert lifecycle["gate"] == "explicit_user_selected_life_stage"
    assert family["gate"] == "adult_patient_or_guardian_consent"


def test_handoff_manifest_preserves_non_bypass_invariants():
    manifest = handoff_manifest()
    invariants = manifest["invariants"]
    assert invariants["handoff_grants_new_tool_permissions"] is False
    assert invariants["external_unknown_becomes_confirmed"] is False
    assert invariants["provider_confirmed_equals_patient_reported"] is False
    assert invariants["model_executes_payment"] is False
    assert invariants["model_can_self_promote"] is False
    assert invariants["clinical_authority_remains_human"] is True
