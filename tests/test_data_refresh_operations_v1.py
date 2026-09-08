from zendoc.data_refresh import (
    create_data_refresh_task,
    data_refresh_operations,
    update_data_refresh_task,
)
from zendoc.db import get_db
from zendoc.public_data_ingestion import ingest_public_records
from tests.test_milestone1 import make_app, make_client


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def test_p0_refresh_task_is_idempotent_and_requires_real_batch_for_completion(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        first = create_data_refresh_task(
            owner_actor(),
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
            owner_note="Initial P0 refresh.",
        )
        second = create_data_refresh_task(
            owner_actor(),
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
        )
        assert first["id"] == second["id"]
        assert first["priority"] == "P0"
        assert first["status"] == "queued"

        failed = False
        try:
            update_data_refresh_task(
                owner_actor(),
                first["id"],
                status="completed",
            )
        except ValueError:
            failed = True
        assert failed is True

        update_data_refresh_task(
            owner_actor(),
            first["id"],
            status="in_progress",
        )

        ingest_public_records(
            owner_actor(),
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
            records=[{
                "source_record_id": "REFRESH-REAL-1",
                "category": "hospital",
                "name": "Refresh Proof Hospital",
                "address": "1 Refresh Road",
                "city": "Kalyani",
                "district": "Nadia",
                "state": "West Bengal",
                "postal_code": "741235",
            }],
            dry_run=False,
        )
        batch_id = int(
            get_db().execute(
                """
                SELECT id FROM data_ingestion_batches
                WHERE source_id='data_gov_hospitals'
                  AND ingestion_type='public_healthcare_entities'
                  AND dry_run=0 AND status='completed'
                ORDER BY id DESC LIMIT 1
                """
            ).fetchone()["id"]
        )

        completed = update_data_refresh_task(
            owner_actor(),
            first["id"],
            status="completed",
            linked_batch_id=batch_id,
        )
        assert completed["status"] == "completed"
        assert completed["linked_batch_id"] == batch_id
        assert completed["batch_status"] == "completed"
        assert completed["completed_at"] is not None


def test_refresh_task_rejects_wrong_batch_and_reference_only_source(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        task = create_data_refresh_task(
            owner_actor(),
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
        )

        ingest_public_records(
            owner_actor(),
            source_id="clinical_establishments",
            ingestion_type="public_healthcare_entities",
            records=[{
                "source_record_id": "WRONG-BATCH-1",
                "category": "hospital",
                "name": "Wrong Batch Hospital",
                "address": "2 Road",
                "city": "Kalyani",
                "district": "Nadia",
                "state": "West Bengal",
                "postal_code": "741235",
            }],
            dry_run=False,
        )
        wrong_batch_id = int(
            get_db().execute(
                "SELECT id FROM data_ingestion_batches WHERE source_id='clinical_establishments' ORDER BY id DESC LIMIT 1"
            ).fetchone()["id"]
        )

        failed = False
        try:
            update_data_refresh_task(
                owner_actor(),
                task["id"],
                status="completed",
                linked_batch_id=wrong_batch_id,
            )
        except ValueError:
            failed = True
        assert failed is True

        reference_only_failed = False
        try:
            create_data_refresh_task(
                owner_actor(),
                source_id="abdm_hpr",
            )
        except ValueError:
            reference_only_failed = True
        assert reference_only_failed is True


def test_blocked_refresh_task_requires_reason_and_can_resume(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        task = create_data_refresh_task(
            owner_actor(),
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
        )

        missing_reason = False
        try:
            update_data_refresh_task(owner_actor(), task["id"], status="blocked")
        except ValueError:
            missing_reason = True
        assert missing_reason is True

        blocked = update_data_refresh_task(
            owner_actor(),
            task["id"],
            status="blocked",
            blocked_reason="Official source export is temporarily unavailable.",
        )
        assert blocked["status"] == "blocked"
        assert blocked["blocked_reason"]

        resumed = update_data_refresh_task(
            owner_actor(),
            task["id"],
            status="in_progress",
        )
        assert resumed["status"] == "in_progress"


def test_data_refresh_operations_exposes_only_observed_urgent_sources(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        operations = data_refresh_operations(owner_actor())
        assert operations["urgent_source_count"] > 0
        assert all(
            source["refresh_priority"] in {"P0", "P1"}
            for source in operations["urgent_sources"]
        )
        assert all(
            source["freshness_status"] != "reference_only"
            or not source["ingestion_types"]
            for source in operations["urgent_sources"]
        )
        assert "completed non-dry-run" in operations["truth_notice"]


def test_data_refresh_operations_api_is_owner_only(tmp_path):
    _app, client = make_client(tmp_path)

    denied = client.get("/api/v1/admin/ingestion/refresh-operations")
    assert denied.status_code in {302, 401, 403}

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminStrong123"},
    )
    token = login.get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get(
        "/api/v1/admin/ingestion/refresh-operations",
        headers=headers,
    )
    assert response.status_code == 200
    assert "refresh_operations" in response.get_json()
