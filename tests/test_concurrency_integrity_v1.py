from __future__ import annotations

import pytest

from zendoc.db import get_db, is_integrity_error, now_iso
from zendoc.prescription_service import create_prescription
from zendoc.provider_service import book_provider_slot, create_schedule
from tests.test_milestone1 import csrf, login_web, make_app, register_web
from tests.test_milestone7 import api_token


def _user(app, email):
    with app.app_context():
        return dict(
            get_db().execute(
                "SELECT * FROM users WHERE email_normalized=?",
                (email.lower(),),
            ).fetchone()
        )


def test_appointment_slot_claim_primary_key_blocks_duplicate_claim(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "doctor", "claim-doctor@example.com", "Claim Doctor")
    doctor = _user(app, "claim-doctor@example.com")

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO appointment_slot_claims
            (provider_id, slot_key, appointment_id, created_at)
            VALUES (?, '2026-12-30T10:00', NULL, ?)
            """,
            (doctor["id"], now_iso()),
        )
        with pytest.raises(Exception) as exc:
            db.execute(
                """
                INSERT INTO appointment_slot_claims
                (provider_id, slot_key, appointment_id, created_at)
                VALUES (?, '2026-12-30T10:00', NULL, ?)
                """,
                (doctor["id"], now_iso()),
            )
        assert is_integrity_error(exc.value)
        db.rollback()


def test_cancelled_connected_appointment_releases_slot_claim(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "claim-patient@example.com", "Claim Patient")
    register_web(client, "doctor", "claim-provider@example.com", "Claim Provider")
    patient = _user(app, "claim-patient@example.com")
    doctor = _user(app, "claim-provider@example.com")

    with app.app_context():
        db = get_db()
        now = now_iso()
        profile_id = db.execute(
            """
            INSERT INTO provider_profiles
            (user_id,provider_type,specialty,organization,verification_status,created_at,updated_at)
            VALUES (?, 'doctor','General','Claim Clinic','verified',?,?)
            """,
            (doctor["id"], now, now),
        ).lastrowid
        create_schedule(
            doctor,
            {
                "weekday": 2,
                "start_time": "10:00",
                "end_time": "11:00",
                "slot_minutes": 30,
            },
        )
        db.commit()

        appointment_id = db.execute(
            """
            INSERT INTO appointments
            (patient_id,provider_id,provider_profile_id,provider_name,scheduled_for,reason,status,created_at,updated_at)
            VALUES (?,?,?,'Claim Provider','2026-12-30T10:00','Test','requested',?,?)
            """,
            (patient["id"], doctor["id"], profile_id, now, now),
        ).lastrowid
        db.execute(
            """
            INSERT INTO appointment_slot_claims
            (provider_id,slot_key,appointment_id,created_at)
            VALUES (?,?,?,?)
            """,
            (doctor["id"], "2026-12-30T10:00", appointment_id, now),
        )
        db.commit()

    login_web(client, "doctor", "claim-provider@example.com")
    page = client.get("/appointments")
    token = csrf(page.data.decode())
    response = client.post(
        f"/appointments/{appointment_id}/status",
        data={"csrf_token": token, "status": "cancelled"},
        follow_redirects=False,
    )
    assert response.status_code in {302, 303}

    with app.app_context():
        claim = get_db().execute(
            "SELECT 1 FROM appointment_slot_claims WHERE appointment_id=?",
            (appointment_id,),
        ).fetchone()
        assert claim is None


def test_nullable_request_fingerprints_are_unique_when_present(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    api_token(client, "fingerprint-patient@example.com")
    register_web(client, "doctor", "fingerprint-doctor@example.com", "Fingerprint Doctor")
    patient = _user(app, "fingerprint-patient@example.com")
    doctor = _user(app, "fingerprint-doctor@example.com")

    with app.app_context():
        db = get_db()
        now = now_iso()
        db.execute(
            """
            INSERT INTO consultation_requests
            (patient_id,doctor_id,consultation_type,status,reason,request_fingerprint,created_at,updated_at)
            VALUES (?,?,'chat','requested','Retry','same-fingerprint',?,?)
            """,
            (patient["id"], doctor["id"], now, now),
        )
        with pytest.raises(Exception) as exc:
            db.execute(
                """
                INSERT INTO consultation_requests
                (patient_id,doctor_id,consultation_type,status,reason,request_fingerprint,created_at,updated_at)
                VALUES (?,?,'chat','requested','Retry','same-fingerprint',?,?)
                """,
                (patient["id"], doctor["id"], now, now),
            )
        assert is_integrity_error(exc.value)
        db.rollback()


def test_prescription_uids_do_not_depend_on_row_count(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    api_token(client, "uid-patient@example.com")
    patient = _user(app, "uid-patient@example.com")

    with app.app_context():
        first = create_prescription(
            patient_id=patient["id"],
            prescriber_name="Existing Prescription",
            items=[{"medicine_name": "Medicine A", "extraction_confidence": 0.5}],
            source="USER_REPORTED",
        )
        second = create_prescription(
            patient_id=patient["id"],
            prescriber_name="Existing Prescription",
            items=[{"medicine_name": "Medicine B", "extraction_confidence": 0.5}],
            source="USER_REPORTED",
        )
        assert first["prescription_uid"] != second["prescription_uid"]
        assert first["prescription_uid"].startswith(f"rx_{patient['id']}_")
        assert second["prescription_uid"].startswith(f"rx_{patient['id']}_")


def test_concurrency_migration_is_additive_and_repeatable(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        versions = {
            row["version"]
            for row in db.execute(
                """
                SELECT version FROM schema_migrations
                WHERE version IN (
                    'post_submission_concurrency_v1',
                    'post_submission_request_fingerprints_v1'
                )
                """
            ).fetchall()
        }
        assert versions == {
            "post_submission_concurrency_v1",
            "post_submission_request_fingerprints_v1",
        }

        columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(consultation_requests)").fetchall()
        }
        assert "request_fingerprint" in columns
