from zendoc.benefit_sources import coverage_truth_state, get_source, list_sources


def test_benefit_source_registry_contains_core_india_sources():
    ids = {item["source_id"] for item in list_sources()}
    assert {"myscheme", "abdm", "pmjay", "swasthya_sathi", "lic", "irdai", "ngo_darpan", "mca_csr"} <= ids


def test_west_bengal_source_filter_keeps_national_and_state_sources():
    ids = {item["source_id"] for item in list_sources(geography="WEST_BENGAL")}
    assert "swasthya_sathi" in ids
    assert "pmjay" in ids
    assert "lic" in ids


def test_personal_coverage_is_never_confirmed_from_discovery_only():
    result = coverage_truth_state(source_id="lic")
    assert result["status"] == "DISCOVERY_ONLY"
    assert result["confirmed"] is False


def test_authorized_provider_evidence_can_be_confirmed():
    result = coverage_truth_state(
        source_id="pmjay",
        evidence_type="GOVERNMENT_RESPONSE",
        provider_confirmed=True,
    )
    assert result["status"] == "CONFIRMED"
    assert result["confirmed"] is True


def test_public_source_metadata_does_not_contain_credentials():
    source = get_source("abdm")
    serialized = str(source).lower()
    assert "api_key" not in serialized
    assert "password" not in serialized
    assert "token" not in serialized
