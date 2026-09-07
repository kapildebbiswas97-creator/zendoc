from zendoc.state_source_priorities import state_source_priority
from tests.test_milestone1 import login_web, make_client


def test_assam_priority_stack_targets_dibrugarh_and_official_sources():
    profile = state_source_priority("assam")
    assert profile["configured"] is True
    assert "Dibrugarh" in profile["priority_districts"]
    assert "assam_health_institutes" in profile["official_directory_sources"]
    assert "assam_medical_colleges" in profile["official_directory_sources"]
    assert "pharmacy_live_stock" in profile["live_data_gaps"]


def test_west_bengal_priority_stack_targets_nadia():
    profile = state_source_priority("west_bengal")
    assert profile["configured"] is True
    assert profile["priority_districts"] == ["Nadia"]
    assert "wbhs_empanelled_hco" in profile["official_directory_sources"]


def test_unconfigured_state_gets_safe_default_stack():
    profile = state_source_priority("kerala")
    assert profile["configured"] is False
    assert "lgd" in profile["official_directory_sources"]
    assert "hospital_bed_availability" in profile["live_data_gaps"]


def test_owner_state_priority_api_is_protected(tmp_path):
    _app, client = make_client(tmp_path)

    denied = client.get("/api/v1/admin/ingestion/state-priority/assam")
    assert denied.status_code in {302, 401, 403}

    login = login_web(client, "admin", "admin@example.com", "AdminStrong123")
    assert login.status_code == 200

    allowed = client.get("/api/v1/admin/ingestion/state-priority/assam")
    assert allowed.status_code == 200
    payload = allowed.get_json()["priority"]
    assert "Dibrugarh" in payload["priority_districts"]
