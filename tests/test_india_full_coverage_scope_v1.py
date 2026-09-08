from zendoc.india_regions import INDIA_REGIONS
from zendoc.state_source_priorities import state_source_priority
from tests.test_milestone1 import make_client


def test_india_scope_contains_all_current_states_and_union_territories():
    states = [item for item in INDIA_REGIONS if item["region_type"] == "state"]
    uts = [item for item in INDIA_REGIONS if item["region_type"] == "union_territory"]

    assert len(states) == 28
    assert len(uts) == 8
    assert len(INDIA_REGIONS) == 36


def test_priority_districts_do_not_limit_full_region_scope():
    west_bengal = state_source_priority("west_bengal")
    assam = state_source_priority("assam")

    assert west_bengal["coverage_scope"] == "FULL_REGION"
    assert assam["coverage_scope"] == "FULL_REGION"
    assert west_bengal["priority_districts"] == ["Nadia"]
    assert assam["priority_districts"] == ["Dibrugarh"]


def test_non_priority_states_are_still_first_class_coverage_targets():
    for slug in ("maharashtra", "kerala", "telangana", "uttarakhand", "tamil_nadu", "goa", "ladakh"):
        profile = state_source_priority(slug)
        assert profile["configured"] is True
        assert profile["coverage_scope"] == "FULL_REGION"
        assert "lgd" in profile["official_directory_sources"]


def test_india_regions_owner_endpoint_reports_28_states_and_8_uts(tmp_path):
    _app, client = make_client(tmp_path)

    denied = client.get("/api/v1/admin/ingestion/india-regions")
    assert denied.status_code in {302, 401, 403}

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminStrong123"},
    )
    token = login.get_json()["token"]
    allowed = client.get(
        "/api/v1/admin/ingestion/india-regions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert allowed.status_code == 200
    payload = allowed.get_json()
    assert payload["state_count"] == 28
    assert payload["union_territory_count"] == 8
    assert len(payload["regions"]) == 36
