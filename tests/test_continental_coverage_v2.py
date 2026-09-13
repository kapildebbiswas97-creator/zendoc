from zendoc.continental_coverage import ASIA, EUROPE, OCEANIA, AFRICA_FIRST_WAVE, continent_coverage_summary
from zendoc.global_source_registry import country_coverage_manifest
from zendoc.medical_knowledge_registry import get_medical_knowledge_source
from zendoc.public_source_registry import get_public_ingestion_source
from tests.test_milestone1 import login_web, make_app


def test_continent_catalog_has_requested_full_regions():
    assert len(ASIA) == 48
    assert len(EUROPE) == 44
    assert len(OCEANIA) == 14
    assert len(AFRICA_FIRST_WAVE) >= 10


def test_named_expansion_countries_are_registered_after_app_start(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        coverage = {item["country_code"]: item for item in country_coverage_manifest()}
        for code in ("JP", "FR", "BR", "IL", "IR", "AU", "NZ", "ZA", "KE", "EG", "NG"):
            assert code in coverage
        assert coverage["JP"]["continent"] == "Asia"
        assert coverage["FR"]["continent"] == "Europe"
        assert coverage["AU"]["continent"] == "Oceania"
        assert coverage["ZA"]["continent"] == "Africa"


def test_reviewed_official_sources_are_available_without_false_connectivity(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        japan = get_public_ingestion_source("jp_mhlw_nabii")
        france = get_public_ingestion_source("fr_ans_annuaire_sante")
        brazil = get_public_ingestion_source("br_cnes")
        australia = get_public_ingestion_source("au_nhsd")
        new_zealand = get_public_ingestion_source("nz_healthpoint")
        assert japan["country_code"] == "JP"
        assert "public_healthcare_entities" in japan["ingestion_types"]
        assert france["country_code"] == "FR"
        assert "public_healthcare_entities" in france["ingestion_types"]
        assert brazil["country_code"] == "BR"
        assert "public_healthcare_entities" in brazil["ingestion_types"]
        assert australia["ingestion_types"] == []
        assert new_zealand["ingestion_types"] == []
        assert "SCRAPING_PROHIBITED" in new_zealand["live_fetch_status"]


def test_continental_medical_authorities_keep_snapshot_gate(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        for source_id in (
            "jp_mhlw_guidance", "fr_has_guidance", "br_moh_guidance", "au_health_guidance",
            "nz_health_guidance", "il_moh_guidance", "ir_mohme_guidance", "za_ndoh_guidance",
        ):
            source = get_medical_knowledge_source(source_id)
            assert source is not None
            assert source["allowed_for_discovery"] is True
            assert source["allowed_for_answering_without_snapshot"] is False
            assert source["requires_document_level_usage_review"] is True


def test_owner_global_coverage_exposes_continent_summary(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    response = client.get("/owner/data/global-coverage")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["continents"]["Asia"]["jurisdiction_count"] == 48
    assert payload["continents"]["Europe"]["jurisdiction_count"] == 44
    assert payload["continents"]["Oceania"]["jurisdiction_count"] == 14
    assert payload["continents"]["Africa"]["jurisdiction_count"] >= 10
    assert continent_coverage_summary()["Asia"]["jurisdiction_count"] == 48
