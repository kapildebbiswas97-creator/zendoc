from zendoc.geography_region_registry import import_lgd_state_registry, list_import_regions
from zendoc.state_geography_bootstrap import bootstrap_state_geography, list_target_states
from tests.test_milestone1 import make_app


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def test_official_state_registry_enables_new_states_without_code_changes(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        result = import_lgd_state_registry([
            {"State Code": "DL-CODE", "State Name (In English)": "Delhi"},
            {"State Code": "KL-CODE", "State Name (In English)": "Kerala"},
            {"State Code": "KA-CODE", "State Name (In English)": "Karnataka"},
            {"State Code": "MH-CODE", "State Name (In English)": "Maharashtra"},
        ])
        assert result["accepted_count"] == 4

        names = {item["name"] for item in list_target_states()}
        assert {"Delhi", "Kerala", "Karnataka", "Maharashtra"} <= names

        preview = bootstrap_state_geography(
            owner_actor(),
            state_slug="delhi",
            districts=[
                {
                    "state_code": "DL-CODE",
                    "code": "DL-D1",
                    "name": "Pilot Delhi District",
                }
            ],
            dry_run=True,
        )
        assert preview["validation"]["valid"] is True
        assert preview["state"]["name"] == "Delhi"


def test_registry_lookup_persists_source_provenance(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        import_lgd_state_registry(
            [{"State Code": "KL-X", "State Name": "Kerala"}],
            source="lgd_official_snapshot",
        )
        regions = list_import_regions(country_code="IN", region_level="state")
        kerala = next(item for item in regions if item["name"] == "Kerala")
        assert kerala["region_code"] == "KL-X"
        assert kerala["source"] == "lgd_official_snapshot"
        assert kerala["source_ref"] == "state:KL-X"
