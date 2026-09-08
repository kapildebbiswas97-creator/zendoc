from zendoc.public_data_ingestion import ingest_public_records, search_public_healthcare_entities
from tests.test_milestone1 import make_app


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def ingest(source_id, record):
    return ingest_public_records(
        owner_actor(),
        source_id=source_id,
        ingestion_type="public_healthcare_entities",
        records=[record],
        dry_run=False,
    )


def test_exact_cross_source_duplicate_collapses_and_preserves_provenance(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        base = {
            "category": "hospital",
            "name": "Nadia General Hospital",
            "address": "1 Station Road",
            "city": "Kalyani",
            "district": "Nadia",
            "state": "West Bengal",
            "postal_code": "741235",
            "freshness_at": "2026-09-01T00:00:00+00:00",
        }
        ingest("data_gov_hospitals", {**base, "source_record_id": "DGH-1"})
        ingest("clinical_establishments", {**base, "source_record_id": "CE-1"})

        results = search_public_healthcare_entities(
            category="hospital",
            location="Nadia",
            limit=25,
        )
        matches = [item for item in results if item["name"] == "Nadia General Hospital"]
        assert len(matches) == 1
        item = matches[0]
        assert item["cross_source_deduplicated"] is True
        assert item["duplicate_source_count"] == 2
        assert {source["source_id"] for source in item["provenance_sources"]} == {
            "data_gov_hospitals",
            "clinical_establishments",
        }
        assert item["dedupe_method"] == "EXACT_NAME_AND_STRONG_LOCATION"


def test_same_name_different_postal_code_remains_separate(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        common = {
            "category": "hospital",
            "name": "City Care Hospital",
            "city": "Kolkata",
            "district": "Kolkata",
            "state": "West Bengal",
        }
        ingest(
            "data_gov_hospitals",
            {
                **common,
                "source_record_id": "CITY-A",
                "address": "1 North Road",
                "postal_code": "700001",
            },
        )
        ingest(
            "clinical_establishments",
            {
                **common,
                "source_record_id": "CITY-B",
                "address": "99 South Road",
                "postal_code": "700099",
            },
        )

        results = search_public_healthcare_entities(
            category="hospital",
            location="Kolkata",
            limit=25,
        )
        matches = [item for item in results if item["name"] == "City Care Hospital"]
        assert len(matches) == 2
        assert all(item["duplicate_source_count"] == 1 for item in matches)


def test_authoritative_registry_wins_primary_record_but_keeps_other_source(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        common = {
            "category": "hospital",
            "name": "Authority Hospital",
            "address": "5 Registry Lane",
            "city": "Delhi",
            "district": "New Delhi",
            "state": "Delhi",
            "postal_code": "110001",
        }
        ingest(
            "data_gov_hospitals",
            {
                **common,
                "source_record_id": "OGD-AUTH",
                "freshness_at": "2026-09-08T00:00:00+00:00",
            },
        )
        ingest(
            "abdm_hfr",
            {
                **common,
                "source_record_id": "HFR-AUTH",
                "freshness_at": "2026-08-01T00:00:00+00:00",
            },
        )

        results = search_public_healthcare_entities(
            category="hospital",
            location="Delhi",
            limit=25,
        )
        item = next(result for result in results if result["name"] == "Authority Hospital")
        assert item["source_id"] == "abdm_hfr"
        assert item["source_trust"] == "AUTHORITATIVE_REGISTRY"
        assert item["duplicate_source_count"] == 2


def test_newer_freshness_wins_when_trust_level_is_equal(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        common = {
            "category": "hospital",
            "name": "Freshness Hospital",
            "address": "10 Fresh Road",
            "city": "Kalyani",
            "district": "Nadia",
            "state": "West Bengal",
            "postal_code": "741235",
        }
        ingest(
            "data_gov_hospitals",
            {
                **common,
                "source_record_id": "FRESH-OLD",
                "freshness_at": "2026-07-01T00:00:00+00:00",
            },
        )
        ingest(
            "clinical_establishments",
            {
                **common,
                "source_record_id": "FRESH-NEW",
                "freshness_at": "2026-09-05T00:00:00+00:00",
            },
        )

        results = search_public_healthcare_entities(
            category="hospital",
            location="Nadia",
            limit=25,
        )
        item = next(result for result in results if result["name"] == "Freshness Hospital")
        assert item["source_id"] == "clinical_establishments"
        assert item["freshness_at"] == "2026-09-05T00:00:00+00:00"
        assert item["duplicate_source_count"] == 2
