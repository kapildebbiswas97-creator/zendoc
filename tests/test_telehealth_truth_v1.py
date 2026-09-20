from tests.legacy_milestone7 import api_token, headers, user_id
from tests.test_milestone1 import csrf, login_web, make_client, register_web
from zendoc.db import get_db, now_iso


def _verify_doctor(app, email):
    with app.app_context():
        db = get_db()
        doctor = db.execute("SELECT * FROM users WHERE email_normalized=?", (email,)).fetchone()
        stamp = now_iso()
        existing = db.execute("SELECT id FROM provider_profiles WHERE user_id=?", (doctor["id"],)).fetchone()
        if existing:
            db.execute(
                "UPDATE provider_profiles SET verification_status='verified',updated_at=? WHERE user_id=?",
                (stamp, doctor["id"]),
            )
        else:
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


def test_internal_webrtc_telehealth_allows_declared_voice_and_video(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENDOC_TELEHEALTH_PROVIDER","internal_webrtc")
    app, client = make_client(tmp_path)
    patient_token = api_token(client, "truth-tele-patient@example.com")
    doctor_token = api_token(client, "truth-tele-doctor@example.com", role="doctor")
    doctor_id = _verify_doctor(app, "truth-tele-doctor@example.com")

    availability = client.put(
        "/api/v1/doctor/availability",
        json={
            "status": "available",
            "accepts_chat": True,
            "accepts_voice": True,
            "accepts_video": True,
            "allow_voice_requests": True,
            "allow_video_requests": True,
            "allow_new_consultation_requests": True,
        },
        headers=headers(doctor_token),
    )
    assert availability.status_code == 200

    for channel in ("voice", "video"):
        response = client.post(
            "/api/v1/consultations",
            json={"doctor_id": doctor_id, "consultation_type": channel, "reason": "Follow-up"},
            headers=headers(patient_token),
        )
        assert response.status_code == 201
        assert response.get_json()["consultation"]["consultation_type"] == channel

    chat = client.post(
        "/api/v1/consultations",
        json={"doctor_id": doctor_id, "consultation_type": "chat", "reason": "Follow-up"},
        headers=headers(patient_token),
    )
    assert chat.status_code == 201


def test_patient_telehealth_page_exposes_webrtc_beta_channels(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENDOC_TELEHEALTH_PROVIDER","internal_webrtc")
    app, client = make_client(tmp_path)
    doctor_email = "truth-web-doctor@example.com"
    patient_email = "truth-web-patient@example.com"

    register_web(client, "doctor", doctor_email, "Truth Web Doctor")
    client.get("/logout")
    _verify_doctor(app, doctor_email)

    login_web(client, "doctor", doctor_email)
    doctor_page = client.get("/doctor/availability")
    token = csrf(doctor_page.data.decode())
    saved = client.post(
        "/doctor/availability",
        data={
            "csrf_token": token,
            "status": "available",
            "accepts_chat": "1",
            "accepts_voice": "1",
            "accepts_video": "1",
            "allow_voice_requests": "1",
            "allow_video_requests": "1",
            "allow_new_consultation_requests": "1",
            "patient_message_policy": "accepted_consultation",
        },
        follow_redirects=True,
    )
    assert saved.status_code == 200

    client.get("/logout")
    register_web(client, "patient", patient_email, "Truth Web Patient")
    login_web(client, "patient", patient_email)

    response = client.get("/telehealth")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Secure chat" in body
    assert 'value="voice"' in body
    assert 'value="video"' in body
    assert "authenticated browser WebRTC voice/video are available" in body


def test_accepted_video_consultation_opens_real_connect_call_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENDOC_TELEHEALTH_PROVIDER","internal_webrtc")
    app, client = make_client(tmp_path)
    patient_email = "tele-video-patient@example.com"
    doctor_email = "tele-video-doctor@example.com"

    register_web(client, "doctor", doctor_email, "Tele Video Doctor")
    client.get("/logout")
    doctor_id = _verify_doctor(app, doctor_email)
    login_web(client, "doctor", doctor_email)
    doctor_page = client.get("/doctor/availability")
    token = csrf(doctor_page.data.decode())
    client.post(
        "/doctor/availability",
        data={
            "csrf_token": token,
            "status": "available",
            "accepts_chat": "1",
            "accepts_video": "1",
            "allow_video_requests": "1",
            "allow_new_consultation_requests": "1",
            "patient_message_policy": "accepted_consultation",
        },
        follow_redirects=True,
    )
    client.get("/logout")

    register_web(client, "patient", patient_email, "Tele Video Patient")
    login_web(client, "patient", patient_email)
    tele_page = client.get("/telehealth")
    token = csrf(tele_page.data.decode())
    requested = client.post(
        "/telehealth",
        data={
            "csrf_token": token,
            "action": "request_consultation",
            "doctor_id": doctor_id,
            "consultation_type": "video",
            "reason": "Follow-up video consultation",
        },
        follow_redirects=True,
    )
    assert requested.status_code == 200

    with app.app_context():
        consultation_id = int(
            get_db().execute(
                "SELECT id FROM consultation_requests WHERE doctor_id=? ORDER BY id DESC LIMIT 1",
                (doctor_id,),
            ).fetchone()["id"]
        )

    client.get("/logout")
    login_web(client, "doctor", doctor_email)
    detail_page = client.get(f"/telehealth/{consultation_id}")
    assert detail_page.status_code == 200
    token = csrf(detail_page.data.decode())
    accepted = client.post(
        "/telehealth",
        data={
            "csrf_token": token,
            "action": "update_status",
            "consultation_id": consultation_id,
            "status": "accepted",
        },
        follow_redirects=True,
    )
    assert accepted.status_code == 200

    detail_after = client.get(f"/telehealth/{consultation_id}")
    html = detail_after.get_data(as_text=True)
    assert "ZENDOC Connect consultation room" in html
    assert "Start video call" in html
    assert "/calls/start/" in html
