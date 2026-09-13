from datetime import datetime, timedelta, timezone

import pytest

from zendoc.db import get_db, now_iso
from zendoc.diagnostic_service import book_diagnostic_test
from zendoc.home_health import create_home_health_request
from zendoc.operational_fulfilment import (
    assign_home_health_provider,
    publish_home_health_service,
    update_diagnostic_booking_status,
)
from zendoc.operational_fulfilment_release import (
    link_diagnostic_report,
    list_diagnostic_provider_requests,
    list_my_home_health_capabilities,
    list_patient_diagnostic_requests,
    list_patient_home_health_requests,
)
from tests.test_milestone1 import make_app


def _user(db, name, email, role):
    now = now_iso()
    return int(
        db.execute(
            """
            INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
            VALUES (?,?,?,?,?,1,?,?)
            """,
            (name, email, email, "test-hash", role, now, now),
        ).lastrowid
    )


def _verify_provider(db, provider_id, provider_type, city="Kolkata"):
    now = now_iso()
    db.execute(
        """
        INSERT INTO provider_profiles
        (user_id,provider_type,organization,city,verification_status,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (provider_id, provider_type, "Verified Care Provider", city, "verified", now, now),
    )
    db.commit()


def _diagnostic_booking(app, patient_id, lab_id):
    with app.app_context():
        db = get_db()
        test = db.execute("SELECT id FROM diagnostic_catalog ORDER BY id LIMIT 1").fetchone()
        assert test is not None
        now = now_iso()
        db.execute(
            """
            INSERT INTO diagnostic_offers
            (lab_id,test_id,price_inr,home_collection_available,home_collection_fee_inr,
             verified,data_mode,observed_at,created_at)
            VALUES (?,?,?,?,?,1,'LIVE',?,?)
            """,
            (lab_id, int(test["id"]), 500.0, 1, 50.0, now, now),
        )
        db.commit()
        future = (datetime.now(timezone.utc).date() + timedelta(days=2)).isoformat()
        booking = book_diagnostic_test(
            actor={"id": patient_id, "role": "patient"},
            patient_id=patient_id,
            test_id=int(test["id"]),
            lab_id=lab_id,
            scheduled_date=future,
            address="10 Health Road, Kolkata",
            collection_type="home_collection",
            slot_time="09:00-11:00",
            user_confirmed=True,
            data_mode="LIVE",
        )
        return int(booking["booking_id"])


def test_diagnostic_provider_and_patient_work_queues_are_scoped(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = _user(db, "Patient", "release-patient@example.com", "patient")
        lab_id = _user(db, "Assigned Lab", "release-lab@example.com", "hospital")
        other_lab_id = _user(db, "Other Lab", "release-other-lab@example.com", "hospital")
        _verify_provider(db, lab_id, "lab")
        _verify_provider(db, other_lab_id, "lab")

    booking_id = _diagnostic_booking(app, patient_id, lab_id)
    with app.app_context():
        lab_rows = list_diagnostic_provider_requests({"id": lab_id, "role": "hospital"})
        assert [int(row["id"]) for row in lab_rows] == [booking_id]
        assert list_diagnostic_provider_requests({"id": other_lab_id, "role": "hospital"}) == []
        patient_rows = list_patient_diagnostic_requests({"id": patient_id, "role": "patient"})
        assert [int(row["id"]) for row in patient_rows] == [booking_id]
        with pytest.raises(ValueError):
            list_diagnostic_provider_requests({"id": lab_id, "role": "hospital"}, "invented")


def test_completed_diagnostic_can_link_only_patient_owned_provider_uploaded_report(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = _user(db, "Report Patient", "report-patient@example.com", "patient")
        other_patient_id = _user(db, "Other Patient", "report-other-patient@example.com", "patient")
        lab_id = _user(db, "Report Lab", "report-lab@example.com", "hospital")
        _verify_provider(db, lab_id, "lab")

    booking_id = _diagnostic_booking(app, patient_id, lab_id)
    with app.app_context():
        db = get_db()
        lab = {"id": lab_id, "role": "hospital"}
        update_diagnostic_booking_status(lab, booking_id, "accepted")
        update_diagnostic_booking_status(lab, booking_id, "completed")
        now = now_iso()
        report_id = int(
            db.execute(
                """
                INSERT INTO medical_records
                (owner_id,uploaded_by,title,category,original_filename,stored_filename,mime_type,file_size,created_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (patient_id, lab_id, "CBC report", "diagnostic", "cbc.pdf", "release-cbc.pdf", "application/pdf", 100, now),
            ).lastrowid
        )
        wrong_patient_report_id = int(
            db.execute(
                """
                INSERT INTO medical_records
                (owner_id,uploaded_by,title,category,original_filename,stored_filename,mime_type,file_size,created_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (other_patient_id, lab_id, "Other report", "diagnostic", "other.pdf", "release-other.pdf", "application/pdf", 100, now),
            ).lastrowid
        )
        patient_uploaded_id = int(
            db.execute(
                """
                INSERT INTO medical_records
                (owner_id,uploaded_by,title,category,original_filename,stored_filename,mime_type,file_size,created_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (patient_id, patient_id, "Self upload", "diagnostic", "self.pdf", "release-self.pdf", "application/pdf", 100, now),
            ).lastrowid
        )
        db.commit()

        with pytest.raises(PermissionError):
            link_diagnostic_report(lab, booking_id, wrong_patient_report_id)
        with pytest.raises(PermissionError):
            link_diagnostic_report(lab, booking_id, patient_uploaded_id)

        linked = link_diagnostic_report(lab, booking_id, report_id)
        assert int(linked["report_record_id"]) == report_id
        assert linked["external_execution"] is False
        replay = link_diagnostic_report(lab, booking_id, report_id)
        assert replay["report_link_idempotent_replay"] is True


def test_home_health_capability_and_patient_queue_are_real_assignment_views(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = _user(db, "Home Patient", "release-home-patient@example.com", "patient")
        provider_id = _user(db, "Home Hospital", "release-home-provider@example.com", "hospital")
        _verify_provider(db, provider_id, "hospital")
        patient = {"id": patient_id, "role": "patient", "city": "Kolkata"}
        provider = {"id": provider_id, "role": "hospital"}
        capability = publish_home_health_service(provider, "physiotherapy")
        capabilities = list_my_home_health_capabilities(provider)
        assert [int(row["id"]) for row in capabilities] == [int(capability["id"])]

        request_row = create_home_health_request(
            patient,
            {
                "service_type": "physiotherapy",
                "scheduled_date": (datetime.now(timezone.utc).date() + timedelta(days=2)).isoformat(),
                "address": "44 Recovery Road",
                "city": "Kolkata",
            },
        )
        request_id = int(request_row["id"])
        before = list_patient_home_health_requests(patient)
        assert int(before[0]["id"]) == request_id
        assert before[0]["actually_integrated"] is False

        assign_home_health_provider(patient, request_id, provider_id)
        after = list_patient_home_health_requests(patient)
        assert int(after[0]["provider_id"]) == provider_id
        assert after[0]["actually_integrated"] is True
        assert after[0]["external_execution"] is False
