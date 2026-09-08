from zendoc.data_gap_registry import build_collection_plan, get_data_gap
from zendoc.official_connectors import connector_readiness, infer_mapping, list_connector_profiles
from tests.test_milestone1 import api_token, make_app


def test_connector_readiness_never_claims_unconfigured_live_access(monkeypatch):
    monkeypatch.delenv("ZENDOC_DATA_GOV_API_KEY", raising=False)
    monkeypatch.delenv("ZENDOC_DATA_GOV_HOSPITAL_RESOURCE_ID", raising=False)

    hospital = connector_readiness("data_gov_hospitals")
    assert hospital["ready_for_fetch"] is False
    assert "ZENDOC_DATA_GOV_API_KEY" in hospital["missing_config"]

    hfr = connector_readiness("abdm_hfr")
    assert hfr["ready_for_fetch"] is False
    assert hfr["availability"] == "ONBOARDING_REQUIRED"

    wbhs = connector_readiness("wbhs_empanelled_hco")
    assert wbhs["ready_for_fetch"] is True
    assert wbhs["availability"] == "MANUAL_SNAPSHOT_NOW"


def test_official_mapping_template_is_deterministic_not_fuzzy():
    rows = [
        {
            "hospital_code": "WB-001",
            "hospital_name": "District Hospital",
            "district": "Nadia",
            "state": "West Bengal",
            "phone": "0000000000",
        }
    ]
    result = infer_mapping("data_gov_hospitals", rows)

    assert result["source_id"] == "data_gov_hospitals"
    assert result["canonical_record_count"] == 1
    record = result["records"][0]
    assert record["source_record_id"] == "WB-001"
    assert record["name"] == "District Hospital"
    assert record["category"] == "hospital"
    assert result["mapping_template"]["deterministic_alias_match_only"] is True


def test_wbhs_mapping_preserves_scheme_metadata():
    rows = [
        {
            "hospital_code": "HCO-1",
            "hospital_name": "Pilot HCO",
            "address": "Kolkata",
            "class": "Class I",
            "valid_upto": "2027-03-31",
            "facilities": "General Medicine",
        }
    ]
    result = infer_mapping("wbhs_empanelled_hco", rows)
    record = result["records"][0]

    assert record["category"] == "hospital"
    assert record["metadata"]["hco_class"] == "Class I"
    assert record["metadata"]["valid_upto"] == "2027-03-31"
    assert record["metadata"]["facilities_available"] == "General Medicine"


def test_data_gap_collection_plan_prioritizes_no_capital_p0_work():
    plan = build_collection_plan()
    p0_ids = {item["gap_id"] for item in plan["priority_zero"]}

    assert "pharmacy_live_stock" in p0_ids
    assert "pharmacy_actual_price" in p0_ids
    assert "lab_live_slots" in p0_ids
    assert "lab_actual_price" in p0_ids
    assert "provider_response_time" in p0_ids
    assert "personal_health_records" in p0_ids

    assert "pharmacy_live_stock" in plan["no_capital_collect_now"]
    assert "provider_response_time" in plan["no_capital_collect_now"]
    assert "ambulance_live_dispatch" in plan["partner_or_authorized_integration_required"]


def test_data_gap_minimum_fields_avoid_unnecessary_clinical_collection():
    care_barriers = get_data_gap("care_barriers")
    assert care_barriers["tier"] == "ANONYMOUS_OR_CONSENTED_SURVEY"
    assert "district" in care_barriers["minimum_fields"]
    assert "diagnosis" not in care_barriers["minimum_fields"]
    assert "prescription" not in care_barriers["minimum_fields"]


def test_connector_owner_api_is_owner_only(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    token = api_token(client, "connector-normal@example.com")
    denied = client.get(
        "/api/v1/admin/ingestion/connectors",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert denied.status_code == 403

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminStrong123"},
    )
    owner_token = login.get_json()["token"]
    allowed = client.get(
        "/api/v1/admin/ingestion/connectors",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert allowed.status_code == 200
    assert allowed.get_json()["connectors"]


def test_connector_profiles_have_truthful_availability_states():
    allowed = {
        "CONFIGURABLE_NOW",
        "MANUAL_SNAPSHOT_NOW",
        "ONBOARDING_REQUIRED",
        "DIRECTORY_NOW_LIVE_STOCK_UNVERIFIED",
        "STATE_FRAGMENTED",
        "REFERENCE_ONLY",
    }
    assert {item["availability"] for item in list_connector_profiles()} <= allowed


def test_connector_mapping_preserves_canonical_geography_fields():
    rows = [
        {
            "hospital_code": "WB-GEO-1",
            "hospital_name": "Canonical Geography Hospital",
            "district": "Nadia",
            "state": "West Bengal",
            "geography_source": "lgd",
            "geography_source_record_id": "district:320",
        }
    ]

    result = infer_mapping("data_gov_hospitals", rows)
    record = result["records"][0]

    assert record["geography_source"] == "lgd"
    assert record["geography_source_record_id"] == "district:320"
    assert result["mapping_template"]["mapping"]["geography_source"] == "geography_source"
    assert result["mapping_template"]["mapping"]["geography_source_record_id"] == "geography_source_record_id"
