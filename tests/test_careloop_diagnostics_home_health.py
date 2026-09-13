from datetime import datetime, timedelta, timezone

import pytest

from zendoc.db import get_db, now_iso
from zendoc.diagnostic_service import book_diagnostic_test
from zendoc.home_health import create_home_health_request
from zendoc.operational_fulfilment import (
    assign_home_health_provider,
    ensure_diagnostic_careloop_link,
    get_diagnostic_booking,
    get_home_health_fulfilment,
    list_home_health_providers,
    publish_home_health_service,
    update_diagnostic_booking_status,
    update_home_health_request_status,
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


def _fresh_diagnostic_offer(db, lab_id):
    test = db.execute("SELECT id,name FROM diagnostic_catalog ORDER BY id LIMIT 1").fetchone()
    assert test is not None
    now = now_iso()
    db.execute(
        """
        INSERT INTO diagnostic_offers
        (lab_id,test_id,price_inr,home_collection_available,home_collection_fee_inr,
         verified,data_mode,observed_at,created_at)
        VALUES (?,?,?,?,?,1,'LIVE',?,?)
        """,
        (lab_id, int(test["id"]), 650.0, 1, 50.0, now, now),
    )
    db.commit()
    return int(test["id"]), str(test["name"])


def _diagnostic_booking(app, patient_id, lab_id):
    with app.app_context():
        db = get_db()
        test_id, _ = _fresh_diagnostic_offer(db, lab_id)
        future_date = (datetime.now(timezone.utc).date() + timedelta(days=3)).isoformat()
        booking = book_diagnostic_test(
            actor={"id": patient_id, "role": "patient"},
            patient_id=patient_id,
            test_id=test_id,
            lab_id=lab_id,
            scheduled_date=future_date,
            address="12 Care Street, Kolkata",
            collection_type="home_collection",
            slot_time="09:00-11:00",
            user_confirmed=True,
            data_mode="LIVE",
        )
        return int(booking["booking_id"])


def _care_action(db, service_ref):
    return db.execute(
        "SELECT * FROM care_actions WHERE service_ref=? ORDER BY id DESC LIMIT 1",
        (service_ref,),
    ).fetchone()


def test_verified_lab_diagnostic_lifecycle_links_and_syncs_careloop(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = _user(db, "Diagnostic Patient", "diag-loop-patient@example.com", "patient")
        lab_id = _user(db, "Diagnostic Lab", "diag-loop-lab@example.com", "hospital")
        _verify_provider(db, lab_id, "lab")

    booking_id = _diagnostic_booking(app, patient_id, lab_id)

    with app.app_context():
        db = get_db()
        patient = {"id": patient_id, "role": "patient"}
        lab = {"id": lab_id, "role": "hospital"}
        action_id = ensure_diagnostic_careloop_link(booking_id)
        assert action_id is not None
        action = _care_action(db, f"zendoc_diagnostic_booking:{booking_id}")
        assert action["status"] == "STAGED"
        assert action["provider_name"] == "Diagnostic Lab"

        accepted = update_diagnostic_booking_status(lab, booking_id, "accepted")
        assert accepted["status"] == "accepted"
        assert _care_action(db, f"zendoc_diagnostic_booking:{booking_id}")["status"] == "CONFIRMED"

        collected = update_diagnostic_booking_status(lab, booking_id, "sample_collected")
        assert collected["status"] == "sample_collected"
        assert _care_action(db, f"zendoc_diagnostic_booking:{booking_id}")["status"] == "IN_PROGRESS"

        processing = update_diagnostic_booking_status(lab, booking_id, "processing")
        assert processing["status"] == "processing"
        action = _care_action(db, f"zendoc_diagnostic_booking:{booking_id}")
        assert action["status"] == "IN_PROGRESS"
        progress_events = db.execute(
            "SELECT event_type FROM care_action_events WHERE action_id=? ORDER BY id",
            (int(action["id"]),),
        ).fetchall()
        assert "INTERNAL_DIAGNOSTIC_PROGRESS" in [row["event_type"] for row in progress_events]

        completed = update_diagnostic_booking_status(lab, booking_id, "completed", "Lab workflow completed in ZENDOC.")
        assert completed["status"] == "completed"
        assert completed["external_execution"] is False
        assert _care_action(db, f"zendoc_diagnostic_booking:{booking_id}")["status"] == "COMPLETED"

        patient_view = get_diagnostic_booking(patient, booking_id)
        assert "does not independently verify" in patient_view["truth_notice"].lower()
        patient_notifications = db.execute(
            "SELECT title,message FROM notifications WHERE user_id=? ORDER BY id",
            (patient_id,),
        ).fetchall()
        lab_notifications = db.execute(
            "SELECT title FROM notifications WHERE user_id=? ORDER BY id",
            (lab_id,),
        ).fetchall()
        assert [item["title"] for item in patient_notifications] == [
            "Diagnostic accepted",
            "Diagnostic sample collected",
            "Diagnostic processing",
            "Diagnostic completed",
        ]
        assert len(lab_notifications) == 4
        timeline_event = db.execute(
            "SELECT event_type,source_ref FROM health_timeline_events WHERE patient_id=? ORDER BY id DESC LIMIT 1",
            (patient_id,),
        ).fetchone()
        assert timeline_event["event_type"] == "DIAGNOSTIC_COMPLETED"
        assert timeline_event["source_ref"] == f"diagnostic:{booking_id}"


def test_diagnostic_idor_and_patient_advance_are_blocked(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = _user(db, "Secure Diagnostic Patient", "diag-secure-patient@example.com", "patient")
        lab_id = _user(db, "Assigned Diagnostic Lab", "diag-assigned-lab@example.com", "hospital")
        other_lab_id = _user(db, "Other Diagnostic Lab", "diag-other-lab@example.com", "hospital")
        _verify_provider(db, lab_id, "lab")
        _verify_provider(db, other_lab_id, "lab")

    booking_id = _diagnostic_booking(app, patient_id, lab_id)
    with app.app_context():
        db = get_db()
        ensure_diagnostic_careloop_link(booking_id)
        with pytest.raises(PermissionError):
            update_diagnostic_booking_status({"id": other_lab_id, "role": "hospital"}, booking_id, "accepted")
        with pytest.raises(PermissionError):
            update_diagnostic_booking_status({"id": patient_id, "role": "patient"}, booking_id, "accepted")
        assert db.execute("SELECT status FROM diagnostic_bookings WHERE id=?", (booking_id,)).fetchone()["status"] == "requested"
        assert _care_action(db, f"zendoc_diagnostic_booking:{booking_id}")["status"] == "STAGED"


def test_patient_can_cancel_diagnostic_without_claiming_provider_execution(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = _user(db, "Cancel Diagnostic Patient", "diag-cancel-patient@example.com", "patient")
        lab_id = _user(db, "Cancel Diagnostic Lab", "diag-cancel-lab@example.com", "hospital")
        _verify_provider(db, lab_id, "lab")

    booking_id = _diagnostic_booking(app, patient_id, lab_id)
    with app.app_context():
        db = get_db()
        ensure_diagnostic_careloop_link(booking_id)
        result = update_diagnostic_booking_status({"id": patient_id, "role": "patient"}, booking_id, "cancelled")
        assert result["status"] == "cancelled"
        assert result["external_execution"] is False
        assert _care_action(db, f"zendoc_diagnostic_booking:{booking_id}")["status"] == "CANCELLED"


def test_home_health_requires_explicit_verified_provider_capability(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = _user(db, "Home Patient", "home-patient@example.com", "patient")
        provider_id = _user(db, "Home Care Hospital", "home-hospital@example.com", "hospital")
        _verify_provider(db, provider_id, "hospital", "Kolkata")
        patient = {"id": patient_id, "role": "patient", "city": "Kolkata"}
        request_row = create_home_health_request(
            patient,
            {
                "service_type": "physiotherapy",
                "scheduled_date": (datetime.now(timezone.utc).date() + timedelta(days=2)).isoformat(),
                "address": "22 Recovery Road",
                "city": "Kolkata",
            },
        )

        assert list_home_health_providers("physiotherapy", "Kolkata") == []
        with pytest.raises(ValueError):
            assign_home_health_provider(patient, int(request_row["id"]), provider_id)

        listing = publish_home_health_service({"id": provider_id, "role": "hospital"}, "physiotherapy")
        assert listing["active"] == 1
        providers = list_home_health_providers("physiotherapy", "Kolkata")
        assert [int(item["provider_id"]) for item in providers] == [provider_id]

        assignment = assign_home_health_provider(patient, int(request_row["id"]), provider_id)
        assert int(assignment["provider_id"]) == provider_id
        assert db.execute(
            "SELECT COUNT(*) c FROM notifications WHERE user_id IN (?,?) AND title='Home-care provider assigned'",
            (patient_id, provider_id),
        ).fetchone()["c"] == 2
        action = _care_action(db, f"zendoc_home_health_request:{int(request_row['id'])}")
        assert action is not None
        assert action["status"] == "STAGED"


def test_home_health_provider_lifecycle_syncs_and_blocks_idor(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = _user(db, "Home Secure Patient", "home-secure-patient@example.com", "patient")
        provider_id = _user(db, "Assigned Home Hospital", "home-assigned@example.com", "hospital")
        other_id = _user(db, "Other Home Hospital", "home-other@example.com", "hospital")
        _verify_provider(db, provider_id, "hospital")
        _verify_provider(db, other_id, "hospital")
        patient = {"id": patient_id, "role": "patient", "city": "Kolkata"}
        provider = {"id": provider_id, "role": "hospital"}
        other = {"id": other_id, "role": "hospital"}
        publish_home_health_service(provider, "nurse_visit")
        publish_home_health_service(other, "nurse_visit")
        request_row = create_home_health_request(
            patient,
            {
                "service_type": "nurse_visit",
                "scheduled_date": (datetime.now(timezone.utc).date() + timedelta(days=2)).isoformat(),
                "address": "44 Nursing Lane",
                "city": "Kolkata",
            },
        )
        request_id = int(request_row["id"])
        assign_home_health_provider(patient, request_id, provider_id)

        with pytest.raises(PermissionError):
            update_home_health_request_status(other, request_id, "accepted")
        with pytest.raises(PermissionError):
            update_home_health_request_status(patient, request_id, "accepted")

        accepted = update_home_health_request_status(provider, request_id, "accepted")
        assert accepted["status"] == "accepted"
        assert _care_action(db, f"zendoc_home_health_request:{request_id}")["status"] == "CONFIRMED"

        progress = update_home_health_request_status(provider, request_id, "in_progress")
        assert progress["status"] == "in_progress"
        assert _care_action(db, f"zendoc_home_health_request:{request_id}")["status"] == "IN_PROGRESS"

        completed = update_home_health_request_status(provider, request_id, "completed")
        assert completed["status"] == "completed"
        assert completed["external_execution"] is False
        assert _care_action(db, f"zendoc_home_health_request:{request_id}")["status"] == "COMPLETED"

        patient_view = get_home_health_fulfilment(patient, request_id)
        assert patient_view["actually_integrated"] is True
        assert patient_view["external_execution"] is False
        assert "does not claim dispatch" in patient_view["truth_notice"].lower()


def test_home_health_patient_cancel_and_doctor_capability_boundary(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = _user(db, "Cancel Home Patient", "home-cancel-patient@example.com", "patient")
        doctor_id = _user(db, "Home Doctor", "home-doctor@example.com", "doctor")
        _verify_provider(db, doctor_id, "doctor")
        patient = {"id": patient_id, "role": "patient", "city": "Kolkata"}
        doctor = {"id": doctor_id, "role": "doctor"}

        with pytest.raises(PermissionError):
            publish_home_health_service(doctor, "physiotherapy")
        publish_home_health_service(doctor, "doctor_visit")

        request_row = create_home_health_request(
            patient,
            {
                "service_type": "doctor_visit",
                "scheduled_date": (datetime.now(timezone.utc).date() + timedelta(days=2)).isoformat(),
                "address": "55 Home Visit Street",
                "city": "Kolkata",
            },
        )
        request_id = int(request_row["id"])
        assign_home_health_provider(patient, request_id, doctor_id)
        cancelled = update_home_health_request_status(patient, request_id, "cancelled")
        assert cancelled["status"] == "cancelled"
        assert _care_action(db, f"zendoc_home_health_request:{request_id}")["status"] == "CANCELLED"
