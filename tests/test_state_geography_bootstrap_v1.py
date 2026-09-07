from zendoc.geography_graph import list_geography_relationships
from zendoc.state_geography_bootstrap import (
    bootstrap_state_geography,
    list_target_states,
    state_coverage_summary,
)
from tests.test_milestone1 import make_app


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def sample_payload(state_code, district_code, subdistrict_code, block_code, panchayat_code, village_code, district_name, subdistrict_name, village_name):
    return {
        "districts": [
            {"state_code": state_code, "code": district_code, "name": district_name},
        ],
        "subdistricts": [
            {
                "state_code": state_code,
                "code": subdistrict_code,
                "name": subdistrict_name,
                "district_code": district_code,
            },
        ],
        "blocks": [
            {
                "state_code": state_code,
                "code": block_code,
                "name": f"{subdistrict_name} Block",
                "district_code": district_code,
                "subdistrict_code": subdistrict_code,
            },
        ],
        "panchayats": [
            {
                "state_code": state_code,
                "code": panchayat_code,
                "name": f"{subdistrict_name} GP",
                "district_code": district_code,
                "block_code": block_code,
            },
        ],
        "villages": [
            {
                "state_code": state_code,
                "code": village_code,
                "name": village_name,
                "district_code": district_code,
                "subdistrict_code": subdistrict_code,
                "block_code": block_code,
                "panchayat_code": panchayat_code,
            },
        ],
    }


def test_target_states_are_exactly_requested_states():
    states = {item["slug"]: item for item in list_target_states()}
    assert states["west_bengal"]["lgd_state_code"] == "19"
    assert states["assam"]["lgd_state_code"] == "18"
    assert states["uttar_pradesh"]["lgd_state_code"] == "9"


def test_west_bengal_bootstrap_builds_district_subdistrict_village_and_links(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        payload = sample_payload(
            "19", "WB-D1", "WB-SD1", "WB-B1", "WB-GP1", "WB-V1",
            "Nadia", "Ranaghat", "Pilot Village WB",
        )

        preview = bootstrap_state_geography(
            owner_actor(),
            state_slug="west_bengal",
            **payload,
            dry_run=True,
            freshness_at="2026-09-01T00:00:00+00:00",
        )
        assert preview["validation"]["valid"] is True

        result = bootstrap_state_geography(
            owner_actor(),
            state_slug="west_bengal",
            **payload,
            dry_run=False,
            freshness_at="2026-09-01T00:00:00+00:00",
        )
        assert result["applied"]["districts"] == 1
        assert result["applied"]["subdistricts"] == 1
        assert result["applied"]["villages"] == 1
        assert result["applied"]["relationships"] >= 2

        coverage = state_coverage_summary("west_bengal")
        assert coverage["loaded"] is True
        assert coverage["counts"]["district"] == 1
        assert coverage["counts"]["subdivision"] == 1
        assert coverage["counts"]["village"] == 1
        assert coverage["relationships"]["VILLAGE_TO_PANCHAYAT"] >= 1


def test_assam_bootstrap_supports_same_state_scale_path(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        payload = sample_payload(
            "18", "AS-D1", "AS-SD1", "AS-B1", "AS-GP1", "AS-V1",
            "Dibrugarh", "Dibrugarh East", "Pilot Village Assam",
        )
        result = bootstrap_state_geography(
            owner_actor(),
            state_slug="assam",
            **payload,
            dry_run=False,
        )
        assert result["state"]["name"] == "Assam"
        assert state_coverage_summary("assam")["counts"]["village"] == 1


def test_uttar_pradesh_bootstrap_supports_same_state_scale_path(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        payload = sample_payload(
            "9", "UP-D1", "UP-SD1", "UP-B1", "UP-GP1", "UP-V1",
            "Lucknow", "Lucknow Tehsil", "Pilot Village UP",
        )
        result = bootstrap_state_geography(
            owner_actor(),
            state_slug="uttar_pradesh",
            **payload,
            dry_run=False,
        )
        assert result["state"]["name"] == "Uttar Pradesh"
        assert state_coverage_summary("uttar_pradesh")["counts"]["village"] == 1


def test_state_bootstrap_rejects_cross_state_rows(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        preview = bootstrap_state_geography(
            owner_actor(),
            state_slug="assam",
            districts=[{"state_code": "19", "code": "BAD-D1", "name": "Wrong State District"}],
            dry_run=True,
        )
        assert preview["validation"]["valid"] is False
        assert preview["validation"]["rejected_count"] == 1
        assert "does not match target state code 18" in preview["validation"]["rejected"][0]["reason"]


def test_geography_relationships_keep_panchayat_separate_from_admin_parent(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        payload = sample_payload(
            "19", "WB-D2", "WB-SD2", "WB-B2", "WB-GP2", "WB-V2",
            "Test District", "Test Subdistrict", "Test Village",
        )
        bootstrap_state_geography(owner_actor(), state_slug="west_bengal", **payload, dry_run=False)

        from zendoc.db import get_db
        village = get_db().execute(
            "SELECT id,parent_id FROM geography_nodes WHERE source_ref='village:WB-V2'"
        ).fetchone()
        parent = get_db().execute("SELECT node_type FROM geography_nodes WHERE id=?", (village["parent_id"],)).fetchone()
        assert parent["node_type"] == "subdivision"

        relationships = list_geography_relationships(village["id"])
        types = {item["relationship_type"] for item in relationships}
        assert "VILLAGE_TO_PANCHAYAT" in types
        assert "BLOCK_MEMBERSHIP" in types
