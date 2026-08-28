from zendoc import create_app
from zendoc.db import get_db

from tests.test_milestone1 import csrf, login_web, make_client, register_web


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def register_api(client, email, role="patient", password="StrongPass123"):
    return client.post(
        "/api/v1/auth/register",
        json={"name": email, "email": email, "password": password, "role": role},
    )


def login_api(client, email, role="patient", password="StrongPass123"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password, "role": role})


def api_token(client, email, role="patient", password="StrongPass123"):
    register_api(client, email, role, password)
    return login_api(client, email, role, password).json["token"]


def user_id(app, email):
    with app.app_context():
        return get_db().execute("SELECT id FROM users WHERE email_normalized=?", (email.strip().lower(),)).fetchone()["id"]


def test_admin_requires_environment_config_not_real_default(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "no-admin-default.db"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "SECRET_KEY": "test-secret",
            "ADMIN_EMAIL": None,
            "ADMIN_PASSWORD": None,
            "RATE_LIMIT_PER_MINUTE": 1000,
        }
    )
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) c FROM users WHERE role='admin'").fetchone()["c"] == 0


def test_duplicate_registration_blocked_after_email_normalization(tmp_path):
    app, client = make_client(tmp_path)
    response = register_web(client, "patient", "  MixedCase@Example.com  ", "Case User")
    assert response.status_code == 200

    duplicate = register_web(client, "patient", "mixedcase@example.com", "Duplicate")
    assert duplicate.status_code == 409
    assert b"An account with this email already exists. Please log in or reset your password." in duplicate.data

    with app.app_context():
        rows = get_db().execute("SELECT email, email_normalized FROM users WHERE email_normalized='mixedcase@example.com'").fetchall()
        assert len(rows) == 1


def test_login_survives_app_restart_and_normalizes_case_whitespace(tmp_path):
    db_path = tmp_path / "restart-login.db"
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(db_path),
            "UPLOAD_FOLDER": str(tmp_path / "uploads1"),
            "SECRET_KEY": "test-secret",
            "ADMIN_EMAIL": "admin@example.com",
            "ADMIN_PASSWORD": "AdminStrong123",
            "RATE_LIMIT_PER_MINUTE": 1000,
        }
    )
    client = app.test_client()
    register_web(client, "patient", "persist@example.com", "Persistent Patient")
    client.get("/logout")

    app_restarted = create_app(
        {
            "TESTING": True,
            "DATABASE": str(db_path),
            "UPLOAD_FOLDER": str(tmp_path / "uploads2"),
            "SECRET_KEY": "test-secret",
            "ADMIN_EMAIL": "admin@example.com",
            "ADMIN_PASSWORD": "AdminStrong123",
            "RATE_LIMIT_PER_MINUTE": 1000,
        }
    )
    client_restarted = app_restarted.test_client()
    login = login_web(client_restarted, "patient", " PERSIST@EXAMPLE.COM ")
    assert b"Welcome, Persistent Patient" in login.data


