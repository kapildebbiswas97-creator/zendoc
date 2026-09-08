import json
from datetime import datetime, timedelta, timezone

from zendoc.data_freshness import ingestion_freshness_report
from zendoc.db import get_db
from tests.test_milestone1 import make_app, make_client


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def insert_completed_batch(db, *, source_id, completed_at, unresolved=0, ambiguous=0, rejected=0):
    summary = {
        "geography_linked_count": 5,
        "geography_unresolved_count": unresolved,
        "geography_ambiguous_count": ambiguous,
    }
    db.execute(
        """
        INSERT INTO data_ingestion_batches
        (batch_uid,source_id,ingestion_type,checksum_sha256,record_count,accepted_count,rejected_count,
         dry_run,status,requested_by,summary_json,created_at,completed_at)
        VALUES (?,?,?,?,10,5,?,0,'completed',1,?,?,?)
        """,
        (
            f"batch-{source_id}-{completed_at}",
            source_id,
            "public_healthcare_entities",
            f"sha-{source_id}-{completed_at}",
            rejected,
            json.dumps(summary),
            completed_at,
            completed_at,
        ),
    )


def test_freshness_report_distinguishes_recent_stale_never_and_reference_only(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        now = datetime.now(timezone.utc)
        insert_completed_batch(
            db,
            source_id="data_gov_hospitals",
            completed_at=(now - timedelta(days=5)).isoformat(timespec="seconds"),
        )
        insert_completed_batch(
            db,
            source_id="clinical_establishments",
            completed_at=(now - timedelta(days=120)).isoformat(timespec="seconds"),
        )
        db.commit()

        report = ingestion_freshness_report(owner_actor())
        rows = {item["source_id"]: item for item in report["sources"]}

        assert rows["data_gov_hospitals"]["freshness_status"] == "recent"
        assert rows["clinical_establishments"]["freshness_status"] == "stale"
        assert rows["lgd"]["freshness_status"] == "never_ingested"
        assert rows["abdm_hpr"]["freshness_status"] == "reference_only"
        assert rows["data_gov_hospitals"]["refresh_priority"] == "P2"
        assert rows["clinical_establishments"]["refresh_priority"] == "P0"


def test_freshness_quality_issue_escalates_recent_source_to_p1(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        insert_completed_batch(
            db,
            source_id="data_gov_hospitals",
            completed_at=now,
            unresolved=3,
            ambiguous=1,
            rejected=2,
        )
        db.commit()

        report = ingestion_freshness_report(owner_actor())
        row = next(item for item in report["sources"] if item["source_id"] == "data_gov_hospitals")
        assert row["freshness_status"] == "recent"
        assert row["refresh_priority"] == "P1"
        assert row["latest_geography_unresolved_count"] == 3
        assert row["latest_geography_ambiguous_count"] == 1
        assert row["last_rejected_count"] == 2


def test_data_freshness_dashboard_and_api_are_owner_only(tmp_path):
    _app, client = make_client(tmp_path)

    assert client.get("/admin/startup/data-freshness").status_code in {302, 401, 403}
    assert client.get("/api/v1/admin/ingestion/freshness").status_code in {302, 401, 403}

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminStrong123"},
    )
    token = login.get_json()["token"]
    response = client.get(
        "/api/v1/admin/ingestion/freshness",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert "freshness" in response.get_json()
