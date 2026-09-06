from __future__ import annotations

import pytest

from zendoc.db import get_db, now_iso
from zendoc.diagnostic_service import complete_diagnostic_test
from zendoc.fulfilment_optimizer import optimize_prescription_fulfilment
from zendoc.order_service import update_order_tracking_status
from zendoc.prescription_service import create_prescription, transition_prescription_status
from zendoc.telehealth import request_consultation, update_consultation_status
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


def test_completed_appointment_cannot_move_back_to_confirmed(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "state-patient@example.com", "State Patient")
    register_web(client, "doctor", "state-doctor@example.com", "State Doctor")
    patient = _user(app, "state-patient@example.com")
    doctor = _user(app, "state-doctor@example.com")

    with app.app_context():
        db = get_db()
        appointment_id = db.execute(
            """
            INSERT INTO appointments
            (patient_id,provider_id,provider_name,scheduled_for,reason,status,created_at,updated_at)
            VALUES (?,?,'State Doctor','2026-12-20T10:00','Review','completed',?,?)
            """,
            (patient["id"], doctor["id"], now_iso(), now_iso()),
        ).lastrowid
        db.commit()

    login_web(client, "doctor", "state-doctor@example.com")
    page = client.get("/appointments")
    token = csrf(page.data.decode())

    rollback = client.post(
        f"/appointments/{appointment_id}/status",
        data={"csrf_token": token, "status": "confirmed"},
        follow_redirects=False,
    )
    assert rollback.status_code == 409

    page = client.get("/appointments")
    token = csrf(page.data.decode())
    replay = client.post(
        f"/appointments/{appointment_id}/status",
        data={"csrf_token": token, "status": "completed"},
        follow_redirects=False,
    )
    assert replay.status_code in {302, 303}

    with app.app_context():
        status = get_db().execute(
            "SELECT status FROM appointments WHERE id=?", (appointment_id,)
        ).fetchone()["status"]
        assert status == "completed"