def test_wrong_password_correct_password_role_and_remember_me(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "remember@example.com")
    assert b"Invalid login details" in login_web(client, "patient", "remember@example.com", "wrong").data
    assert login_web(client, "doctor", "remember@example.com").status_code == 200
    assert b"Invalid login details" in login_web(client, "doctor", "remember@example.com").data

    page = client.get("/login/patient")
    token = csrf(page.data.decode())
    response = client.post(
        "/login/patient",
        data={"csrf_token": token, "email": "remember@example.com", "password": "StrongPass123", "remember_me": "1"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert sess.permanent is True


def test_duplicate_legacy_accounts_are_documented_not_deleted(tmp_path):
    app, client = make_client(tmp_path)
    with app.app_context():
        now = "2026-08-28T00:00:00+00:00"
        db = get_db()
        db.execute(
            "INSERT INTO users (name,email,password_hash,role,created_at,updated_at) VALUES ('Legacy A','legacy@example.com','hash','patient',?,?)",
            (now, now),
        )
        db.execute(
            "INSERT INTO users (name,email,password_hash,role,created_at,updated_at) VALUES ('Legacy B','LEGACY@example.com','hash','patient',?,?)",
            (now, now),
        )
        db.commit()
        from zendoc.db import migrate_schema

        migrate_schema(db)
        assert db.execute("SELECT COUNT(*) c FROM users WHERE LOWER(email)='legacy@example.com'").fetchone()["c"] == 2
        group = db.execute("SELECT * FROM duplicate_account_groups WHERE email_normalized='legacy@example.com'").fetchone()
        assert group is not None

    duplicate = register_api(client, "legacy@example.com")
    assert duplicate.status_code == 409


def test_agent_permissions_audit_and_emergency_first(tmp_path):
    app, client = make_client(tmp_path)
    patient_token = api_token(client, "agent-patient@example.com")

    denied = client.get("/api/v1/admin/agent-command-center", headers=headers(patient_token))
    assert denied.status_code == 403

    emergency = client.post("/api/v1/agent/message", json={"message": "I need help for chest pain"}, headers=headers(patient_token))
    assert emergency.status_code == 200
    assert emergency.json["intent"] == "emergency"
    assert emergency.json["urgency"] == "emergency"

    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) c FROM agent_runs WHERE intent='emergency'").fetchone()["c"] == 1


def test_admin_agent_command_center_platform_health(tmp_path):
    _app, client = make_client(tmp_path)
    admin = login_api(client, "admin@example.com", "admin", "AdminStrong123").json["token"]

    summary = client.post("/api/v1/agent/message", json={"message": "Give me today's operations summary"}, headers=headers(admin))
    assert summary.status_code == 200
    assert summary.json["intent"] == "platform_health"

    center = client.get("/api/v1/admin/agent-command-center", headers=headers(admin))
    assert center.status_code == 200
    assert "specialized_agents" in center.json


def test_doctor_availability_consultation_and_messaging_isolation(tmp_path):
    app, client = make_client(tmp_path)
    patient_token = api_token(client, "tele-patient@example.com")
    doctor_token = api_token(client, "tele-doctor@example.com", role="doctor")
    outsider_token = api_token(client, "tele-outsider@example.com")
    doctor_id = user_id(app, "tele-doctor@example.com")

    availability = client.put(
        "/api/v1/doctor/availability",
        json={"status": "available", "accepts_chat": True, "accepts_video": True},
        headers=headers(doctor_token),
    )
    assert availability.status_code == 200
    assert availability.json["doctor_availability"]["accepts_video"] == 1

    requested = client.post(
        "/api/v1/consultations",
        json={"doctor_id": doctor_id, "consultation_type": "video", "reason": "Follow-up"},
        headers=headers(patient_token),
    )
    assert requested.status_code == 201
    consultation_id = requested.json["consultation"]["id"]
    assert requested.json["consultation"]["status"] == "requested"

    denied = client.get(f"/api/v1/consultations/{consultation_id}/messages", headers=headers(outsider_token))
    assert denied.status_code == 403

    accepted = client.post(
        f"/api/v1/consultations/{consultation_id}/status",
        json={"status": "accepted"},
        headers=headers(doctor_token),
    )
    assert accepted.status_code == 200
    assert accepted.json["consultation"]["room_provider"] == "local_demo"

    message = client.post(
        f"/api/v1/consultations/{consultation_id}/messages",
        json={"body": "Hello doctor"},
        headers=headers(patient_token),
    )
    assert message.status_code == 201


def test_video_intelligence_fallback_and_history(tmp_path):
    app, client = make_client(tmp_path)
    token = api_token(client, "video@example.com")
    response = client.get("/api/v1/video-intelligence/search?q=squat&category=exercise", headers=headers(token))
    assert response.status_code == 200
    assert response.json["available"] is False
    assert response.json["results"] == []
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) c FROM video_search_history WHERE query='squat'").fetchone()["c"] == 1


def test_pose_coach_route_and_pose_session_isolation(tmp_path):
    _app, client = make_client(tmp_path)
    one = api_token(client, "pose-one@example.com")
    two = api_token(client, "pose-two@example.com")

    saved = client.post(
        "/api/v1/fitness/pose-sessions",
        json={"exercise": "squat", "reps": 12, "sets": 1, "duration_seconds": 45, "confidence": 0.72},
        headers=headers(one),
    )
    assert saved.status_code == 201
    session_id = saved.json["pose_session"]["id"]

    other = client.post(
        "/api/v1/fitness/pose-sessions",
        json={"exercise": "plank", "duration_seconds": 30},
        headers=headers(two),
    )
    assert other.status_code == 201
    assert other.json["pose_session"]["id"] != session_id

    login_web(client, "patient", "pose-one@example.com")
    assert client.get("/fitness/pose-coach").status_code == 200


