from zendoc.business_api import authenticate_business_api_key, create_business_api_client, issue_business_api_key
from zendoc.institution_pilots import create_institution_pilot, pilot_execution_summary, pilot_system_telemetry
from tests.test_milestone1 import make_app


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def test_pilot_system_telemetry_derives_only_linked_b2b_activity(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        pilot = create_institution_pilot(
            owner_actor(),
            {"organization_name": "Telemetry Hospital", "organization_type": "hospital"},
        )
        client = create_business_api_client(
            owner_actor(),
            {
                "name": "Telemetry Client",
                "client_type": "hospital",
                "pilot_id": pilot["id"],
                "allowed_scopes": ["public_directory.read"],
            },
        )
        key = issue_business_api_key(owner_actor(), client["id"], expires_in_days=30)

        authenticate_business_api_key(
            key["api_key"],
            required_scope="public_directory.read",
            endpoint="/api/v1/business/public-directory",
            method="GET",
        )
        authenticate_business_api_key(
            key["api_key"],
            required_scope="public_directory.read",
            endpoint="/api/v1/business/public-directory",
            method="GET",
        )

        telemetry = pilot_system_telemetry(owner_actor(), pilot["id"], days=30)
        assert telemetry["linked_api_clients"] == 1
        assert telemetry["active_api_clients"] == 1
        assert telemetry["api_requests"] >= 2
        assert telemetry["source_type"] == "system_derived"
        assert "patient_users" not in telemetry
        assert "completed_appointments" not in telemetry

        execution = pilot_execution_summary(owner_actor(), pilot["id"])
        assert execution["system_telemetry"]["linked_api_clients"] == 1
        assert execution["latest_usage"] is None
