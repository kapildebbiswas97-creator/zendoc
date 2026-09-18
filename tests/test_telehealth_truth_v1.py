from tests.legacy_milestone7 import api_token, headers, user_id
from tests.test_milestone1 import login_web, make_client, register_web
from zendoc.db import get_db, now_iso


def _verify_doctor(app, email):
    with app.app_context():
        db = get_db()
        doctor = db.execute("SELECT * FROM users WHERE email_normalized=?", (email,)).fetchone()
        stamp = now_iso()
        db.execute(
            """
            INSERT INTO provider_profiles
            (user_id,provider_type,specialty,organization,verification_status,created_at,updated_at)
            VALUES (?,'doctor','General Medicine','Truth Clinic','verified',?,?)
            """,
            (doctor["id"], stamp, stamp),
        )
        db.commit()
        return int(doctor["id"])


def test_local_telehealth_rejects_unavailable_voice_and_video(tmp_path):
    app, client = make_client(tmp_path)
    patient_token = api_token(client, "truth-tele-patient@example.com")
    doctor_token = api_token(client, "truth-tele-doctor@example.com", role="doctor")
    doctor_id = user_id(app, "truth-tele-doctor@example.com")

    video_availability = client.put(
        "/api/v1/doctor/availability",
        json={"status": "available", "accepts_chat": True, "accepts_video": True},
        headers=headers(doctor_token),
    )
    assert video_availability.status_code == 400
    assert "Video telehealth is not available" in video_availability.get_json()["error"]["message"]

    for channel in ("voice", "video"):
        response = client.post(
            "/api/v1/consultations",
            json={"doctor_id": doctor_id, "consultation_type": channel, "reason": "Follow-up"},
            headers=headers(patient_token),
        )
        assert response.status_code == 400
        assert f"{channel.title()} telehealth is not available" in response.get_json()["error"]["message"]

    chat = client.post(
        "/api/v1/consultations",
        json={"doctor_id": doctor_id, "consultation_type": "chat", "reason": "Follow-up"},
        headers=headers(patient_token),
    )
    assert chat.status_code == 201
    assert chat.get_json()["consultation"]["consultation_type"] == "chat"


def test_patient_telehealth_page_hides_unsupported_media_channels(tmp_path):
    app, client = make_client(tmp_path)
    doctor_email = "truth-web-doctor@example.com"
    patient_email = "truth-web-patient@example.com"

    register_web(client, "doctor", doctor_email, "Truth Web Doctor")
    client.get("/logout")
    _verify_doctor(app, doctor_email)

    register_web(client, "patient", patient_email, "Truth Web Patient")
    login_web(client, "patient", patient_email)

    response = client.get("/telehealth")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Secure chat" in body
    assert 'value="voice"' not in body
    assert 'value="video"' not in body
    assert "production voice/video WebRTC is Integration Required" in body
