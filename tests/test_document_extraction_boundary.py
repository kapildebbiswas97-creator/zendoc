from pathlib import Path

from zendoc.db import get_db, now_iso
from tests.test_milestone1 import make_client, register_web


def _patient_id(app, email):
    with app.app_context():
        return int(get_db().execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()["id"])


def _record(app, patient_id, *, filename, stored_filename, mime_type, content, report_type="other"):
    with app.app_context():
        root = Path(app.config["UPLOAD_FOLDER"])
        root.mkdir(parents=True, exist_ok=True)
        (root / stored_filename).write_bytes(content)
        cursor = get_db().execute(
            """
            INSERT INTO medical_records
            (owner_id,uploaded_by,title,category,original_filename,stored_filename,mime_type,file_size,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                patient_id, patient_id, "Extraction test", "Report", filename, stored_filename,
                mime_type, len(content), now_iso(),
            ),
        )
        record_id = int(cursor.lastrowid)
        get_db().execute(
            """
            INSERT INTO report_metadata
            (record_id,report_uid,report_type,extraction_status,extraction_message,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                record_id, f"TEST-{record_id}", report_type, "unavailable",
                "Automatic extraction unavailable for this document.", now_iso(), now_iso(),
            ),
        )
        get_db().commit()
        return record_id


def _api_headers(client, email, password="StrongPass123"):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "role": "patient"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['token']}"}


def test_native_utf8_text_extraction_is_authorized_and_non_diagnostic(tmp_path):
    app, client = make_client(tmp_path)
    email = "extract-owner@example.com"
    register_web(client, "patient", email)
    patient_id = _patient_id(app, email)
    record_id = _record(
        app,
        patient_id,
        filename="report.txt",
        stored_filename="native-report.txt",
        mime_type="text/plain",
        content=b"Patient supplied note\n  second   line  \n",
    )

    response = client.post(
        f"/api/v1/reports/{record_id}/extract-text",
        headers=_api_headers(client, email),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "NATIVE_TEXT_EXTRACTED"
    assert payload["text"] == "Patient supplied note\nsecond line"
    assert len(payload["text_sha256"]) == 64
    assert payload["ocr_used"] is False
    assert payload["clinical_imaging_interpretation"] is False

    with app.app_context():
        metadata = get_db().execute(
            "SELECT extraction_status, extraction_message FROM report_metadata WHERE record_id=?",
            (record_id,),
        ).fetchone()
        assert metadata["extraction_status"] == "native_text_extracted"
        assert "OCR and clinical imaging interpretation were not used" in metadata["extraction_message"]


def test_non_text_document_reports_ocr_integration_required_without_fabrication(tmp_path):
    app, client = make_client(tmp_path)
    email = "extract-pdf@example.com"
    register_web(client, "patient", email)
    patient_id = _patient_id(app, email)
    record_id = _record(
        app,
        patient_id,
        filename="scan.pdf",
        stored_filename="scan.pdf",
        mime_type="application/pdf",
        content=b"%PDF-1.4\nminimal-test",
    )

    response = client.post(
        f"/api/v1/reports/{record_id}/extract-text",
        headers=_api_headers(client, email),
    )

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["status"] == "OCR_INTEGRATION_REQUIRED"
    assert payload["text"] is None
    assert payload["clinical_imaging_interpretation"] is False


def test_document_extraction_blocks_cross_patient_idor(tmp_path):
    app, client = make_client(tmp_path)
    first_email = "extract-first@example.com"
    second_email = "extract-second@example.com"
    register_web(client, "patient", first_email)
    client.get("/logout")
    register_web(client, "patient", second_email)
    second_id = _patient_id(app, second_email)
    record_id = _record(
        app,
        second_id,
        filename="private.txt",
        stored_filename="private.txt",
        mime_type="text/plain",
        content=b"Private patient report",
    )

    denied = client.post(
        f"/api/v1/reports/{record_id}/extract-text",
        headers=_api_headers(client, first_email),
    )

    assert denied.status_code == 403
    assert "cannot access another patient" in denied.get_json()["error"]["message"].lower()


def test_document_extraction_capabilities_are_truthful_and_authenticated(tmp_path):
    _app, client = make_client(tmp_path)
    denied = client.get("/api/v1/document-extraction/capabilities")
    assert denied.status_code in {401, 403}

    email = "extract-capabilities@example.com"
    register_web(client, "patient", email)
    allowed = client.get(
        "/api/v1/document-extraction/capabilities",
        headers=_api_headers(client, email),
    )
    assert allowed.status_code == 200
    capabilities = allowed.get_json()["capabilities"]
    assert capabilities["native_utf8_text"]["status"] == "WORKING"
    assert capabilities["ocr"]["status"] == "INTEGRATION_REQUIRED"
    assert capabilities["clinical_imaging_interpretation"]["status"] == "DISABLED"
