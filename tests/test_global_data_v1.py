from zendoc.db import get_db
from zendoc.global_public_data import ingest_global_public_healthcare
from zendoc.global_source_registry import INDIA_ADMIN1, country_coverage_manifest
from zendoc.medical_knowledge_registry import get_medical_knowledge_source
from zendoc.public_source_registry import get_public_ingestion_source
from tests.test_milestone1 import login_web, make_app


def test_global_country_schema_and_source_install(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        public_columns = {row["name"] for row in get_db().execute("PRAGMA table_info(public_healthcare_entities)").fetchall()}
        provider_columns = {row["name"] for row in get_db().execute("PRAGMA table_info(provider_profiles)").fetchall()}
        inventory_columns = {row["name"] for row in get_db().execute("PRAGMA table_info(inventory_observations)").fetchall()}
        assert {"country_code", "country_name"}.issubset(public_columns)
        assert {"country_code", "country_name"}.issubset(provider_columns)
        assert "currency_code" in inventory_columns
        assert get_public_ingestion_source("us_cms_hospital_general") is not None
        assert get_public_ingestion_source("bd_dghs_facility_registry") is not None
        assert get_medical_knowledge_source("uk_nice_guidance") is not None
        assert get_medical_knowledge_source("sg_moh_guidance") is not None


def test_india_manifest_covers_all_states_and_union_territories():
    assert len(INDIA_ADMIN1) == 36
    coverage = {item["country_code"]: item for item in country_coverage_manifest()}
    assert coverage["IN"]["admin1_count"] == 36
    for code in ("IN", "SG", "GB", "US", "RU", "CN", "BD", "PK"):
        assert code in coverage


def test_global_import_keeps_public_listing_unverified_and_tags_country(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        owner = get_db().execute("SELECT * FROM users WHERE role='admin' AND active=1 ORDER BY id LIMIT 1").fetchone()
        records = [
            {
                "source_record_id": "sample-us-hospital-001",
                "category": "hospital",
                "name": "Sample Public Hospital",
                "address": "1 Example Street",
                "city": "Boston",
                "state": "MA",
                "postal_code": "02108",
                "freshness_at": "2026-09-01T00:00:00+00:00",
            }
        ]
        preview = ingest_global_public_healthcare(
            owner,
            source_id="us_cms_hospital_general",
            records=records,
            dry_run=True,
        )
        assert preview["dry_run"] is True
        assert preview["country_code"] == "US"

        applied = ingest_global_public_healthcare(
            owner,
            source_id="us_cms_hospital_general",
            records=records,
            dry_run=False,
        )
        assert applied["country_code"] == "US"
        row = get_db().execute(
            "SELECT * FROM public_healthcare_entities WHERE source_id=? AND source_record_id=?",
            ("us_cms_hospital_general", "sample-us-hospital-001"),
        ).fetchone()
        assert row["country_code"] == "US"
        assert row["country_name"] == "United States"
        assert row["zendoc_verification_status"] == "not_verified"
        assert row["booking_connectivity"] == "not_connected"


def test_global_coverage_endpoint_is_owner_only(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    anonymous = client.get("/owner/data/global-coverage", follow_redirects=False)
    assert anonymous.status_code == 302
    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    response = client.get("/owner/data/global-coverage")
    assert response.status_code == 200
    payload = response.get_json()
    countries = {item["country_code"]: item for item in payload["countries"]}
    assert countries["IN"]["admin1_count"] == 36
    assert "US" in countries
    assert "BD" in countries
