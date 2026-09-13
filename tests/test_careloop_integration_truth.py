from datetime import datetime, timedelta, timezone

from zendoc.care_action_ledger import create_action, get_action
from zendoc.care_journey_store import create_persisted_journey
from zendoc.db import get_db, now_iso
from zendoc.diagnostic_service import book_diagnostic_test
from zendoc.home_health import create_home_health_request
from zendoc.operational_fulfilment import (
    assign_home_health_provider,
    publish_home_health_service,
    update_diagnostic_booking_status,
)
from zendoc.pharmacy_service import create_medicine_order
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


def _verify_provider(db, provider_id, provider_type):
    now = now_iso()
    db.execute(
        """
        INSERT INTO provider_profiles
        (user_id,provider_type,verification_status,created_at,updated_at)
        VALUES (?,?,?,?,?)
        """,
        (provider_id, provider_type, "verified", now, now),
    )
    db.commit()


def _care_action(db, service_ref):
    return db.execute(
        "SELECT id FROM care_actions WHERE service_ref=? ORDER BY id DESC LIMIT 1",
        (service_ref,),
    ).fetchone()


def test_verified_pharmacy_action_is_truthfully_integrated(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = _user(db, "Patient", "truth-pharmacy-patient@example.com", "patient")
        pharmacy_id = _user(db, "Pharmacy", "truth-pharmacy@example.com", "pharmacy")
        _verify_provider(db, pharmacy_id, "pharmacy")
        patient = {"id": patient_id, "role": "patient"}
        order = create_medicine_order(
            patient,
            {
                "items": [{"name": "ORS", "quantity": 1}],
                "delivery_address": "Truth address",
                "pharmacy_id": pharmacy_id,
            },
        )
        row = _care_action(db, f"zendoc_pharmacy_order:{int(order['id'])}")
        assert row is not None
        action = get_action(patient, int(row["id"]))
        assert action["integration_status"] == "ACTUALLY_INTEGRATED"
        assert action["execution_scope"] == "zendoc_internal_registered_pharmacy"
        assert action["external_execution"] is False


def test_verified_diagnostic_action_is_truthfully_integrated(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = _user(db, "Patient", "truth-diagnostic-patient@example.com", "patient")
        lab_id = _user(db, "Lab", "truth-diagnostic-lab@example.com", "hospital")
        _verify_provider(db, lab_id, "lab")
        test = db.execute("SELECT id FROM diagnostic_catalog ORDER BY id LIMIT 1").fetchone()
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
            address="10 Health Road",
            collection_type="home_collection",
            slot_time="09:00-11:00",
            user_confirmed=True,
            data_mode="LIVE",
        )
        update_diagnostic_booking_status(
            {"id": lab_id, "role": "hospital"}, int(booking["booking_id"]), "accepted"
        )
        row = _care_action(db, f"zendoc_diagnostic_booking:{int(booking['booking_id'])}")
        assert row is not None
        action = get_action({"id": patient_id, "role": "patient"}, int(row["id"]))
        assert action["integration_status"] == "ACTUALLY_INTEGRATED"
        assert action["execution_scope"] == "zendoc_internal_verified_diagnostic_provider"
        assert action["external_execution"] is False


def test_assigned_capable_home_health_action_is_truthfully_integrated(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = _user(db, "Patient", "truth-home-patient@example.com", "patient")
        provider_id = _user(db, "Hospital", "truth-home-provider@example.com", "hospital")
        _verify_provider(db, provider_id, "hospital")
        patient = {"id": patient_id, "role": "patient", "city": "Kolkata"}
        provider = {"id": provider_id, "role": "hospital"}
        publish_home_health_service(provider, "physiotherapy")
        request_row = create_home_health_request(
            patient,
            {
                "service_type": "physiotherapy",
                "scheduled_date": (datetime.now(timezone.utc).date() + timedelta(days=2)).isoformat(),
                "address": "44 Recovery Road",
                "city": "Kolkata",
            },
        )
        assign_home_health_provider(patient, int(request_row["id"]), provider_id)
        row = _care_action(db, f"zendoc_home_health_request:{int(request_row['id'])}")
        assert row is not None
        action = get_action(patient, int(row["id"]))
        assert action["integration_status"] == "ACTUALLY_INTEGRATED"
        assert action["execution_scope"] == "zendoc_internal_verified_home_health_provider"
        assert action["external_execution"] is False


def test_forged_service_ref_remains_tracking_only(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = _user(db, "Patient", "truth-forged@example.com", "patient")
        patient = {"id": patient_id, "role": "patient"}
        journey = create_persisted_journey(
            patient,
            patient_id=patient_id,
            provenance={"source": "truth_regression"},
        )
        action = create_action(
            patient,
            int(journey["id"]),
            {
                "action_type": "diagnostic_service",
                "title": "Forged diagnostic reference",
                "status": "STAGED",
                "human_confirmation_required": True,
                "service_ref": "zendoc_diagnostic_booking:999999999",
            },
        )
        assert action["integration_status"] == "TRACKING_ONLY"
        assert action["actual_execution_recorded"] is False
        assert action["external_execution"] is False
