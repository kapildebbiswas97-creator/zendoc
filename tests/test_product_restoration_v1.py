from zendoc.db import get_db
from tests.test_milestone1 import csrf, login_web, make_app, register_web


def test_mental_wellness_private_history_and_journal(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "wellness-owner@example.com", "Wellness Owner")
    login_web(client, "patient", "wellness-owner@example.com")

    page = client.get("/mental-wellness")
    assert page.status_code == 200
    token = csrf(page.data.decode())
    saved = client.post(
        "/mental-wellness",
        data={
            "csrf_token": token,
            "action": "checkin",
            "mood_level": "7",
            "stress_level": "4",
            "energy_level": "6",
            "sleep_quality": "8",
            "note": "A calmer day.",
        },
        follow_redirects=True,
    )
    assert saved.status_code == 200
    assert b"Private wellbeing check-in saved." in saved.data
    assert b"Mood 7/10" in saved.data

    token = csrf(saved.data.decode())
    journal = client.post(
        "/mental-wellness",
        data={
            "csrf_token": token,
            "action": "journal",
            "title": "Private reflection",
            "body": "This belongs only to my account.",
        },
        follow_redirects=True,
    )
    assert journal.status_code == 200
    assert b"Private journal entry saved." in journal.data
    assert b"This belongs only to my account." in journal.data

    with app.app_context():
        row = get_db().execute(
            "SELECT id,user_id FROM mental_wellness_journal WHERE title=?",
            ("Private reflection",),
        ).fetchone()
        assert row is not None
        entry_id = int(row["id"])

    other = app.test_client()
    register_web(other, "patient", "wellness-other@example.com", "Wellness Other")
    login_web(other, "patient", "wellness-other@example.com")
    other_page = other.get("/mental-wellness")
    assert b"This belongs only to my account." not in other_page.data

    other_token = csrf(other_page.data.decode())
    denied = other.post(
        "/mental-wellness",
        data={"csrf_token": other_token, "action": "delete_journal", "entry_id": entry_id},
        follow_redirects=True,
    )
    assert b"Private journal entry not found." in denied.data

    owner_page = client.get("/mental-wellness")
    owner_token = csrf(owner_page.data.decode())
    deleted = client.post(
        "/mental-wellness",
        data={"csrf_token": owner_token, "action": "delete_journal", "entry_id": entry_id},
        follow_redirects=True,
    )
    assert b"Private journal entry deleted." in deleted.data


def test_community_save_share_and_author_delete(tmp_path):
    app = make_app(tmp_path)
    author = app.test_client()
    viewer = app.test_client()
    register_web(author, "patient", "social-author@example.com", "Social Author")
    register_web(viewer, "patient", "social-viewer@example.com", "Social Viewer")
    login_web(author, "patient", "social-author@example.com")
    login_web(viewer, "patient", "social-viewer@example.com")

    page = author.get("/community")
    token = csrf(page.data.decode())
    created = author.post(
        "/community",
        data={
            "csrf_token": token,
            "action": "post",
            "lane": "fitness",
            "body": "A real community post for save and share testing.",
            "accept_guidelines": "1",
        },
        follow_redirects=True,
    )
    assert created.status_code == 200
    with app.app_context():
        post_id = int(get_db().execute(
            "SELECT id FROM health_social_posts WHERE body=?",
            ("A real community post for save and share testing.",),
        ).fetchone()["id"])

    viewer_page = viewer.get("/community")
    viewer_token = csrf(viewer_page.data.decode())
    saved = viewer.post(
        "/community",
        data={"csrf_token": viewer_token, "action": "save", "post_id": post_id},
        follow_redirects=True,
    )
    assert b"Post saved." in saved.data
    saved_feed = viewer.get("/community?mode=saved")
    assert b"A real community post for save and share testing." in saved_feed.data

    detail = viewer.get(f"/community/posts/{post_id}")
    assert detail.status_code == 200
    assert b"A stable page you can share" in detail.data

    viewer_token = csrf(saved.data.decode())
    forbidden = viewer.post(
        "/community",
        data={"csrf_token": viewer_token, "action": "delete_post", "post_id": post_id},
        follow_redirects=True,
    )
    assert b"You can only delete your own community posts." in forbidden.data

    author_page = author.get("/community")
    author_token = csrf(author_page.data.decode())
    removed = author.post(
        "/community",
        data={"csrf_token": author_token, "action": "delete_post", "post_id": post_id},
        follow_redirects=True,
    )
    assert b"Your community post was deleted." in removed.data
    assert viewer.get(f"/community/posts/{post_id}").status_code == 404