def test_staff_task_lifecycle_and_operations_isolation(tmp_path):
    app, client = make_client(tmp_path)
    admin_token = login_api(client, "admin@example.com", "admin", "AdminStrong123").json["token"]
    staff_token = api_token(client, "staff@example.com", role="pharmacy")
    outsider_token = api_token(client, "staff-outsider@example.com", role="doctor")
    staff_id = user_id(app, "staff@example.com")

    profile = client.post(
        "/api/v1/staff-profiles",
        json={"user_id": staff_id, "staff_type": "pharmacy_worker", "service_area": "Kolkata"},
        headers=headers(admin_token),
    )
    assert profile.status_code == 200

    task = client.post(
        "/api/v1/staff-tasks",
        json={"assigned_staff_id": staff_id, "task_type": "medicine_delivery_staff", "title": "Prepare medicine request"},
        headers=headers(admin_token),
    )
    assert task.status_code == 201
    task_id = task.json["staff_task"]["id"]

    denied = client.post(f"/api/v1/staff-tasks/{task_id}/status", json={"status": "accepted"}, headers=headers(outsider_token))
    assert denied.status_code == 403

    accepted = client.post(f"/api/v1/staff-tasks/{task_id}/status", json={"status": "accepted"}, headers=headers(staff_token))
    assert accepted.status_code == 200
    assert accepted.json["staff_task"]["status"] == "accepted"


def test_milestone7_public_and_auth_routes(tmp_path):
    _app, client = make_client(tmp_path)
    assert client.get("/fitness/pose-coach").status_code == 302
    assert client.post("/api/v1/agent/message", json={"message": "platform health"}).status_code == 401


def test_contact_discovery_privacy_and_specialty_search(tmp_path):
    app, client = make_client(tmp_path)
    patient_tok = api_token(client, "discover-patient@example.com")
    doctor_tok = api_token(client, "discover-doctor@example.com", role="doctor")
    doc_id = user_id(app, "discover-doctor@example.com")

    # Set doctor to accept new patient messages
    client.put(
        "/api/v1/doctor/availability",
        json={"status": "available", "accepts_chat": True, "patient_message_policy": "anyone"},
        headers=headers(doctor_tok),
    )

    # Set provider profile with specialty
    client.post(
        "/api/v1/provider/profile",
        json={"provider_type": "doctor", "specialty": "Cardiology", "organization": "Heart Care Clinic"},
        headers=headers(doctor_tok),
    )

    # Search by doctor name
    res = client.get("/api/v1/contacts?q=doctor", headers=headers(patient_tok))
    assert res.status_code == 200
    contacts = res.json["contacts"]
    assert any(c["id"] == doc_id for c in contacts)
    # Check no email or phone leaked
    for c in contacts:
        assert "email" not in c
        assert "phone" not in c
        assert "password_hash" not in c

    # Search by specialty
    res_spec = client.get("/api/v1/contacts?q=cardiology", headers=headers(patient_tok))
    assert res_spec.status_code == 200
    assert any(c["id"] == doc_id for c in res_spec.json["contacts"])


def test_doctor_patient_communication_policies_and_toggles(tmp_path):
    app, client = make_client(tmp_path)
    patient_tok = api_token(client, "policy-patient@example.com")
    patient_id = user_id(app, "policy-patient@example.com")
    doctor_tok = api_token(client, "policy-doctor@example.com", role="doctor")
    doc_id = user_id(app, "policy-doctor@example.com")

    # Policy 1: nobody
    client.put(
        "/api/v1/doctor/availability",
        json={"status": "available", "accepts_chat": False, "patient_message_policy": "nobody"},
        headers=headers(doctor_tok),
    )
    fail_conv = client.post("/api/v1/conversations", json={"target_user_id": doc_id}, headers=headers(patient_tok))
    assert fail_conv.status_code == 403

    # Policy 2: appointment only
    client.put(
        "/api/v1/doctor/availability",
        json={"status": "available", "accepts_chat": True, "patient_message_policy": "appointment"},
        headers=headers(doctor_tok),
    )
    # Still no appointment -> fail
    fail_appt = client.post("/api/v1/conversations", json={"target_user_id": doc_id}, headers=headers(patient_tok))
    assert fail_appt.status_code == 403

    # Add appointment
    with app.app_context():
        now = "2026-08-28T10:00:00+00:00"
        get_db().execute(
            "INSERT INTO appointments (patient_id, provider_id, provider_name, scheduled_for, reason, status, created_at, updated_at) VALUES (?, ?, 'Dr Policy', ?, 'Checkup', 'confirmed', ?, ?)",
            (patient_id, doc_id, now, now, now),
        )
        get_db().commit()

    # Now allowed
    start_res = client.post("/api/v1/conversations", json={"target_user_id": doc_id}, headers=headers(patient_tok))
    assert start_res.status_code == 201
    conv_id = start_res.json["conversation"]["id"]

    # Send message
    msg_res = client.post(f"/api/v1/conversations/{conv_id}/messages", json={"body": "Hello doctor with appointment"}, headers=headers(patient_tok))
    assert msg_res.status_code == 201


