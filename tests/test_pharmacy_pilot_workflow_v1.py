import pytest

from zendoc.db import get_db, now_iso
from zendoc.pharmacy_service import create_medicine_order, list_medicine_orders
from tests.test_milestone1 import make_app


def _user(db, name, email, role):
    now = now_iso()
    return int(db.execute(
        """
        INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
        VALUES (?,?,?,?,?,1,?,?)
        """,
        (name, email, email, "test-hash", role, now, now),
    ).lastrowid)


def test_assigned_pharmacy_can_see_incoming_order(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = _user(db, "Pilot Patient", "pharmacy-patient@example.com", "patient")
        pharmacy_id = _user(db, "Pilot Pharmacy", "pharmacy-provider@example.com", "pharmacy")
        db.commit()
        patient = {"id": patient_id, "role": "patient"}
        pharmacy = {"id": pharmacy_id, "role": "pharmacy"}

        order = create_medicine_order(patient, {
            "items": [{"name": "Paracetamol 500mg", "quantity": 1}],
            "delivery_address": "Pilot address",
            "pharmacy_id": pharmacy_id,
        })
        assert order["pharmacy_id"] == pharmacy_id
        assert [row["id"] for row in list_medicine_orders(pharmacy)] == [order["id"]]


def test_order_rejects_inactive_or_non_pharmacy_assignment(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = _user(db, "Pilot Patient", "pharmacy-patient2@example.com", "patient")
        doctor_id = _user(db, "Pilot Doctor", "pharmacy-doctor@example.com", "doctor")
        db.commit()
        with pytest.raises(ValueError, match="active pharmacy"):
            create_medicine_order(
                {"id": patient_id, "role": "patient"},
                {"items": [{"name": "Test", "quantity": 1}], "delivery_address": "Address", "pharmacy_id": doctor_id},
            )


def test_unknown_prescription_record_is_a_client_error(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = _user(db, "Pilot Patient", "pharmacy-patient3@example.com", "patient")
        db.commit()
        with pytest.raises(LookupError, match="Prescription medical record not found"):
            create_medicine_order(
                {"id": patient_id, "role": "patient"},
                {
                    "items": [{"name": "Test", "quantity": 1}],
                    "delivery_address": "Address",
                    "prescription_record_id": 999999,
                },
            )


def test_pharmacy_api_maps_unknown_prescription_to_404(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register = client.post(
        "/api/v1/auth/register",
        json={"name": "API Patient", "email": "pharmacy-api-patient@example.com", "password": "StrongPass123", "role": "patient"},
    )
    assert register.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "pharmacy-api-patient@example.com", "password": "StrongPass123"},
    )
    response = client.post(
        "/api/v1/pharmacy/orders",
        headers={"Authorization": f"Bearer {login.get_json()['token']}"},
        json={"items": [{"name": "Test", "quantity": 1}], "delivery_address": "Address", "prescription_record_id": 999999},
    )
    assert response.status_code == 404

