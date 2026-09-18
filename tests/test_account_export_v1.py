import json

from tests.test_milestone1 import login_web, make_client, register_web
from zendoc.db import get_db, now_iso


def test_patient_can_export_own_structured_data_without_auth_or_storage_fields(tmp_path):
    app, client = make_client(tmp_path)
    email = "export-patient@example.com"
    register_web(client, "patient", email, "Export Patient")
    login_web(client, "patient", email)

    with app.app_context():
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email_normalized=?", (email,)).fetchone()
        uid = int(user["id"])
        stamp = now_iso()
        db.execute(
            """
            INSERT INTO health_metrics
            (user_id,metric_type,metric_value,unit,recorded_at,numeric_value,source,notes)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (uid, "weight", "65", "kg", stamp, 65.0, "manual", "My export metric"),
        )
        db.execute(
            """
            INSERT INTO ai_interactions
            (user_id,feature,intent,input_text,output_text,risk_level,model_version,provider,emergency,success,latency_ms,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                uid,
                "zendoc_ai",
                "general",
                "private export prompt",
                "private export answer",
                "low",
                "test-model",
                "test-provider",
                0,
                1,
                1,
                stamp,
            ),
        )
        db.execute(
            """
            INSERT INTO medical_records
            (owner_id,uploaded_by,title,category,original_filename,stored_filename,mime_type,file_size,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                uid,
                uid,
                "Export report",
                "other",
                "report.txt",
                "storage-object-marker-123.txt",
                "text/plain",
                5,
                stamp,
            ),
        )
        db.commit()

    response = client.get("/account/export")
    assert response.status_code == 200
    assert response.mimetype == "application/json"
    assert "attachment" in response.headers.get("Content-Disposition", "")
    payload = json.loads(response.get_data(as_text=True))

    assert payload["account"]["email_normalized"] == email
    assert "password_hash" not in payload["account"]
    assert "api_tokens" not in payload
    assert payload["patient_data"]["health_metrics"][0]["notes"] == "My export metric"
    assert payload["patient_data"]["ai_interactions"][0]["input_text"] == "private export prompt"
    record = payload["patient_data"]["medical_records"][0]
    assert record["original_filename"] == "report.txt"
    assert "stored_filename" not in record
    assert "storage-object-marker-123" not in response.get_data(as_text=True)


def test_mobile_api_account_export_is_user_scoped(tmp_path):
    _app, client = make_client(tmp_path)
    one = "export-one@example.com"
    two = "export-two@example.com"
    register_web(client, "patient", one, "Export One")
    client.get("/logout")
    register_web(client, "patient", two, "Export Two")

    login = client.post(
        "/api/v1/auth/login",
        json={"email": one, "password": "StrongPass123"},
    )
    assert login.status_code == 200
    token = login.get_json()["token"]

    response = client.get(
        "/api/v1/account/export",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["account"]["email_normalized"] == one
    assert two not in json.dumps(payload)


def test_provider_export_omits_patient_consultation_reason(tmp_path):
    app, client = make_client(tmp_path)
    doctor_email = "export-doctor@example.com"
    patient_email = "export-reason-patient@example.com"
    register_web(client, "doctor", doctor_email, "Export Doctor")
    client.get("/logout")
    register_web(client, "patient", patient_email, "Export Reason Patient")

    patient_reason_marker = "PATIENT-REASON-PORTABILITY-BOUNDARY-123"
    with app.app_context():
        db = get_db()
        doctor = db.execute("SELECT * FROM users WHERE email_normalized=?", (doctor_email,)).fetchone()
        patient = db.execute("SELECT * FROM users WHERE email_normalized=?", (patient_email,)).fetchone()
        stamp = now_iso()
        db.execute(
            """
            INSERT INTO consultation_requests
            (patient_id,doctor_id,consultation_type,status,reason,created_at,updated_at)
            VALUES (?,?,'chat','requested',?,?,?)
            """,
            (patient["id"], doctor["id"], patient_reason_marker, stamp, stamp),
        )
        db.commit()

    login = client.post(
        "/api/v1/auth/login",
        json={"email": doctor_email, "password": "StrongPass123"},
    )
    assert login.status_code == 200
    token = login.get_json()["token"]

    response = client.get(
        "/api/v1/account/export",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = json.dumps(response.get_json())
    assert patient_reason_marker not in body
    provider_data = response.get_json()["provider_data"]
    assert provider_data["consultation_metadata"][0]["consultation_type"] == "chat"
    assert "reason" not in provider_data["consultation_metadata"][0]
