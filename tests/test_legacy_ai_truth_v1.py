from zendoc.ai import assistant_answer, doctor_prediction
from tests.test_milestone1 import login_web, make_client, register_web


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


def test_ai_page_labels_deterministic_helpers_truthfully(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "ai-guided-tools@example.com")
    login_web(client, "patient", "ai-guided-tools@example.com")

    response = client.get("/ai")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Platform navigation helper" in body
    assert "does not call a model or execute tools" in body
    assert "Not a diagnosis or clinical assessment" in body
