from zendoc.db import get_db, now_iso
from zendoc.pharmacy_order_routes import update_medicine_order_status
from zendoc.pharmacy_service import create_medicine_order
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


def _verify_pharmacy(db, pharmacy_id):
    now = now_iso()
    db.execute(
        """
        INSERT INTO provider_profiles
        (user_id,provider_type,verification_status,created_at,updated_at)
        VALUES (?,?,?,?,?)
        """,
        (pharmacy_id, "pharmacy", "verified", now, now),
    )
    db.commit()


def _care_action_for_order(db, order_id):
    return db.execute(
        "SELECT * FROM care_actions WHERE service_ref=? ORDER BY id DESC LIMIT 1",
        (f"zendoc_pharmacy_order:{int(order_id)}",),
    ).fetchone()


def test_verified_assigned_pharmacy_order_links_and_syncs_careloop(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = _user(db, "CareLoop Patient", "careloop-rx-patient@example.com", "patient")
        pharmacy_id = _user(db, "CareLoop Pharmacy", "careloop-rx-pharmacy@example.com", "pharmacy")
        _verify_pharmacy(db, pharmacy_id)
        patient = {"id": patient_id, "role": "patient"}
        pharmacy = {"id": pharmacy_id, "role": "pharmacy"}

        order = create_medicine_order(patient, {
            "items": [{"name": "Paracetamol 500mg", "quantity": 1}],
            "delivery_address": "Pilot delivery address",
            "pharmacy_id": pharmacy_id,
        })
        action = _care_action_for_order(db, order["id"])
        assert action is not None
        assert action["patient_id"] == patient_id
        assert action["status"] == "STAGED"
        assert action["provider_name"] == "CareLoop Pharmacy"

        accepted = update_medicine_order_status(pharmacy, order["id"], "accepted")
        assert accepted["status"] == "accepted"
        assert _care_action_for_order(db, order["id"])["status"] == "CONFIRMED"

        preparing = update_medicine_order_status(pharmacy, order["id"], "preparing")
        assert preparing["status"] == "preparing"
        assert _care_action_for_order(db, order["id"])["status"] == "IN_PROGRESS"

        dispatched = update_medicine_order_status(pharmacy, order["id"], "dispatched")
        assert dispatched["status"] == "dispatched"
        assert _care_action_for_order(db, order["id"])["status"] == "IN_PROGRESS"

        completed = update_medicine_order_status(pharmacy, order["id"], "completed")
        assert completed["status"] == "completed"
        action = _care_action_for_order(db, order["id"])
        assert action["status"] == "COMPLETED"
        events = db.execute(
            "SELECT event_type,status FROM care_action_events WHERE action_id=? ORDER BY id",
            (int(action["id"]),),
        ).fetchall()
        assert [(row["event_type"], row["status"]) for row in events][-3:] == [
            ("INTERNAL_PHARMACY_ORDER_SYNC", "CONFIRMED"),
            ("INTERNAL_PHARMACY_ORDER_SYNC", "IN_PROGRESS"),
            ("INTERNAL_PHARMACY_ORDER_SYNC", "COMPLETED"),
        ]


def test_unverified_or_unassigned_pharmacy_order_is_not_marked_integrated(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = _user(db, "Truth Patient", "truth-rx-patient@example.com", "patient")
        unverified_pharmacy_id = _user(db, "Unverified Pharmacy", "truth-rx-pharmacy@example.com", "pharmacy")
        db.commit()
        patient = {"id": patient_id, "role": "patient"}

        unverified = create_medicine_order(patient, {
            "items": [{"name": "ORS", "quantity": 1}],
            "delivery_address": "Truth address",
            "pharmacy_id": unverified_pharmacy_id,
        })
        assert _care_action_for_order(db, unverified["id"]) is None

        unassigned = create_medicine_order(patient, {
            "items": [{"name": "ORS", "quantity": 1}],
            "delivery_address": "Truth address",
        })
        assert _care_action_for_order(db, unassigned["id"]) is None


def test_other_pharmacy_cannot_update_assigned_order_or_care_action(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = _user(db, "Secure Patient", "secure-rx-patient@example.com", "patient")
        assigned_id = _user(db, "Assigned Pharmacy", "assigned-rx@example.com", "pharmacy")
        other_id = _user(db, "Other Pharmacy", "other-rx@example.com", "pharmacy")
        _verify_pharmacy(db, assigned_id)
        _verify_pharmacy(db, other_id)
        patient = {"id": patient_id, "role": "patient"}
        other = {"id": other_id, "role": "pharmacy"}

        order = create_medicine_order(patient, {
            "items": [{"name": "Paracetamol 500mg", "quantity": 1}],
            "delivery_address": "Secure address",
            "pharmacy_id": assigned_id,
        })
        action = _care_action_for_order(db, order["id"])
        assert action["status"] == "STAGED"

        try:
            update_medicine_order_status(other, order["id"], "accepted")
        except PermissionError:
            pass
        else:
            raise AssertionError("Unassigned pharmacy must not update another pharmacy's order")

        persisted_order = db.execute("SELECT status FROM medicine_orders WHERE id=?", (order["id"],)).fetchone()
        assert persisted_order["status"] == "pending"
        assert _care_action_for_order(db, order["id"])["status"] == "STAGED"


def test_pharmacy_status_api_rejects_cross_pharmacy_idor(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    def register(name, email, role):
        response = client.post(
            "/api/v1/auth/register",
            json={"name": name, "email": email, "password": "StrongPass123", "role": role},
        )
        assert response.status_code == 201

    register("API Patient", "api-rx-patient@example.com", "patient")
    register("Assigned API Pharmacy", "api-rx-assigned@example.com", "pharmacy")
    register("Other API Pharmacy", "api-rx-other@example.com", "pharmacy")

    with app.app_context():
        db = get_db()
        patient_id = int(db.execute("SELECT id FROM users WHERE email_normalized=?", ("api-rx-patient@example.com",)).fetchone()["id"])
        assigned_id = int(db.execute("SELECT id FROM users WHERE email_normalized=?", ("api-rx-assigned@example.com",)).fetchone()["id"])
        other_id = int(db.execute("SELECT id FROM users WHERE email_normalized=?", ("api-rx-other@example.com",)).fetchone()["id"])
        _verify_pharmacy(db, assigned_id)
        _verify_pharmacy(db, other_id)
        order = create_medicine_order(
            {"id": patient_id, "role": "patient"},
            {
                "items": [{"name": "ORS", "quantity": 1}],
                "delivery_address": "API address",
                "pharmacy_id": assigned_id,
            },
        )
        order_id = int(order["id"])

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "api-rx-other@example.com", "password": "StrongPass123"},
    )
    assert login.status_code == 200
    token = login.get_json()["token"]
    denied = client.post(
        f"/api/v1/pharmacy/orders/{order_id}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "accepted"},
    )
    assert denied.status_code == 403

    with app.app_context():
        db = get_db()
        assert db.execute("SELECT status FROM medicine_orders WHERE id=?", (order_id,)).fetchone()["status"] == "pending"
        assert _care_action_for_order(db, order_id)["status"] == "STAGED"


def test_invalid_pharmacy_transition_does_not_change_source_or_careloop(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = _user(db, "Transition Patient", "transition-rx-patient@example.com", "patient")
        pharmacy_id = _user(db, "Transition Pharmacy", "transition-rx-pharmacy@example.com", "pharmacy")
        _verify_pharmacy(db, pharmacy_id)
        patient = {"id": patient_id, "role": "patient"}
        pharmacy = {"id": pharmacy_id, "role": "pharmacy"}
        order = create_medicine_order(patient, {
            "items": [{"name": "ORS", "quantity": 1}],
            "delivery_address": "Transition address",
            "pharmacy_id": pharmacy_id,
        })

        try:
            update_medicine_order_status(pharmacy, order["id"], "completed")
        except ValueError:
            pass
        else:
            raise AssertionError("pending -> completed must be rejected")

        assert db.execute("SELECT status FROM medicine_orders WHERE id=?", (order["id"],)).fetchone()["status"] == "pending"
        assert _care_action_for_order(db, order["id"])["status"] == "STAGED"
