from zendoc.official_connectors import connector_readiness, infer_mapping, list_connector_profiles
from zendoc.public_source_registry import public_data_coverage_matrix
from tests.test_milestone1 import login_web, make_client


def test_public_data_coverage_matrix_separates_public_and_private_data():
    coverage = public_data_coverage_matrix()

    assert coverage["geography"]["status"] == "STRONG_OFFICIAL_COVERAGE"
    assert coverage["hospitals_and_nursing_homes"]["sources"]
    assert coverage["pharmacies_and_medical_shops"]["status"] == "STATE_FRAGMENTED"

    assert coverage["patient_medical_records"]["status"] == "PRIVATE_AUTHORIZATION_ONLY"
    assert coverage["patient_medical_records"]["sources"] == []
    assert coverage["provider_private_clinical_records"]["status"] == "PRIVATE_AUTHORIZATION_ONLY"


def test_delhi_nursing_home_mapping_preserves_registration_metadata():
    rows = [
        {
            "registration_no": "DNH-001",
            "nursing_home_name": "Pilot Nursing Home",
            "address": "Delhi",
            "status": "Active",
            "valid_upto": "2027-12-31",
            "beds": "25",
        }
    ]
    result = infer_mapping("delhi_registered_nursing_homes", rows)
    record = result["records"][0]

    assert record["category"] == "nursing_home"
    assert record["state"] == "Delhi"
    assert record["metadata"]["registration_status"] == "Active"
    assert record["metadata"]["valid_upto"] == "2027-12-31"
    assert record["metadata"]["beds"] == "25"


def test_state_drug_controller_connector_is_truthfully_fragmented():
    profile = connector_readiness("cdsco_state_drug_control")

    assert profile["availability"] == "STATE_FRAGMENTED"
    assert profile["connector_type"] == "STATE_SPECIFIC_PUBLIC_LOOKUP_OR_SNAPSHOT"
    assert profile["ready_for_fetch"] is True


def test_owner_coverage_endpoint_is_protected(tmp_path):
    _app, client = make_client(tmp_path)

    denied = client.get("/api/v1/admin/ingestion/coverage")
    assert denied.status_code in {302, 401, 403}

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminStrong123"},
    )
    assert login.status_code == 200
    token = login.get_json()["token"]

    allowed = client.get(
        "/api/v1/admin/ingestion/coverage",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert allowed.status_code == 200
    payload = allowed.get_json()
    assert payload["coverage"]["patient_medical_records"]["status"] == "PRIVATE_AUTHORIZATION_ONLY"
