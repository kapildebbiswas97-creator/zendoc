from io import BytesIO

from werkzeug.datastructures import FileStorage

from tests.test_milestone1 import csrf, login_web, make_client, register_web
from zendoc.db import get_db, now_iso
from zendoc.record_storage import S3CompatibleRecordStorage
from zendoc.launch_readiness import public_launch_readiness
from zendoc.account_lifecycle import delete_account


def test_public_launch_legal_pwa_and_deletion_routes_exist(tmp_path):
    _app, client = make_client(tmp_path)

    for path, marker in (
        ("/privacy", "ZENDOC Privacy Policy"),
        ("/terms", "ZENDOC Terms of Service"),
        ("/medical-disclaimer", "Medical Disclaimer"),
        ("/account-deletion", "Delete your ZENDOC account"),
        ("/offline", "ZENDOC needs a connection"),
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert marker in response.get_data(as_text=True)

    manifest = client.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    payload = manifest.get_json()
    assert payload["name"] == "ZENDOC"
    assert payload["start_url"] == "/"
    assert payload["display"] == "standalone"

    sw = client.get("/sw.js")
    assert sw.status_code == 200
    text = sw.get_data(as_text=True)
    assert 'url.pathname.startsWith("/api/")' in text
    assert "HTML stays network-only" in text
    assert sw.headers["Service-Worker-Allowed"] == "/"


def test_profile_exposes_in_app_account_deletion_path(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "delete-profile@example.com", "Delete Profile")
    login_web(client, "patient", "delete-profile@example.com")

    response = client.get("/profile")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Delete ZENDOC account" in body
    assert "/account-deletion" in body


def test_password_confirmed_account_deletion_removes_account_ai_data_and_owned_file(tmp_path):
    app, client = make_client(tmp_path)
    email = "delete-me@example.com"
    register_web(client, "patient", email, "Delete Me")
    login_web(client, "patient", email)

    with app.app_context():
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email_normalized=?", (email,)).fetchone()
        user_id = int(user["id"])
        upload_root = app.config["UPLOAD_FOLDER"]
        import os
        os.makedirs(upload_root, exist_ok=True)
        stored = "delete-owned-report.txt"
        with open(os.path.join(upload_root, stored), "wb") as handle:
            handle.write(b"private report")
        db.execute(
            """
            INSERT INTO medical_records
            (owner_id,uploaded_by,title,category,original_filename,stored_filename,mime_type,file_size,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (user_id, user_id, "Delete report", "other", "report.txt", stored, "text/plain", 14, now_iso()),
        )
        db.execute(
            """
            INSERT INTO ai_interactions
            (user_id,feature,intent,input_text,output_text,risk_level,model_version,provider,emergency,success,latency_ms,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (user_id, "zendoc_ai", "general", "private question", "private answer", "low", "test", "test", 0, 1, 1, now_iso()),
        )
        db.commit()

    page = client.get("/account-deletion")
    token = csrf(page.data.decode())
    response = client.post(
        "/account-deletion",
        data={"csrf_token": token, "password": "StrongPass123"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "Your ZENDOC account was deleted" in response.get_data(as_text=True)

    with app.app_context():
        db = get_db()
        assert db.execute("SELECT id FROM users WHERE email_normalized=?", (email,)).fetchone() is None
        assert db.execute("SELECT id FROM ai_interactions WHERE input_text='private question'").fetchone() is None
        import os
        assert not os.path.exists(os.path.join(app.config["UPLOAD_FOLDER"], "delete-owned-report.txt"))


def test_wrong_password_does_not_delete_account(tmp_path):
    app, client = make_client(tmp_path)
    email = "keep-me@example.com"
    register_web(client, "patient", email, "Keep Me")
    login_web(client, "patient", email)

    page = client.get("/account-deletion")
    token = csrf(page.data.decode())
    response = client.post(
        "/account-deletion",
        data={"csrf_token": token, "password": "wrong-password"},
    )
    assert response.status_code == 400

    with app.app_context():
        assert get_db().execute("SELECT id FROM users WHERE email_normalized=?", (email,)).fetchone() is not None


def test_public_email_deletion_request_is_non_enumerating_and_sends_link_when_configured(tmp_path, monkeypatch):
    app, client = make_client(tmp_path)
    email = "delete-link@example.com"
    register_web(client, "patient", email, "Delete Link")

    sent = []
    from zendoc import public_launch_routes

    monkeypatch.setattr(
        public_launch_routes,
        "email_delivery_status",
        lambda: {"transactional_email": True, "provider": "smtp", "status": "configured"},
    )
    monkeypatch.setattr(
        public_launch_routes,
        "send_transactional_email",
        lambda to_email, subject, text_body: sent.append((to_email, subject, text_body)) or {"status": "sent"},
    )

    page = client.get("/account-deletion")
    token = csrf(page.data.decode())
    existing = client.post(
        "/account-deletion",
        data={"csrf_token": token, "email": email},
    )
    assert existing.status_code == 200
    assert "Deletion request received" in existing.get_data(as_text=True)
    assert len(sent) == 1
    assert sent[0][0] == email
    assert "/account-deletion/confirm?token=" in sent[0][2]

    page = client.get("/account-deletion")
    token = csrf(page.data.decode())
    missing = client.post(
        "/account-deletion",
        data={"csrf_token": token, "email": "missing-account@example.com"},
    )
    assert missing.status_code == 200
    assert "Deletion request received" in missing.get_data(as_text=True)
    assert len(sent) == 1


def test_api_account_deletion_supports_future_mobile_wrapper(tmp_path):
    app, client = make_client(tmp_path)
    email = "mobile-delete@example.com"
    register_web(client, "patient", email, "Mobile Delete")

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPass123"},
    )
    assert login.status_code == 200
    bearer = login.get_json()["token"]

    deleted = client.delete(
        "/api/v1/account",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"password": "StrongPass123"},
    )
    assert deleted.status_code == 200
    assert deleted.get_json()["status"] == "deleted"

    with app.app_context():
        assert get_db().execute("SELECT id FROM users WHERE email_normalized=?", (email,)).fetchone() is None


class _FakeBody:
    def __init__(self, value):
        self.value = value

    def read(self, _limit=-1):
        return self.value


class _FakeS3:
    def __init__(self):
        self.objects = {}
        self.deleted = []

    def upload_fileobj(self, stream, bucket, key, ExtraArgs=None):
        self.objects[(bucket, key)] = {
            "body": stream.read(),
            "content_type": (ExtraArgs or {}).get("ContentType"),
            "sse": (ExtraArgs or {}).get("ServerSideEncryption"),
        }

    def head_object(self, Bucket, Key):
        item = self.objects[(Bucket, Key)]
        return {"ContentLength": len(item["body"])}

    def get_object(self, Bucket, Key):
        item = self.objects[(Bucket, Key)]
        return {"Body": _FakeBody(item["body"]), "ContentType": item["content_type"]}

    def delete_object(self, Bucket, Key):
        self.deleted.append((Bucket, Key))
        self.objects.pop((Bucket, Key), None)


def test_s3_compatible_storage_save_read_and_delete(tmp_path, monkeypatch):
    app, _client = make_client(tmp_path)
    fake = _FakeS3()
    storage = S3CompatibleRecordStorage()

    with app.app_context():
        monkeypatch.setattr(
            storage,
            "_client",
            lambda: (
                fake,
                {
                    "bucket": "zendoc-test",
                    "endpoint_url": "https://storage.example.test",
                    "region": "auto",
                    "access_key": "x",
                    "secret_key": "y",
                    "sse": "AES256",
                },
            ),
        )
        upload = FileStorage(
            stream=BytesIO(b"hello-health-record"),
            filename="record.txt",
            content_type="text/plain",
        )
        saved = storage.save(upload, "record.txt")
        assert saved.provider == "s3"
        assert saved.size_bytes == len(b"hello-health-record")
        assert storage.read_bytes(saved.storage_key, max_bytes=100) == b"hello-health-record"
        storage.delete(saved.storage_key)
        assert ("zendoc-test", saved.storage_key) in fake.deleted


def test_public_launch_gate_reports_missing_real_world_configuration(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        app.config.update(
            ZENDOC_ENV="production",
            PUBLIC_BASE_URL="",
            EMAIL_PROVIDER="none",
            STORAGE_PROVIDER="local",
            STORAGE_VERIFIED=False,
            PERSISTENCE_VERIFIED=True,
        )
        report = public_launch_readiness()
        assert report["status"] == "PUBLIC_LAUNCH_BLOCKED"
        keys = {item["key"] for item in report["blockers"]}
        assert "public_base_url" in keys
        assert "transactional_email" in keys
        assert "durable_record_storage" in keys
        assert "/privacy" not in (report.get("missing_routes") or [])


def test_provider_account_deletion_deidentifies_without_cascading_patient_history(tmp_path):
    app, client = make_client(tmp_path)
    doctor_email = "delete-provider@example.com"
    patient_email = "provider-history-patient@example.com"
    register_web(client, "doctor", doctor_email, "Dr Delete Provider")
    client.get("/logout")
    register_web(client, "patient", patient_email, "History Patient")

    with app.app_context():
        db = get_db()
        doctor = db.execute("SELECT * FROM users WHERE email_normalized=?", (doctor_email,)).fetchone()
        patient = db.execute("SELECT * FROM users WHERE email_normalized=?", (patient_email,)).fetchone()
        stamp = now_iso()
        profile_id = db.execute(
            """
            INSERT INTO provider_profiles
            (user_id,provider_type,specialty,organization,verification_status,created_at,updated_at)
            VALUES (?,'doctor','Cardiology','History Clinic','verified',?,?)
            """,
            (doctor["id"], stamp, stamp),
        ).lastrowid
        appointment_id = db.execute(
            """
            INSERT INTO appointments
            (patient_id,provider_id,provider_profile_id,provider_name,specialty,scheduled_for,reason,status,created_at,updated_at)
            VALUES (?,?,?,?,?,'2026-12-15T10:00','History preservation','completed',?,?)
            """,
            (
                patient["id"],
                doctor["id"],
                profile_id,
                doctor["name"],
                "Cardiology",
                stamp,
                stamp,
            ),
        ).lastrowid
        record_id = db.execute(
            """
            INSERT INTO medical_records
            (owner_id,uploaded_by,title,category,original_filename,stored_filename,mime_type,file_size,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                patient["id"],
                doctor["id"],
                "Provider uploaded patient record",
                "other",
                "history.txt",
                "patient-history-provider-upload.txt",
                "text/plain",
                10,
                stamp,
            ),
        ).lastrowid
        db.commit()

        result = delete_account(doctor, password="StrongPass123")
        assert result["status"] == "deleted"
        assert result["deidentified_operational_anchor_retained"] is True

        tombstone = db.execute("SELECT * FROM users WHERE id=?", (doctor["id"],)).fetchone()
        assert tombstone is not None
        assert tombstone["active"] == 0
        assert tombstone["name"] == "Former ZENDOC provider"
        assert tombstone["email_normalized"].endswith("@zendoc.invalid")
        assert tombstone["phone"] is None

        assert db.execute("SELECT id FROM provider_profiles WHERE user_id=?", (doctor["id"],)).fetchone() is None

        appointment = db.execute("SELECT * FROM appointments WHERE id=?", (appointment_id,)).fetchone()
        assert appointment is not None
        assert appointment["patient_id"] == patient["id"]
        assert appointment["provider_id"] is None
        assert appointment["provider_profile_id"] is None
        assert appointment["provider_name"] == "Former ZENDOC provider"

        record = db.execute("SELECT * FROM medical_records WHERE id=?", (record_id,)).fetchone()
        assert record is not None
        assert record["owner_id"] == patient["id"]
        assert record["uploaded_by"] == doctor["id"]
