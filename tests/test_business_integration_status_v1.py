from zendoc.business_api import create_business_api_client, issue_business_api_key
from tests.test_milestone1 import make_client


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def test_partner_integration_status_reports_scopes_without_patient_capability(tmp_path):
    app, client = make_client(tmp_path)
    with app.app_context():
        partner = create_business_api_client(
            owner_actor(),
            {
                "name": "Integration Partner",
                "client_type": "hospital",
                "allowed_scopes": [
                    "public_directory.read",
                    "provider_profile.read",
                    "provider_availability.read",
                    "booking_handoff.write",
                ],
            },
        )
        key = issue_business_api_key(owner_actor(), partner["id"], expires_in_days=30)

    response = client.get(
        "/api/v1/business/integration-status",
        headers={"X-ZENDOC-Partner-Key": key["api_key"]},
    )
    assert response.status_code == 200
    payload = response.get_json()["integration"]
    assert payload["authenticated"] is True
    assert payload["capabilities"]["public_directory"] == "enabled_by_scope"
    assert payload["capabilities"]["booking_handoff"] == "enabled_by_scope"
    assert payload["capabilities"]["patient_records"] == "not_available"
    assert payload["capabilities"]["medical_history"] == "not_available"
    assert payload["capabilities"]["prescriptions"] == "not_available"
    assert payload["capabilities"]["clinical_data"] == "not_available"
