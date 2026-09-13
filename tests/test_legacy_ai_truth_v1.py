from zendoc.ai import assistant_answer, doctor_prediction


def test_legacy_pharmacy_guidance_matches_current_truth_boundary():
    answer = assistant_answer("Can ZENDOC help with my medicine and pharmacy order?")
    lowered = answer.lower()

    assert "pharmacy" in lowered
    assert "planned for a future phase" not in lowered
    assert "actually confirmed" in lowered
    assert "integration as required" in lowered


def test_legacy_ambulance_guidance_never_claims_dispatch():
    answer = assistant_answer("Can you get an ambulance for me?")
    lowered = answer.lower()

    assert "emergency services" in lowered
    assert "does not claim an ambulance was dispatched" in lowered
    assert "real connected provider confirms" in lowered


def test_legacy_ai_explains_governed_execution_boundary():
    answer = assistant_answer("How does your AI model run tools?")
    lowered = answer.lower()

    assert "deterministic safety" in lowered
    assert "server-side permissions" in lowered
    assert "consent" in lowered
    assert "audit" in lowered


def test_legacy_symptom_fallback_is_explicitly_non_diagnostic():
    result = doctor_prediction("I feel unusual today")

    assert result["risk_level"] == "low"
    assert "does not diagnose" in result["next_steps"].lower()
