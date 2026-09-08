import hashlib

from zendoc.db import get_db
from zendoc.geography_graph import link_entity_to_geography, upsert_geography_node
from zendoc.public_data_ingestion import ingest_public_records
from zendoc.startup_analytics import india_coverage_quality, record_finder_search, startup_metrics
from tests.test_milestone1 import make_app, make_client


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def test_finder_analytics_store_no_raw_free_text_location(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        user = {"id": 42}
        raw_location = "Some Private Free Text Location"
        record_finder_search(
            user,
            category="hospital",
            location=raw_location,
            result_count=0,
            source_tiers={},
        )
        get_db().commit()

        row = get_db().execute(
            "SELECT * FROM product_analytics_events ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row["location_hash"] == hashlib.sha256(raw_location.casefold().encode("utf-8")).hexdigest()[:32]
        assert raw_location not in str(dict(row))


def test_startup_metrics_report_useful_no_result_and_repeat_search_users(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        record_finder_search({"id": 10}, category="hospital", location="", result_count=3, source_tiers={"zendoc_verified": 1})
        record_finder_search({"id": 10}, category="pharmacy", location="", result_count=0, source_tiers={})
        record_finder_search({"id": 11}, category="doctor", location="", result_count=1, source_tiers={"official_public_directory_not_zendoc_verified": 1})
        get_db().commit()

        metrics = startup_metrics(owner_actor(), days=30)
        assert metrics["healthcare_searches"] == 3
        assert metrics["useful_searches"] == 2
        assert metrics["no_result_searches"] == 1
        assert metrics["active_search_users"] == 2
        assert metrics["repeat_search_users"] == 1
        assert metrics["useful_result_rate"] == 0.6667


def test_india_coverage_quality_counts_only_present_data_and_never_invents_percentage(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
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
        district = upsert_geography_node(
            node_type="district",
            name="Nadia",
            parent_id=state["id"],
            source="lgd",
            source_ref="district:320",
            verified=True,
        )
        ingest = ingest_public_records(
            owner_actor(),
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
            records=[
                {
                    "source_record_id": "HOSP-COV-1",
                    "category": "hospital",
                    "name": "Coverage Hospital",
                    "state": "West Bengal",
                    "district": "Nadia",
                    "geography_source": "lgd",
                    "geography_source_record_id": "district:320",
                }
            ],
            dry_run=False,
        )
        assert ingest["applied"]["geography_linked_count"] == 1

        coverage = india_coverage_quality(owner_actor())
        assert coverage["region_target_count"] == 36
        assert coverage["canonical_state_nodes_loaded"] == 1
        assert coverage["public_healthcare_entity_count"] == 1
        assert coverage["public_healthcare_entities_linked_to_canonical_geography"] == 1
        assert "coverage_percentage" not in coverage

        wb = next(item for item in coverage["regions"] if item["slug"] == "west_bengal")
        assert wb["geography_counts"]["district"] == 1
        assert wb["linked_public_facility_counts"]["hospital"] == 1


def test_startup_owner_apis_are_protected(tmp_path):
    _app, client = make_client(tmp_path)

    denied_metrics = client.get("/api/v1/admin/startup/metrics")
    denied_coverage = client.get("/api/v1/admin/startup/india-coverage")
    assert denied_metrics.status_code in {302, 401, 403}
    assert denied_coverage.status_code in {302, 401, 403}

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminStrong123"},
    )
    token = login.get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    metrics = client.get("/api/v1/admin/startup/metrics", headers=headers)
    coverage = client.get("/api/v1/admin/startup/india-coverage", headers=headers)
    assert metrics.status_code == 200
    assert coverage.status_code == 200
    assert coverage.get_json()["coverage"]["region_target_count"] == 36