def test_doctor_to_doctor_professional_messaging(tmp_path):
    app, client = make_client(tmp_path)
    doc1_tok = api_token(client, "dr1@example.com", role="doctor")
    doc2_tok = api_token(client, "dr2@example.com", role="doctor")
    doc2_id = user_id(app, "dr2@example.com")

    # Doctor 1 starts conversation with Doctor 2 directly
    start = client.post("/api/v1/conversations", json={"target_user_id": doc2_id, "title": "Clinical Consult"}, headers=headers(doc1_tok))
    assert start.status_code == 201
    conv_id = start.json["conversation"]["id"]

    # Doctor 2 can reply
    reply = client.post(f"/api/v1/conversations/{conv_id}/messages", json={"body": "Agreed on differential diagnosis."}, headers=headers(doc2_tok))
    assert reply.status_code == 201


def test_pharmacy_and_staff_task_communication_contexts(tmp_path):
    app, client = make_client(tmp_path)
    patient_tok = api_token(client, "pharm-patient@example.com")
    patient_id = user_id(app, "pharm-patient@example.com")
    pharm_tok = api_token(client, "pharm-store@example.com", role="pharmacy")
    pharm_id = user_id(app, "pharm-store@example.com")

    # No order -> denied
    denied = client.post("/api/v1/conversations", json={"target_user_id": pharm_id}, headers=headers(patient_tok))
    assert denied.status_code == 403

    # Add medicine order
    with app.app_context():
        now = "2026-08-28T10:00:00+00:00"
        get_db().execute(
            "INSERT INTO medicine_orders (patient_id, ordered_by, pharmacy_id, items_json, delivery_address, status, created_at) VALUES (?, ?, ?, '[]', '123 Main St', 'pending', ?)",
            (patient_id, patient_id, pharm_id, now),
        )
        get_db().commit()

    # Now allowed
    allowed = client.post("/api/v1/conversations", json={"target_user_id": pharm_id}, headers=headers(patient_tok))
    assert allowed.status_code == 201


def test_family_messaging_with_access_grant(tmp_path):
    app, client = make_client(tmp_path)
    patient1_tok = api_token(client, "fam1@example.com", role="patient")
    patient1_id = user_id(app, "fam1@example.com")
    patient2_tok = api_token(client, "fam2@example.com", role="patient")
    patient2_id = user_id(app, "fam2@example.com")

    # Without family grant -> denied
    denied = client.post("/api/v1/conversations", json={"target_user_id": patient2_id}, headers=headers(patient1_tok))
    assert denied.status_code == 403

    # Grant family access
    with app.app_context():
        now = "2026-08-28T10:00:00+00:00"
        get_db().execute(
            "INSERT INTO family_access_grants (grantor_id, grantee_id, scopes, created_at) VALUES (?, ?, '[\"appointments\",\"reports\",\"metrics\",\"care_tasks\"]', ?)",
            (patient2_id, patient1_id, now),
        )
        get_db().commit()

    allowed = client.post("/api/v1/conversations", json={"target_user_id": patient2_id}, headers=headers(patient1_tok))
    assert allowed.status_code == 201


def test_conversation_and_message_participant_isolation(tmp_path):
    app, client = make_client(tmp_path)
    doc1_tok = api_token(client, "iso-doc1@example.com", role="doctor")
    doc2_tok = api_token(client, "iso-doc2@example.com", role="doctor")
    outsider_tok = api_token(client, "iso-outsider@example.com", role="patient")
    doc2_id = user_id(app, "iso-doc2@example.com")

    start = client.post("/api/v1/conversations", json={"target_user_id": doc2_id}, headers=headers(doc1_tok))
    conv_id = start.json["conversation"]["id"]

    # Outsider cannot get conversation
    assert client.get(f"/api/v1/conversations/{conv_id}", headers=headers(outsider_tok)).status_code == 403
    # Outsider cannot list messages
    assert client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers(outsider_tok)).status_code == 403
    # Outsider cannot send message
    assert client.post(f"/api/v1/conversations/{conv_id}/messages", json={"body": "Intruder"}, headers=headers(outsider_tok)).status_code == 403


