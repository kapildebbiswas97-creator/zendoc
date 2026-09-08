from zendoc.official_connectors import connector_readiness, infer_mapping
from zendoc.state_source_priorities import state_source_priority


def test_west_bengal_swasthya_sathi_mapping_is_deterministic():
    rows = [
        {
            "hospital_code": "SS-WB-1",
            "hospital_name": "Pilot Swasthya Sathi Hospital",
            "district": "Nadia",
            "status": "Active",
            "services": "General Medicine",
        }
    ]
    result = infer_mapping("swasthya_sathi_hospitals", rows)
    record = result["records"][0]

    assert record["source_record_id"] == "SS-WB-1"
    assert record["state"] == "West Bengal"
    assert record["category"] == "hospital"
    assert record["metadata"]["empanelment_status"] == "Active"
    assert record["metadata"]["services"] == "General Medicine"


def test_up_nhm_source_is_state_priority_and_manual_snapshot():
    profile = state_source_priority("uttar_pradesh")
    assert "up_nhm_health_facilities" in profile["official_directory_sources"]
    assert "up_nhm_health_facilities" in profile["state_specific_sources"]

    readiness = connector_readiness("up_nhm_health_facilities")
    assert readiness["availability"] == "MANUAL_SNAPSHOT_NOW"
    assert readiness["connector_type"] == "DATED_OFFICIAL_WEB_OR_DOCUMENT_SNAPSHOT"


def test_up_nhm_phc_mapping_preserves_programme_and_type():
    rows = [
        {
            "facility_code": "UP-PHC-1",
            "facility_name": "Pilot Urban PHC",
            "facility_type": "PHC",
            "district": "Lucknow",
            "programme": "NUHM",
            "source_date": "2026-08-01",
        }
    ]
    result = infer_mapping("up_nhm_health_facilities", rows)
    record = result["records"][0]

    assert record["source_record_id"] == "UP-PHC-1"
    assert record["state"] == "Uttar Pradesh"
    assert record["category"] == "PHC"
    assert record["metadata"]["programme"] == "NUHM"
    assert record["metadata"]["source_date"] == "2026-08-01"


def test_nabl_lab_mapping_uses_accreditation_number_as_identity():
    rows = [
        {
            "accreditation_no": "NABL-123",
            "laboratory_name": "Pilot Pathology Lab",
            "district": "Nadia",
            "state": "West Bengal",
            "status": "Active",
            "valid_upto": "2027-12-31",
        }
    ]
    result = infer_mapping("nabl_labs", rows)
    record = result["records"][0]

    assert record["source_record_id"] == "NABL-123"
    assert record["category"] == "laboratory"
    assert record["metadata"]["accreditation_status"] == "Active"
    assert record["metadata"]["valid_upto"] == "2027-12-31"


def test_jan_aushadhi_kendra_mapping_is_pharmacy_not_live_stock():
    rows = [
        {
            "kendra_code": "PMBJP-001",
            "kendra_name": "Pilot Jan Aushadhi Kendra",
            "district": "Dibrugarh",
            "state": "Assam",
        }
    ]
    result = infer_mapping("pmbjp_kendras", rows)
    record = result["records"][0]

    assert record["source_record_id"] == "PMBJP-001"
    assert record["category"] == "pharmacy"
    assert record["metadata"]["kendra_code"] == "PMBJP-001"
