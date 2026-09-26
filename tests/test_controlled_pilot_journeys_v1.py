from datetime import datetime, timedelta, timezone

from zendoc.db import get_db, now_iso
from zendoc.diagnostic_service import book_diagnostic_test
from zendoc.operational_fulfilment import update_diagnostic_booking_status
from zendoc.pharmacy_order_routes import update_medicine_order_status
from zendoc.pharmacy_service import create_medicine_order
from tests.test_milestone1 import csrf, login_web, make_client, register_web


def _future_web_datetime(days=5):
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")


def _future_date(days=5):
    return (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()


def test_patient_find_care_request_provider_acknowledgement_and_feedback(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENDOC_PLACES_PROVIDER", "none")
    app, client = make_client(tmp_path)

    register_web(client, "doctor", "pilot-doctor@example.com", "Pilot Doctor")
    client.get("/logout")
    with app.app_context():
        db = get_db()
        doctor = db.execute(
            "SELECT id FROM users WHERE email_normalized='pilot-doctor@example.com'"
        ).fetchone()
        db.execute(
            """
            UPDATE provider_profiles
            SET provider_type='doctor', specialty='Cardiology',
                organization='Pilot Clinic', address='Station Road',
                city='Kalyani', state='West Bengal', postal_code='741235',
                verification_status='verified', updated_at=?
            WHERE user_id=?
            """,
            (now_iso(), int(doctor["id"])),
        )
        db.commit()

    register_web(client, "patient", "pilot-patient@example.com", "Pilot Patient")
    login_web(client, "patient", "pilot-patient@example.com")

    finder_page = client.get("/finder")
    finder_token = csrf(finder_page.data.decode())
    finder = client.post(
        "/finder",
        data={
            "csrf_token": finder_token,
            "category": "doctor",
            "specialty": "Cardiology",
            "location": "Kalyani",
            "radius_km": "10",
        },
        follow_redirects=True,
    )
    assert finder.status_code == 200
    assert b"Pilot Doctor" in finder.data

    appointment_page = client.get("/appointments")
    appointment_token = csrf(appointment_page.data.decode())
    requested = client.post(
        "/appointments",
        data={
            "csrf_token": appointment_token,
            "provider_email": "pilot-doctor@example.com",
            "provider_name": "Pilot Doctor",
            "scheduled_for": _future_web_datetime(),
            "reason": "Controlled pilot care request",
        },
        follow_redirects=False,
    )
    assert requested.status_code == 302

    with app.app_context():
        db = get_db()
        appointment = db.execute(
            "SELECT id,status FROM appointments ORDER BY id DESC LIMIT 1"
        ).fetchone()
        appointment_id = int(appointment["id"])
        assert appointment["status"] == "requested"
        action = db.execute(
            "SELECT id,status FROM care_actions WHERE service_ref=?",
            (f"zendoc_appointment:{appointment_id}",),
        ).fetchone()
        assert action is not None
        assert action["status"] == "STAGED"

    client.get("/logout")
    login_web(client, "doctor", "pilot-doctor@example.com")
    provider_page = client.get("/appointments")
    provider_token = csrf(provider_page.data.decode())
    confirmed = client.post(
        f"/appointments/{appointment_id}/status",
        data={"csrf_token": provider_token, "status": "confirmed"},
        follow_redirects=False,
    )
    assert confirmed.status_code == 302

    client.get("/logout")
    login_web(client, "patient", "pilot-patient@example.com")
    feedback_page = client.get("/feedback?page=/appointments&feature=appointments")
    feedback_token = csrf(feedback_page.data.decode())
    feedback = client.post(
        "/feedback",
        data={
            "csrf_token": feedback_token,
            "page_path": "/appointments",
            "feature": "appointments",
            "category": "usability",
            "severity": "low",
            "message": "Controlled pilot journey completed; feedback path works.",
        },
        follow_redirects=True,
    )
    assert feedback.status_code == 200

    with app.app_context():
        db = get_db()
        appointment = db.execute(
            "SELECT status FROM appointments WHERE id=?", (appointment_id,)
        ).fetchone()
        assert appointment["status"] == "confirmed"
        action = db.execute(
            "SELECT status FROM care_actions WHERE service_ref=?",
            (f"zendoc_appointment:{appointment_id}",),
        ).fetchone()
        assert action["status"] == "CONFIRMED"
        feedback_row = db.execute(
            "SELECT status,feature FROM pilot_feedback_reports ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert feedback_row["status"] == "NEW"
        assert feedback_row["feature"] == "appointments"


def test_pharmacy_request_requires_assigned_provider_acknowledgement(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "pharmacy", "pilot-pharmacy@example.com", "Pilot Pharmacy")
    client.get("/logout")
    register_web(client, "patient", "pilot-pharmacy-patient@example.com", "Pilot Patient")

    with app.app_context():
        db = get_db()
        pharmacy = db.execute(
            "SELECT * FROM users WHERE email_normalized='pilot-pharmacy@example.com'"
        ).fetchone()
        patient = db.execute(
            "SELECT * FROM users WHERE email_normalized='pilot-pharmacy-patient@example.com'"
        ).fetchone()
        db.execute(
            "UPDATE provider_profiles SET provider_type='pharmacy',verification_status='verified',updated_at=? WHERE user_id=?",
            (now_iso(), int(pharmacy["id"])),
        )
        db.commit()

        order = create_medicine_order(
            dict(patient),
            {
                "items": [{"name": "Pilot medicine request", "quantity": 1}],
                "delivery_address": "Pilot delivery address",
                "pharmacy_id": int(pharmacy["id"]),
            },
        )
        assert order["status"] == "pending"

        accepted = update_medicine_order_status(
            dict(pharmacy), int(order["id"]), "accepted"
        )
        assert accepted["status"] == "accepted"
        persisted = db.execute(
            "SELECT status,pharmacy_id FROM medicine_orders WHERE id=?",
            (int(order["id"]),),
        ).fetchone()
        assert persisted["status"] == "accepted"
        assert int(persisted["pharmacy_id"]) == int(pharmacy["id"])


def test_lab_request_stays_unreported_until_provider_workflow_advances(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "hospital", "pilot-lab@example.com", "Pilot Lab")
    client.get("/logout")
    register_web(client, "patient", "pilot-lab-patient@example.com", "Pilot Patient")

    with app.app_context():
        db = get_db()
        lab = db.execute(
            "SELECT * FROM users WHERE email_normalized='pilot-lab@example.com'"
        ).fetchone()
        patient = db.execute(
            "SELECT * FROM users WHERE email_normalized='pilot-lab-patient@example.com'"
        ).fetchone()
        db.execute(
            """
            UPDATE provider_profiles
            SET provider_type='lab',verification_status='verified',
                organization='Pilot Lab',city='Kalyani',updated_at=?
            WHERE user_id=?
            """,
            (now_iso(), int(lab["id"])),
        )
        test = db.execute(
            "SELECT id FROM diagnostic_catalog ORDER BY id LIMIT 1"
        ).fetchone()
        assert test is not None
        db.execute(
            """
            INSERT INTO diagnostic_offers
            (lab_id,test_id,price_inr,home_collection_available,home_collection_fee_inr,
             verified,data_mode,observed_at,created_at)
            VALUES (?,?,500,1,0,1,'LIVE',?,?)
            """,
            (int(lab["id"]), int(test["id"]), now_iso(), now_iso()),
        )
        db.commit()

        booking = book_diagnostic_test(
            actor=dict(patient),
            patient_id=int(patient["id"]),
            test_id=int(test["id"]),
            lab_id=int(lab["id"]),
            scheduled_date=_future_date(),
            address="Pilot collection address, Kalyani",
            collection_type="home_collection",
            user_confirmed=True,
            data_mode="LIVE",
        )
        assert booking["status"] == "requested"
        assert booking.get("report_record_id") is None

        accepted = update_diagnostic_booking_status(
            dict(lab), int(booking["id"]), "accepted",
            note="Assigned lab acknowledged the request in ZENDOC.",
        )
        assert accepted["status"] == "accepted"
        assert accepted["external_execution"] is False
        assert accepted.get("report_record_id") is None