def test_unauthorized_same_state_appointment_request_is_still_forbidden(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "same-patient@example.com", "Same Patient")
    register_web(client, "doctor", "same-doctor-a@example.com", "Doctor A")
    register_web(client, "doctor", "same-doctor-b@example.com", "Doctor B")
    patient = _user(app, "same-patient@example.com")
    doctor_a = _user(app, "same-doctor-a@example.com")

    with app.app_context():
        db = get_db()
        appointment_id = db.execute(
            """
            INSERT INTO appointments
            (patient_id,provider_id,provider_name,scheduled_for,reason,status,created_at,updated_at)
            VALUES (?,?,'Doctor A','2026-12-20T10:00','Review','confirmed',?,?)
            """,
            (patient["id"], doctor_a["id"], now_iso(), now_iso()),
        ).lastrowid
        db.commit()

    login_web(client, "doctor", "same-doctor-b@example.com")
    page = client.get("/appointments")
    token = csrf(page.data.decode())
    response = client.post(
        f"/appointments/{appointment_id}/status",
        data={"csrf_token": token, "status": "confirmed"},
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_ended_telehealth_consultation_is_terminal_and_replay_safe(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    api_token(client, "tele-state-patient@example.com")
    register_web(client, "doctor", "tele-state-doctor@example.com", "Tele Doctor")
    patient = _user(app, "tele-state-patient@example.com")
    doctor = _user(app, "tele-state-doctor@example.com")

    with app.app_context():
        consultation = request_consultation(
            patient,
            {
                "doctor_id": doctor["id"],
                "consultation_type": "chat",
                "reason": "Follow up",
            },
        )
        accepted = update_consultation_status(doctor, consultation["id"], "accepted")
        assert accepted["status"] == "accepted"
        ended = update_consultation_status(doctor, consultation["id"], "ended")
        assert ended["status"] == "ended"

        replay = update_consultation_status(doctor, consultation["id"], "ended")
        assert replay["status"] == "ended"

        with pytest.raises(ValueError):
            update_consultation_status(doctor, consultation["id"], "accepted")


def test_diagnostic_completion_replay_does_not_duplicate_timeline_event(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    api_token(client, "diag-state-patient@example.com")
    register_web(client, "hospital", "diag-state-lab@example.com", "State Lab")
    patient = _user(app, "diag-state-patient@example.com")
    lab = _user(app, "diag-state-lab@example.com")

    with app.app_context():
        db = get_db()
        now = now_iso()
        db.execute(
            """
            INSERT INTO provider_profiles
            (user_id,provider_type,specialty,organization,verification_status,created_at,updated_at)
            VALUES (?, 'diagnostic_centre','General','State Lab','verified',?,?)
            """,
            (lab["id"], now, now),
        )
        test_id = db.execute(
            """
            INSERT INTO diagnostic_catalog
            (code,name,category,fasting_required,sample_type,tat_hours,standard_price_inr,created_at)
            VALUES ('STATE-DIAG','State Test','general',0,'blood',24,100,?)
            """,
            (now,),
        ).lastrowid
        booking_id = db.execute(
            """
            INSERT INTO diagnostic_bookings
            (booking_uid,patient_id,booked_by,lab_id,test_id,collection_type,scheduled_date,address,status,price_inr,created_at,updated_at)
            VALUES ('state-diag-booking',?,?,?,?,'lab_visit','2026-12-20','Lab','requested',100,?,?)
            """,
            (patient["id"], patient["id"], lab["id"], test_id, now, now),
        ).lastrowid
        db.commit()

        first = complete_diagnostic_test(lab, booking_id, "Completed")
        assert first["status"] == "completed"
        replay = complete_diagnostic_test(lab, booking_id, "Completed again")
        assert replay["idempotent_replay"] is True

        count = db.execute(
            """
            SELECT COUNT(*) c FROM health_timeline_events
            WHERE patient_id=? AND event_type='DIAGNOSTIC_COMPLETED'
              AND source_ref=?
            """,
            (patient["id"], f"diagnostic:{booking_id}"),
        ).fetchone()["c"]
        assert count == 1


def test_delivered_order_is_terminal_and_delivery_event_is_not_duplicated(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    api_token(client, "order-state-patient@example.com")
    register_web(client, "pharmacy", "order-state-pharmacy@example.com", "State Pharmacy")
    patient = _user(app, "order-state-patient@example.com")
    pharmacy = _user(app, "order-state-pharmacy@example.com")

    with app.app_context():
        db = get_db()
        now = now_iso()
        order_id = db.execute(
            """
            INSERT INTO medicine_orders
            (patient_id,ordered_by,pharmacy_id,items_json,delivery_address,status,tracking_status,created_at,updated_at)
            VALUES (?,?,?,'[]','Test Address','out_for_delivery','OUT_FOR_DELIVERY',?,?)
            """,
            (patient["id"], patient["id"], pharmacy["id"], now, now),
        ).lastrowid
        db.commit()

        delivered = update_order_tracking_status(pharmacy, order_id, "DELIVERED")
        assert delivered["tracking_status"] == "DELIVERED"
        replay = update_order_tracking_status(pharmacy, order_id, "DELIVERED")
        assert replay["tracking_status"] == "DELIVERED"

        with pytest.raises(ValueError):
            update_order_tracking_status(pharmacy, order_id, "PREPARING")

        count = db.execute(
            """
            SELECT COUNT(*) c FROM health_timeline_events
            WHERE patient_id=? AND event_type='MEDICINE_DELIVERED'
              AND source_ref=?
            """,
            (patient["id"], f"order:{order_id}"),
        ).fetchone()["c"]
        assert count == 1


def test_terminal_prescription_cannot_return_active_or_be_fulfilled(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    api_token(client, "rx-state-patient@example.com")
    patient = _user(app, "rx-state-patient@example.com")

    with app.app_context():
        db = get_db()
        sku_id = db.execute(
            """
            INSERT INTO medication_skus
            (sku_code,name,generic_name,form,pack_size,pack_unit,mrp_inr,rx_required,data_mode,created_at)
            VALUES ('STATE-RX-1','State Medicine','State Generic','tablet',1,'tablet',10,0,'LIVE',?)
            """,
            (now_iso(),),
        ).lastrowid
        db.commit()

        rx = create_prescription(
            patient_id=patient["id"],
            prescriber_name="Existing Prescription",
            items=[
                {
                    "medicine_name": "State Medicine",
                    "sku_id": sku_id,
                    "extraction_confidence": 1.0,
                    "quantity_prescribed": 1,
                }
            ],
            source="USER_REPORTED",
        )
        cancelled = transition_prescription_status(rx["id"], patient, "cancelled")
        assert cancelled["status"] == "cancelled"

        replay = transition_prescription_status(rx["id"], patient, "cancelled")
        assert replay["status"] == "cancelled"

        with pytest.raises(ValueError):
            transition_prescription_status(rx["id"], patient, "active")

        with pytest.raises(ValueError):
            optimize_prescription_fulfilment(
                prescription_id=rx["id"],
                patient_id=patient["id"],
                stage_in_db=False,
            )


def test_prescribing_doctor_can_supersede_but_unrelated_doctor_cannot(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    api_token(client, "rx-doc-patient@example.com")
    register_web(client, "doctor", "rx-doc-a@example.com", "Doctor A")
    register_web(client, "doctor", "rx-doc-b@example.com", "Doctor B")
    patient = _user(app, "rx-doc-patient@example.com")
    doctor_a = _user(app, "rx-doc-a@example.com")
    doctor_b = _user(app, "rx-doc-b@example.com")

    with app.app_context():
        rx = create_prescription(
            patient_id=patient["id"],
            prescriber_name="Doctor A",
            prescriber_id=doctor_a["id"],
            items=[{"medicine_name": "Uncatalogued Medicine", "extraction_confidence": 0.5}],
            source="PROVIDER_RECORDED",
        )

        with pytest.raises(PermissionError):
            transition_prescription_status(rx["id"], doctor_b, "superseded")

        changed = transition_prescription_status(rx["id"], doctor_a, "superseded")
        assert changed["status"] == "superseded"


def test_duplicate_telehealth_request_reuses_existing_active_consultation(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    api_token(client, "tele-retry-patient@example.com")
    register_web(client, "doctor", "tele-retry-doctor@example.com", "Retry Doctor")
    patient = _user(app, "tele-retry-patient@example.com")
    doctor = _user(app, "tele-retry-doctor@example.com")

    payload = {
        "doctor_id": doctor["id"],
        "consultation_type": "chat",
        "reason": "Same retry reason",
        "scheduled_for": "2026-12-22T11:00",
    }
    with app.app_context():
        first = request_consultation(patient, payload)
        second = request_consultation(patient, payload)
        assert second["id"] == first["id"]
        assert second["idempotent_replay"] is True

        count = get_db().execute(
            """
            SELECT COUNT(*) c FROM consultation_requests
            WHERE patient_id=? AND doctor_id=? AND reason=?
            """,
            (patient["id"], doctor["id"], payload["reason"]),
        ).fetchone()["c"]
        assert count == 1


def test_duplicate_diagnostic_booking_reuses_existing_request_without_new_timeline_event(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    api_token(client, "diag-retry-patient@example.com")
    register_web(client, "hospital", "diag-retry-lab@example.com", "Retry Lab")
    patient = _user(app, "diag-retry-patient@example.com")
    lab = _user(app, "diag-retry-lab@example.com")

    with app.app_context():
        db = get_db()
        now = now_iso()
        db.execute(
            """
            INSERT INTO provider_profiles
            (user_id,provider_type,specialty,organization,verification_status,created_at,updated_at)
            VALUES (?, 'diagnostic_centre','General','Retry Lab','verified',?,?)
            """,
            (lab["id"], now, now),
        )
        test_id = db.execute(
            """
            INSERT INTO diagnostic_catalog
            (code,name,category,fasting_required,sample_type,tat_hours,standard_price_inr,created_at)
            VALUES ('RETRY-DIAG','Retry Diagnostic','general',0,'blood',24,100,?)
            """,
            (now,),
        ).lastrowid
        db.execute(
            """
            INSERT INTO diagnostic_offers
            (lab_id,test_id,price_inr,home_collection_available,home_collection_fee_inr,verified,data_mode,observed_at,created_at)
            VALUES (?,?,100,1,0,1,'LIVE',?,?)
            """,
            (lab["id"], test_id, now, now),
        )
        db.commit()

        from zendoc.diagnostic_service import book_diagnostic_test
        kwargs = {
            "actor": patient,
            "patient_id": patient["id"],
            "test_id": test_id,
            "lab_id": lab["id"],
            "scheduled_date": "2026-12-23",
            "address": "Retry Address",
            "collection_type": "home_collection",
            "slot_time": "09:30",
            "user_confirmed": True,
        }
        first = book_diagnostic_test(**kwargs)
        second = book_diagnostic_test(**kwargs)
        assert second["booking_id"] == first["booking_id"]
        assert second["idempotent_replay"] is True

        booking_count = db.execute(
            """
            SELECT COUNT(*) c FROM diagnostic_bookings
            WHERE patient_id=? AND lab_id=? AND test_id=? AND scheduled_date='2026-12-23'
            """,
            (patient["id"], lab["id"], test_id),
        ).fetchone()["c"]
        assert booking_count == 1

        event_count = db.execute(
            """
            SELECT COUNT(*) c FROM health_timeline_events
            WHERE patient_id=? AND event_type='DIAGNOSTIC_REQUESTED'
            """,
            (patient["id"],),
        ).fetchone()["c"]
        assert event_count == 1