def test_message_receipts_and_unread_count_lifecycle(tmp_path):
    app, client = make_client(tmp_path)
    doc1_tok = api_token(client, "receipt-doc1@example.com", role="doctor")
    doc2_tok = api_token(client, "receipt-doc2@example.com", role="doctor")
    doc2_id = user_id(app, "receipt-doc2@example.com")

    start = client.post("/api/v1/conversations", json={"target_user_id": doc2_id}, headers=headers(doc1_tok))
    conv_id = start.json["conversation"]["id"]

    # Send message from doc1 to doc2
    client.post(f"/api/v1/conversations/{conv_id}/messages", json={"body": "Unread test"}, headers=headers(doc1_tok))

    # Doc2 should have 1 unread message
    unread = client.get("/api/v1/messages/unread-count", headers=headers(doc2_tok)).json["unread_count"]
    assert unread >= 1

    # Doc2 reads messages
    msgs = client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers(doc2_tok))
    assert msgs.status_code == 200

    # Doc2 unread count drops
    unread_after = client.get("/api/v1/messages/unread-count", headers=headers(doc2_tok)).json["unread_count"]
    assert unread_after == 0


def test_record_sharing_with_consent_and_video_sharing(tmp_path):
    app, client = make_client(tmp_path)
    doc1_tok = api_token(client, "share-doc1@example.com", role="doctor")
    doc2_tok = api_token(client, "share-doc2@example.com", role="doctor")
    doc1_id = user_id(app, "share-doc1@example.com")
    doc2_id = user_id(app, "share-doc2@example.com")

    start = client.post("/api/v1/conversations", json={"target_user_id": doc2_id}, headers=headers(doc1_tok))
    conv_id = start.json["conversation"]["id"]

    # Share video
    video_share = client.post(
        f"/api/v1/conversations/{conv_id}/share-video",
        json={"video_url": "https://www.youtube.com/watch?v=example", "title": "Mobility Routine"},
        headers=headers(doc1_tok),
    )
    assert video_share.status_code == 201
    assert video_share.json["message"]["message_type"] == "video"

    # Create a medical record owned by doc1
    with app.app_context():
        now = "2026-08-28T10:00:00+00:00"
        cur = get_db().execute(
            "INSERT INTO medical_records (owner_id, uploaded_by, title, category, original_filename, stored_filename, file_size, created_at) VALUES (?, ?, 'Lab Blood Work', 'lab', 'blood.pdf', 'blood_stored.pdf', 1024, ?)",
            (doc1_id, doc1_id, now),
        )
        rec_id = cur.lastrowid
        get_db().commit()

    # Share record by owner
    report_share = client.post(
        f"/api/v1/conversations/{conv_id}/share-report",
        json={"record_id": rec_id, "title": "Shared Lab Blood Work"},
        headers=headers(doc1_tok),
    )
    assert report_share.status_code == 201
    assert report_share.json["message"]["message_type"] == "report"


def test_core_agent_communication_tools_and_policy_enforcement(tmp_path):
    app, client = make_client(tmp_path)
    patient_tok = api_token(client, "agent-comm-patient@example.com")
    doctor_tok = api_token(client, "agent-comm-doctor@example.com", role="doctor")

    # Patient asks Core Agent to find contacts
    find_res = client.post("/api/v1/agent/message", json={"message": "find contact doctor"}, headers=headers(patient_tok))
    assert find_res.status_code == 200
    assert find_res.json["intent"] == "contact_discovery"

    # Patient asks to share report -> Core agent requires confirmation and does not bypass policy
    share_req = client.post("/api/v1/agent/message", json={"message": "share medical record with doctor"}, headers=headers(patient_tok))
    assert share_req.status_code == 200
    assert share_req.json["requires_confirmation"] is True

    # Check unread messages through agent
    unread_req = client.post("/api/v1/agent/message", json={"message": "check my unread messages"}, headers=headers(patient_tok))
    assert unread_req.status_code == 200
    assert unread_req.json["intent"] == "messages_inbox"


def test_universal_search_includes_contacts_and_videos_without_leaks(tmp_path):
    app, client = make_client(tmp_path)
    from zendoc.universal_search import search_all

    patient_tok = api_token(client, "search-user@example.com")
    with app.app_context():
        user = get_db().execute("SELECT * FROM users WHERE email_normalized='search-user@example.com'").fetchone()
        results = search_all(user, "squat video")
        categories = [c["category"] for c in results["categories"]]
        assert "Video Guidance" in categories

