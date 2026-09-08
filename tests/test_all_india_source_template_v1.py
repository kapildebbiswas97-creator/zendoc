from zendoc.state_source_priorities import (
    BASELINE_INDIA_DIRECTORY_SOURCES,
    BASELINE_LIVE_DATA_GAPS,
    state_source_priority,
)


def test_indian_state_without_state_specific_connectors_still_gets_full_national_scope():
    profile = state_source_priority("tamil_nadu")

    assert profile["configured"] is True
    assert profile["template"] == "INDIA_NATIONAL_SCOPE_V1"
    assert profile["coverage_scope"] == "FULL_REGION"
    for source in (
        "lgd",
        "data_gov_hospitals",
        "clinical_establishments",
        "pmjay_hospitals",
        "nabl_labs",
        "nabh_directory",
        "pmbjp_kendras",
        "data_gov_blood_banks",
        "cdsco_state_drug_control",
    ):
        assert source in profile["official_directory_sources"]

    assert profile["state_specific_sources"] == []
    assert "pharmacy_actual_price" in profile["live_data_gaps"]
    assert "lab_actual_price" in profile["live_data_gaps"]


def test_state_enriched_profile_keeps_baseline_and_state_sources():
    profile = state_source_priority("kerala")

    assert profile["configured"] is True
    assert profile["template"] == "STATE_ENRICHED_V1"
    assert "kerala_health_institutions" in profile["state_specific_sources"]
    assert "kerala_ehealth_hospitals" in profile["state_specific_sources"]

    for source in BASELINE_INDIA_DIRECTORY_SOURCES:
        assert source in profile["official_directory_sources"]

    for gap in BASELINE_LIVE_DATA_GAPS:
        assert gap in profile["live_data_gaps"]


def test_priority_profiles_do_not_duplicate_source_ids():
    for state in (
        "west_bengal",
        "assam",
        "uttar_pradesh",
        "delhi",
        "kerala",
        "karnataka",
        "maharashtra",
        "tamil_nadu",
    ):
        profile = state_source_priority(state)
        sources = profile["official_directory_sources"]
        assert len(sources) == len(set(sources))
