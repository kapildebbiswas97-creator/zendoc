from zendoc.db import get_db, now_iso
from tests.test_milestone1 import login_web, make_client, register_web


def test_patient_can_open_care_continuity_console(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "continuity@example.com", "Continuity Patient")
    login_web(client, "patient", "continuity@example.com")
    response = client.get("/care-continuity")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Care Continuity" in body
    assert "Clinician handoff packet" in body
    assert "AI Evidence Passport" in body
    assert "never sent automatically" in body


def test_non_patient_cannot_open_patient_continuity_console(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "doctor", "continuity-doctor@example.com", "Continuity Doctor")
    login_web(client, "doctor", "continuity-doctor@example.com")
    assert client.get("/care-continuity").status_code == 403


def test_clinician_handoff_is_descriptive_and_not_auto_shared(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "handoff@example.com", "Handoff Patient")
    login_web(client, "patient", "handoff@example.com")
    response = client.get(
        "/api/v1/clinician-handoff",
        query_string=[
            ("reason_for_visit", "Persistent back pain for one week"),
            ("question", "What could I ask about next steps?"),
            ("question", "Do I need follow-up?"),
        ],
    )
    assert response.status_code == 200
    packet = response.get_json()["handoff_packet"]
    assert packet["clinical_interpretation"] is None
    assert packet["sharing"]["automatic_external_sharing"] is False
    assert packet["sharing"]["patient_controlled"] is True
    assert "does not diagnose" in packet["safety_notice"]
    assert len(packet["questions_for_clinician"]) == 2


def test_evidence_passport_never_invents_historical_sources(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "patient", "passport@example.com", "Passport Patient")
    login_web(client, "patient", "passport@example.com")
    with app.app_context():
        user = get_db().execute(
            "SELECT id FROM users WHERE email_normalized=?",
            ("passport@example.com",),
        ).fetchone()
        cursor = get_db().execute(
            """INSERT INTO ai_interactions
               (user_id,conversation_id,feature,intent,input_text,output_text,risk_level,model_version,provider,emergency,success,latency_ms,created_at)
               VALUES (?,NULL,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                user["id"], "zendoc_ai", "symptoms", "I have a headache", "Safe guidance",
                "low", "zendoc-test-model", "test-provider", 0, 1, 15, now_iso(),
            ),
        )
        interaction_id = int(cursor.lastrowid)
        get_db().commit()
    response = client.get(f"/api/v1/ai-evidence-passports/{interaction_id}")
    assert response.status_code == 200
    passport = response.get_json()["passport"]
    assert passport["generation"]["model_version"] == "zendoc-test-model"
    assert passport["source_level_evidence"]["status"] == "not_recorded"
    assert passport["source_level_evidence"]["sources"] == []
    assert "will not invent citations" in passport["source_level_evidence"]["notice"]
    assert passport["uncertainty"]["status"] == "not_calibrated"


def test_patient_cannot_read_another_users_ai_passport(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "patient", "owner@example.com", "Owner Patient")
    register_web(client, "patient", "other@example.com", "Other Patient")
    with app.app_context():
        other = get_db().execute(
            "SELECT id FROM users WHERE email_normalized=?",
            ("other@example.com",),
        ).fetchone()
        cursor = get_db().execute(
            """INSERT INTO ai_interactions
               (user_id,conversation_id,feature,intent,input_text,output_text,risk_level,model_version,provider,emergency,success,latency_ms,created_at)
               VALUES (?,NULL,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                other["id"], "zendoc_ai", "health_records", "test", "test",
                "low", "model", "provider", 0, 1, 1, now_iso(),
            ),
        )
        interaction_id = int(cursor.lastrowid)
        get_db().commit()
    login_web(client, "patient", "owner@example.com")
    assert client.get(f"/api/v1/ai-evidence-passports/{interaction_id}").status_code == 404
