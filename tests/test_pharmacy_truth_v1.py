from tests.test_milestone1 import api_token, make_client
from tests.test_milestone6 import headers
from zendoc.db import get_db, now_iso


def _provider_id(app, email):
    with app.app_context():
        row = get_db().execute(
            "SELECT id FROM users WHERE email_normalized=?",
            (email,),
        ).fetchone()
        return int(row["id"])


def _make_provider_profile(app, user_id, status="pending"):
    with app.app_context():
        db = get_db()
        stamp = now_iso()
        cursor = db.execute(
            """
            INSERT INTO provider_profiles
            (user_id,provider_type,specialty,organization,city,verification_status,created_at,updated_at)
            VALUES (?,'pharmacy','','Truth Pharmacy','Kolkata',?,?,?)
            """,
            (user_id, status, stamp, stamp),
        )
        db.commit()
        return int(cursor.lastrowid)


def _make_record(app, patient_id, report_type):
    with app.app_context():
        db = get_db()
        stamp = now_iso()
        record_id = db.execute(
            """
            INSERT INTO medical_records
            (owner_id,uploaded_by,title,category,original_filename,stored_filename,mime_type,file_size,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                patient_id,
                patient_id,
                f"{report_type.title()} record",
                report_type,
                f"{report_type}.pdf",
                f"test-{report_type}-{patient_id}.pdf",
                "application/pdf",
                100,
                stamp,
            ),
        ).lastrowid
        db.execute(
            """
            INSERT INTO report_metadata
            (record_id,report_uid,report_type,extraction_status,extraction_message,created_at,updated_at)
            VALUES (?,?,?,'unavailable','test',?,?)
            """,
            (record_id, f"TEST-{record_id}", report_type, stamp, stamp),
        )
        db.commit()
        return int(record_id)


def test_specific_pharmacy_request_requires_verified_provider_profile(tmp_path):
    app, client = make_client(tmp_path)
    patient_token = api_token(client, "pharmacy-truth-patient@example.com")
    api_token(client, "pharmacy-pending@example.com", role="pharmacy")
    pharmacy_id = _provider_id(app, "pharmacy-pending@example.com")
    _make_provider_profile(app, pharmacy_id, status="pending")

    response = client.post(
        "/api/v1/pharmacy/orders",
        json={
            "items": [{"name": "Paracetamol 500mg", "quantity": 1}],
            "delivery_address": "Patient home",
            "pharmacy_id": pharmacy_id,
        },
        headers=headers(patient_token),
    )
    assert response.status_code == 400
    assert "active, verified ZENDOC pharmacy" in response.get_json()["error"]["message"]


def test_verified_pharmacy_can_receive_otc_request_without_stock_claim(tmp_path):
    app, client = make_client(tmp_path)
    patient_token = api_token(client, "pharmacy-otc-patient@example.com")
    api_token(client, "pharmacy-verified@example.com", role="pharmacy")
    pharmacy_id = _provider_id(app, "pharmacy-verified@example.com")
    _make_provider_profile(app, pharmacy_id, status="verified")

    response = client.post(
        "/api/v1/pharmacy/orders",
        json={
            "items": [{"name": "Paracetamol 500mg", "quantity": 1}],
            "delivery_address": "Patient home",
            "pharmacy_id": pharmacy_id,
        },
        headers=headers(patient_token),
    )
    assert response.status_code == 201
    order = response.get_json()["medicine_order"]
    assert order["status"] == "pending"
    assert order["pharmacy_id"] == pharmacy_id
    assert "in_stock" not in order
    assert "price" not in order


def test_rx_catalog_medicine_requires_owned_prescription_record(tmp_path):
    app, client = make_client(tmp_path)
    patient_email = "pharmacy-rx-patient@example.com"
    patient_token = api_token(client, patient_email)
    api_token(client, "pharmacy-rx-verified@example.com", role="pharmacy")
    pharmacy_id = _provider_id(app, "pharmacy-rx-verified@example.com")
    _make_provider_profile(app, pharmacy_id, status="verified")
    patient_id = _provider_id(app, patient_email)

    missing = client.post(
        "/api/v1/pharmacy/orders",
        json={
            "items": [{"name": "Amoxicillin 500mg", "quantity": 1}],
            "delivery_address": "Patient home",
            "pharmacy_id": pharmacy_id,
        },
        headers=headers(patient_token),
    )
    assert missing.status_code == 400
    assert "prescription record is required" in missing.get_json()["error"]["message"]

    wrong_record = _make_record(app, patient_id, "blood_test")
    wrong = client.post(
        "/api/v1/pharmacy/orders",
        json={
            "items": [{"name": "Amoxicillin 500mg", "quantity": 1}],
            "delivery_address": "Patient home",
            "pharmacy_id": pharmacy_id,
            "prescription_record_id": wrong_record,
        },
        headers=headers(patient_token),
    )
    assert wrong.status_code == 400
    assert "not labelled as a prescription" in wrong.get_json()["error"]["message"]

    prescription = _make_record(app, patient_id, "prescription")
    accepted = client.post(
        "/api/v1/pharmacy/orders",
        json={
            "items": [{"name": "Amoxicillin 500mg", "quantity": 1}],
            "delivery_address": "Patient home",
            "pharmacy_id": pharmacy_id,
            "prescription_record_id": prescription,
        },
        headers=headers(patient_token),
    )
    assert accepted.status_code == 201
    order = accepted.get_json()["medicine_order"]
    assert order["status"] == "pending"
    assert order["prescription_record_id"] == prescription
