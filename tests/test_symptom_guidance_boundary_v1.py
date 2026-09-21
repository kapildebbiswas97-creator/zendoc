from tests.legacy_milestone7 import api_token, headers
from tests.test_milestone1 import make_client
from zendoc.ai import doctor_prediction


def test_legacy_doctor_prediction_is_non_diagnostic():
    result = doctor_prediction("fever and cough for two days")
    assert result["scope"] == "non_diagnostic_symptom_guidance"
    assert result["diagnosis"] is None
    assert result["prescription"] is None
    assert result["medication_change"] is None
    assert "possible respiratory infection" not in result["summary"].lower()
    assert "does not diagnose" in result["next_steps"].lower()


def test_legacy_ai_doctor_api_preserves_non_diagnostic_boundary(tmp_path):
    _app, client = make_client(tmp_path)
    token = api_token(client, "symptom-guidance@example.com")

    response = client.post(
        "/api/v1/ai/doctor",
        json={"symptoms": "headache and nausea"},
        headers=headers(token),
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["scope"] == "non_diagnostic_symptom_guidance"
    assert payload["diagnosis"] is None
    assert payload["prescription"] is None
    assert payload["medication_change"] is None
    assert "possible migraine" not in payload["summary"].lower()


def test_emergency_symptom_guidance_does_not_claim_dispatch():
    result = doctor_prediction("severe chest pain and trouble breathing")
    assert result["emergency"] is True
    assert result["diagnosis"] is None
    assert result["prescription"] is None
    text = f"{result['summary']} {result['next_steps']}".lower()
    assert "dispatch" not in text or "does not" in text
