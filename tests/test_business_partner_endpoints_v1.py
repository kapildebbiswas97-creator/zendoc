from datetime import datetime, timedelta, timezone

from zendoc.business_api import create_business_api_client, issue_business_api_key
from zendoc.db import get_db
from zendoc.public_data_ingestion import ingest_public_records
from tests.test_milestone1 import make_app, make_client


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def test_partner_public_directory_requires_scope_and_returns_public_only(tmp_path):
    app, client = make_client(tmp_path)
    with app.app_context():
        ingest_public_records(
            owner_actor(),
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
            records=[
                {
                    "source_record_id": "PARTNER-HOSP-1",
                    "category": "hospital",
                    "name": "Partner Directory Hospital",
                    "state": "West Bengal",
                    "district": "Nadia",
                    "public_phone": "1234567890",
                }
            ],
            dry_run=False,
        )
        partner = create_business_api_client(
            owner_actor(),
            {
                "name": "Directory Partner",
                "client_type": "hospital",
                "allowed_scopes": ["public_directory.read"],
            },
        )
        key = issue_business_api_key(owner_actor(), partner["id"], expires_in_days=30)

    allowed = client.get(
        "/api/v1/business/public-directory?category=hospital&location=Nadia",
        headers={"X-ZENDOC-Partner-Key": key["api_key"]},
    )
    assert allowed.status_code == 200
    payload = allowed.get_json()
    assert payload["patient_data_access"] is False
    assert payload["count"] == 1
    record = payload["results"][0]
    assert record["name"] == "Partner Directory Hospital"
    assert "patient_id" not in record
    assert "medical_history" not in record
    assert "prescription" not in record

    with app.app_context():
        limited = create_business_api_client(
            owner_actor(),
            {
                "name": "Wrong Scope Partner",
                "client_type": "ngo",
                "allowed_scopes": ["pilot_metrics.read"],
            },
        )
        limited_key = issue_business_api_key(owner_actor(), limited["id"], expires_in_days=30)

    denied = client.get(
        "/api/v1/business/public-directory?category=hospital",
        headers={"X-ZENDOC-Partner-Key": limited_key["api_key"]},
    )
    assert denied.status_code == 401


def test_partner_provider_availability_exposes_slots_without_patient_identity(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    with app.app_context():
        db = get_db()
        now = "2026-09-08T00:00:00+00:00"
        provider_user = db.execute(
            """
            INSERT INTO users
            (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
            VALUES (?,?,?,?,?,1,?,?)
            """,
            ("Dr Partner", "partner-doctor@example.com", "partner-doctor@example.com", "x", "doctor", now, now),
        ).lastrowid
        profile_id = db.execute(
            """
            INSERT INTO provider_profiles
            (user_id,provider_type,specialty,qualifications,license_identifier,organization,address,city,state,
             postal_code,public_phone,verification_status,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,'verified',?,?)
            """,
            (
                provider_user, "doctor", "Cardiology", "MBBS", "REG-PARTNER", "Partner Clinic",
                "1 Road", "Kalyani", "West Bengal", "741235", "1234567890", now, now,
            ),
        ).lastrowid

        target_date = (datetime.now(timezone.utc).date() + timedelta(days=1))
        weekday = target_date.weekday()
        db.execute(
            """
            INSERT INTO provider_schedules
            (provider_profile_id,weekday,start_time,end_time,slot_minutes,active,created_at,updated_at)
            VALUES (?,?,'09:00','10:00',30,1,?,?)
            """,
            (profile_id, weekday, now, now),
        )
        partner = create_business_api_client(
            owner_actor(),
            {
                "name": "Availability Partner",
                "client_type": "employer",
                "allowed_scopes": ["provider_availability.read"],
            },
        )
        key = issue_business_api_key(owner_actor(), partner["id"], expires_in_days=30)
        db.commit()

    response = client.get(
        f"/api/v1/business/providers/{profile_id}/availability?date={target_date.isoformat()}",
        headers={"X-ZENDOC-Partner-Key": key["api_key"]},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["patient_data_access"] is False
    assert payload["provider"]["verification_status"] == "verified"
    assert isinstance(payload["available_slots"], list)
    assert "patient" not in payload["provider"]
    assert "patient_id" not in payload
