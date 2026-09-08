from zendoc.db import get_db
from zendoc.geography_graph import list_entities_for_geography, upsert_geography_node
from zendoc.public_data_ingestion import ingest_public_records
from tests.test_milestone1 import make_app


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def canonical_district():
    country = upsert_geography_node(
        node_type="country",
        name="India",
        source="lgd",
        source_ref="country:IN",
        verified=True,
    )
    state = upsert_geography_node(
        node_type="state",
        name="West Bengal",
        parent_id=country["id"],
        source="lgd",
        source_ref="state:19",
        verified=True,
    )
    return upsert_geography_node(
        node_type="district",
        name="Nadia",
        parent_id=state["id"],
        source="lgd",
        source_ref="district:320",
        verified=True,
    )


def test_public_facility_ingestion_links_canonical_geography_and_reports_idempotency(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        district = canonical_district()

        hospital = {
            "source_record_id": "HOSP-001",
            "category": "hospital",
            "name": "Pilot District Hospital",
            "district": "Nadia",
            "state": "West Bengal",
            "geography_source": "lgd",
            "geography_source_record_id": "district:320",
            "metadata": {"facility_level": "district_hospital"},
        }
        first = ingest_public_records(
            owner_actor(),
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
            records=[hospital],
            dry_run=False,
        )
        assert first["applied"]["inserted_count"] == 1
        assert first["applied"]["updated_count"] == 0
        assert first["applied"]["unchanged_count"] == 0
        assert first["applied"]["geography_linked_count"] == 1

        # A different batch checksum causes the importer to evaluate the
        # existing hospital again; it must be unchanged while the PHC inserts.
        phc = {
            "source_record_id": "PHC-001",
            "category": "health_centre",
            "name": "Pilot PHC",
            "district": "Nadia",
            "state": "West Bengal",
            "geography_source": "lgd",
            "geography_source_record_id": "district:320",
            "metadata": {"facility_level": "PHC"},
        }
        second = ingest_public_records(
            owner_actor(),
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
            records=[hospital, phc],
            dry_run=False,
        )
        assert second["applied"]["inserted_count"] == 1
        assert second["applied"]["unchanged_count"] == 1
        assert second["applied"]["updated_count"] == 0
        assert second["applied"]["geography_linked_count"] == 2

        rows = get_db().execute(
            "SELECT source_record_id FROM public_healthcare_entities ORDER BY source_record_id"
        ).fetchall()
        assert [row["source_record_id"] for row in rows] == ["HOSP-001", "PHC-001"]

        links = list_entities_for_geography(district["id"])
        linked_entity_ids = {str(item["entity_id"]) for item in links}
        entity_rows = get_db().execute(
            "SELECT id FROM public_healthcare_entities"
        ).fetchall()
        assert {str(row["id"]) for row in entity_rows} <= linked_entity_ids


def test_public_facility_with_explicit_unknown_canonical_geography_is_rejected(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        result = ingest_public_records(
            owner_actor(),
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
            records=[
                {
                    "source_record_id": "LAB-404",
                    "category": "laboratory",
                    "name": "Unknown Geography Lab",
                    "geography_source": "lgd",
                    "geography_source_record_id": "district:DOES-NOT-EXIST",
                }
            ],
            dry_run=False,
        )

        assert result["accepted_count"] == 0
        assert result["rejected_count"] == 1
        assert result["applied"]["applied"] == []
        assert "canonical geography not found" in result["applied"]["rejected_during_apply"][0]["reason"]
        assert get_db().execute(
            "SELECT id FROM public_healthcare_entities WHERE source_record_id='LAB-404'"
        ).fetchone() is None


def test_public_facility_updates_existing_source_identity_without_duplication(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        canonical_district()
        original = {
            "source_record_id": "PHARM-001",
            "category": "pharmacy",
            "name": "Pilot Pharmacy",
            "district": "Nadia",
            "state": "West Bengal",
            "geography_source": "lgd",
            "geography_source_record_id": "district:320",
        }
        ingest_public_records(
            owner_actor(),
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
            records=[original],
            dry_run=False,
        )

        changed = dict(original)
        changed["name"] = "Pilot Pharmacy Updated"
        changed["public_phone"] = "1234567890"
        result = ingest_public_records(
            owner_actor(),
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
            records=[changed],
            dry_run=False,
        )

        assert result["applied"]["updated_count"] == 1
        assert result["applied"]["inserted_count"] == 0
        rows = get_db().execute(
            "SELECT id,name,public_phone FROM public_healthcare_entities WHERE source_record_id='PHARM-001'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["name"] == "Pilot Pharmacy Updated"
        assert rows[0]["public_phone"] == "1234567890"