def test_native_message_media_is_participant_protected(tmp_path):
    from io import BytesIO

    app = make_app(tmp_path)
    sender = app.test_client()
    receiver = app.test_client()
    stranger = app.test_client()
    register_web(sender, "patient", "media-sender@example.com", "Media Sender")
    register_web(receiver, "patient", "media-receiver@example.com", "Media Receiver")
    register_web(stranger, "patient", "media-stranger@example.com", "Media Stranger")
    login_web(sender, "patient", "media-sender@example.com")
    login_web(receiver, "patient", "media-receiver@example.com")
    login_web(stranger, "patient", "media-stranger@example.com")

    with app.app_context():
        receiver_id = int(get_db().execute(
            "SELECT id FROM users WHERE email_normalized=?",
            ("media-receiver@example.com",),
        ).fetchone()["id"])

    page = sender.get("/messages?q=Media+Receiver")
    token = csrf(page.data.decode())
    started = sender.post(
        "/messages",
        data={
            "csrf_token": token,
            "action": "start",
            "target_user_id": receiver_id,
            "context_type": "direct",
        },
        follow_redirects=False,
    )
    assert started.status_code == 302
    conversation_id = int(started.headers["Location"].rsplit("=", 1)[-1])

    page = sender.get(f"/messages?conversation_id={conversation_id}")
    token = csrf(page.data.decode())
    png = b"\x89PNG\r\n\x1a\n" + (b"zendoc-private-message-media" * 8)
    sent = sender.post(
        "/messages",
        data={
            "csrf_token": token,
            "action": "send",
            "conversation_id": conversation_id,
            "body": "Private image",
            "media_file": (BytesIO(png), "private.png", "image/png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert sent.status_code == 200
    assert b"Private image" in sent.data

    with app.app_context():
        attachment = get_db().execute(
            """
            SELECT ma.id
            FROM message_attachments ma
            JOIN messages m ON m.id=ma.message_id
            WHERE m.conversation_id=? AND ma.attachment_type='image'
            ORDER BY ma.id DESC LIMIT 1
            """,
            (conversation_id,),
        ).fetchone()
        assert attachment is not None
        attachment_id = int(attachment["id"])

    assert sender.get(f"/messages/media/{attachment_id}").status_code == 200
    assert receiver.get(f"/messages/media/{attachment_id}").status_code == 200
    assert stranger.get(f"/messages/media/{attachment_id}").status_code == 404


def test_owner_commerce_metrics_are_click_only(tmp_path):
    app = make_app(tmp_path)
    patient = app.test_client()
    register_web(patient, "patient", "shop-click@example.com", "Shop Click")
    login_web(patient, "patient", "shop-click@example.com")

    response = patient.get(
        "/health-shop/out/amazon_india?q=yoga+mat&category=fitness",
        follow_redirects=False,
    )
    assert response.status_code == 302

    owner = app.test_client()
    login_web(owner, "admin", "admin@example.com", "AdminStrong123")
    page = owner.get("/admin/commerce-referrals")
    assert page.status_code == 200
    assert b"Outbound clicks" in page.data
    assert b"do not prove an order, conversion or commission" in page.data



def test_webrtc_call_signaling_is_authorized_and_private(tmp_path):
    from zendoc.db import now_iso

    app = make_app(tmp_path)
    caller = app.test_client()
    callee = app.test_client()
    stranger = app.test_client()
    register_web(caller, "patient", "call-caller@example.com", "Call Caller")
    register_web(callee, "patient", "call-callee@example.com", "Call Callee")
    register_web(stranger, "patient", "call-stranger@example.com", "Call Stranger")
    login_web(caller, "patient", "call-caller@example.com")
    login_web(callee, "patient", "call-callee@example.com")
    login_web(stranger, "patient", "call-stranger@example.com")

    with app.app_context():
        db = get_db()
        caller_id = int(db.execute(
            "SELECT id FROM users WHERE email_normalized=?",
            ("call-caller@example.com",),
        ).fetchone()["id"])
        callee_id = int(db.execute(
            "SELECT id FROM users WHERE email_normalized=?",
            ("call-callee@example.com",),
        ).fetchone()["id"])

    page = caller.get("/messages?q=Call+Callee")
    token = csrf(page.data.decode())
    started = caller.post(
        "/messages",
        data={
            "csrf_token": token,
            "action": "start",
            "target_user_id": callee_id,
            "context_type": "direct",
        },
        follow_redirects=False,
    )
    conversation_id = int(started.headers["Location"].rsplit("=", 1)[-1])

    # Voice/video is intentionally stricter than text chat.
    denied_page = caller.get(f"/calls/start/{conversation_id}/voice")
    assert denied_page.status_code == 403

    with app.app_context():
        now = now_iso()
        get_db().execute(
            """
            INSERT INTO communication_permissions
            (requester_id,target_user_id,context_type,context_id,allow_chat,allow_voice,allow_video,
             allow_record_sharing,status,created_by,expires_at,revoked_at,created_at,updated_at)
            VALUES (?,?, 'direct', NULL,1,1,1,0,'active',?,NULL,NULL,?,?)
            """,
            (caller_id, callee_id, caller_id, now, now),
        )
        get_db().commit()

    call_page = caller.get(f"/calls/start/{conversation_id}/voice")
    assert call_page.status_code == 200
    caller_token = token
    created = caller.post(
        "/calls/create",
        data={
            "csrf_token": caller_token,
            "conversation_id": conversation_id,
            "call_type": "voice",
            "offer_json": '{"type":"offer","sdp":"v=0\\r\\no=zendoc-offer"}',
        },
    )
    assert created.status_code == 201
    call_id = int(created.get_json()["call"]["id"])

    incoming = callee.get("/messages")
    assert incoming.status_code == 200
    assert b"Incoming calls" in incoming.data
    assert b"Call Caller" in incoming.data
    callee_token = csrf(incoming.data.decode())

    assert stranger.get(f"/calls/{call_id}/state").status_code == 403
    assert stranger.get(f"/calls/{call_id}").status_code == 404

    callee_page = callee.get(f"/calls/{call_id}")
    assert callee_page.status_code == 200
    answered = callee.post(
        f"/calls/{call_id}/answer",
        data={
            "csrf_token": callee_token,
            "accept": "1",
            "answer_json": '{"type":"answer","sdp":"v=0\\r\\no=zendoc-answer"}',
        },
    )
    assert answered.status_code == 200
    assert answered.get_json()["call"]["status"] == "accepted"

    caller_page = caller.get(f"/calls/{call_id}")
    assert caller_page.status_code == 200
    candidate = caller.post(
        f"/calls/{call_id}/ice",
        data={
            "csrf_token": caller_token,
            "candidate_json": '{"candidate":"candidate:1 1 UDP 1 192.0.2.1 12345 typ host","sdpMid":"0","sdpMLineIndex":0}',
        },
    )
    assert candidate.status_code == 201

    state = callee.get(f"/calls/{call_id}/state")
    assert state.status_code == 200
    assert state.get_json()["call"]["status"] == "accepted"
    assert state.get_json()["call"]["answer"]["type"] == "answer"
    assert state.get_json()["call"]["candidates"]

    ended = caller.post(
        f"/calls/{call_id}/end",
        data={"csrf_token": caller_token},
    )
    assert ended.status_code == 200
    assert ended.get_json()["call"]["status"] == "ended"
