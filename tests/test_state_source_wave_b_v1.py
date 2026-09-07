from zendoc.official_connectors import infer_mapping
from zendoc.state_source_priorities import state_source_priority


def test_delhi_priority_stack_uses_state_hospital_and_nursing_home_sources():
    profile = state_source_priority("delhi")
    assert profile["configured"] is True
    assert "delhi_government_hospitals" in profile["official_directory_sources"]
    assert "delhi_registered_nursing_homes" in profile["official_directory_sources"]


def test_kerala_priority_stack_uses_health_and_ehealth_sources():
    profile = state_source_priority("kerala")
    assert profile["configured"] is True
    assert "kerala_health_institutions" in profile["official_directory_sources"]
    assert "kerala_ehealth_hospitals" in profile["official_directory_sources"]


def test_karnataka_priority_stack_marks_reference_infrastructure_source():
    profile = state_source_priority("karnataka")
    assert profile["configured"] is True
    assert "karnataka_health_infrastructure" in profile["official_directory_sources"]


def test_maharashtra_priority_stack_uses_dmer_and_fda_sources():
    profile = state_source_priority("maharashtra")
    assert profile["configured"] is True
    assert "maharashtra_dmer_hospitals" in profile["official_directory_sources"]
    assert "maharashtra_fda_drug_licenses" in profile["official_directory_sources"]


def test_kerala_health_mapping_preserves_bed_metadata_without_claiming_vacancy():
    rows = [
        {
            "institution_code": "KL-001",
            "institution_name": "Pilot Taluk Hospital",
            "institution_category": "hospital",
            "district": "Ernakulam",
            "sanctioned beds": "100",
            "functional beds": "80",
        }
    ]
    result = infer_mapping("kerala_health_institutions", rows)
    record = result["records"][0]

    assert record["state"] == "Kerala"
    assert record["metadata"]["sanctioned_beds"] == "100"
    assert record["metadata"]["functional_beds"] == "80"


def test_maharashtra_dmer_mapping_preserves_medical_college_context():
    rows = [
        {
            "hospital_code": "MH-001",
            "hospital_name": "Pilot Government Hospital",
            "district": "Pune",
            "medical_college": "Pilot Government Medical College",
        }
    ]
    result = infer_mapping("maharashtra_dmer_hospitals", rows)
    record = result["records"][0]

    assert record["state"] == "Maharashtra"
    assert record["category"] == "hospital"
    assert record["metadata"]["medical_college"] == "Pilot Government Medical College"
