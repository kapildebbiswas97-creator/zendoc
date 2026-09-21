from io import BytesIO
from pathlib import Path
import re

import pytest

from zendoc.call_signaling import create_call
from zendoc.connect import (
    create_communication_permission,
    list_communication_permissions,
    list_messages,
    revoke_communication_permission,
    send_message,
    start_conversation,
)
from zendoc.db import get_db
from zendoc.communication_policy import can_call
from zendoc.universal_search import search_all
from tests.test_milestone1 import csrf, login_web, make_app, register_web


ROOT = Path(__file__).resolve().parents[1]


def _user(app, email):
    with app.app_context():
        return dict(
            get_db().execute(
                "SELECT * FROM users WHERE email_normalized=?",
                (email.lower(),),
            ).fetchone()
        )


def _direct_patient_conversation(app, patient_a, patient_b):
    with app.app_context():
        return start_conversation(
            patient_a,
            {"target_user_id": patient_b["id"], "context_type": "direct"},
        )


def test_patient_header_is_grouped_and_universal_search_is_first_class():
    body = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")

    assert "<summary>Care</summary>" in body
    assert "<summary>Health Memory</summary>" in body
    assert "<summary>Connect</summary>" in body
    assert "<summary>Wellbeing</summary>" in body
    assert "global-search-popover" in body
    assert "Search care, records, messages, benefits" in body
    assert "Government OPD · ORS" in body


def test_shell_css_hardens_horizontal_overflow_and_megamenu_responsiveness():
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")

    assert "overflow-x: clip" in css
    assert ".nav-menu-mega" in css
    assert "width: min(1500px, 100%)" in css
    assert "@media (max-width: 960px)" in css


def test_product_wide_search_surfaces_care_memory_connect_and_benefits():
    government = search_all(None, "government opd ors")
    titles = {
        item["title"]
        for category in government["categories"]
        for item in category["items"]
    }
    assert "Government OPD · ORS" in titles

    benefits = search_all(None, "CareFin insurance benefit")
    titles = {
        item["title"]
        for category in benefits["categories"]
        for item in category["items"]
    }
    assert "Care Benefits · CareFin" in titles

    connect = search_all(None, "voice call message")
    titles = {
        item["title"]
        for category in connect["categories"]
        for item in category["items"]
    }
    assert "ZENDOC Connect" in titles


def test_health_memory_snapshot_surfaces_command_center_and_provenance(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "memory-command@example.com", "Memory Command")
    login_web(client, "patient", "memory-command@example.com")

    response = client.get("/health-summary")
    assert response.status_code == 200
    for marker in (
        b"Health Memory command center",
        b"Provider confirmed",
        b"Patient reported",
        b"Uploaded / measured",
        b"Care Journey",
        b"Privacy &amp; access",
    ):
        assert marker in response.data


def test_message_receipts_progress_from_delivered_to_read(tmp_path):
    app = make_app(tmp_path)
    client_a = app.test_client()
    client_b = app.test_client()
    register_web(client_a, "patient", "receipt-a@example.com", "Receipt A")
    register_web(client_b, "patient", "receipt-b@example.com", "Receipt B")
    patient_a = _user(app, "receipt-a@example.com")
    patient_b = _user(app, "receipt-b@example.com")
    conversation = _direct_patient_conversation(app, patient_a, patient_b)

    with app.app_context():
        sent = send_message(
            patient_a,
            conversation["id"],
            {"body": "Receipt truth test", "message_type": "text"},
        )
        assert sent["receipt_summary"]["status"] == "delivered"
        assert sent["receipt_summary"]["recipient_count"] == 1

        list_messages(patient_b, conversation["id"])
        sender_view = list_messages(patient_a, conversation["id"])
        message = next(item for item in sender_view if item["body"] == "Receipt truth test")
        assert message["receipt_summary"]["status"] == "read"
        assert message["receipt_summary"]["read_count"] == 1


def test_private_voice_note_upload_is_audio_and_community_stays_image_video_only(tmp_path):
    app = make_app(tmp_path)
    sender_client = app.test_client()
    recipient_client = app.test_client()
    register_web(sender_client, "patient", "voice-a@example.com", "Voice A")
    register_web(recipient_client, "patient", "voice-b@example.com", "Voice B")
    login_web(sender_client, "patient", "voice-a@example.com")
    sender = _user(app, "voice-a@example.com")
    recipient = _user(app, "voice-b@example.com")
    conversation = _direct_patient_conversation(app, sender, recipient)

    page = sender_client.get(f"/messages?conversation_id={conversation['id']}")
    token = csrf(page.data.decode())
    uploaded = sender_client.post(
        "/messages",
        data={
            "csrf_token": token,
            "action": "send",
            "conversation_id": str(conversation["id"]),
            "body": "",
            "message_type": "text",
            "media_file": (
                BytesIO(b"\x1aE\xdf\xa3voice-note-test"),
                "voice-note.webm",
                "audio/webm",
            ),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert uploaded.status_code == 200
    assert b"Message sent" in uploaded.data

    with app.app_context():
        row = get_db().execute(
            """
            SELECT m.id,m.message_type,ma.attachment_type,ma.metadata_json
            FROM messages m
            JOIN message_attachments ma ON ma.message_id=m.id
            WHERE m.conversation_id=? AND m.message_type='audio'
            ORDER BY m.id DESC LIMIT 1
            """,
            (conversation["id"],),
        ).fetchone()
        assert row is not None
        assert row["message_type"] == "audio"
        assert row["attachment_type"] == "audio"
        assert '"mime_type": "audio/webm"' in row["metadata_json"]

    community = sender_client.get("/community")
    community_token = csrf(community.data.decode())
    rejected = sender_client.post(
        "/community",
        data={
            "csrf_token": community_token,
            "action": "post",
            "lane": "wellness",
            "body": "This audio must not become a Community post.",
            "accept_guidelines": "1",
            "media_file": (
                BytesIO(b"\x1aE\xdf\xa3community-audio-test"),
                "community-audio.webm",
                "audio/webm",
            ),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert rejected.status_code == 200
    assert b"Community media must be JPEG, PNG, WebP, MP4, or WebM" in rejected.data

    with app.app_context():
        post = get_db().execute(
            "SELECT id FROM health_social_posts WHERE body=?",
            ("This audio must not become a Community post.",),
        ).fetchone()
        assert post is None


def test_messages_composer_has_real_voice_note_recording_and_receipt_ui():
    messages = (ROOT / "templates" / "messages.html").read_text(encoding="utf-8")
    bubbles = (ROOT / "templates" / "components" / "_message_bubbles.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "messages_composer.js").read_text(encoding="utf-8")

    assert "message-voice-note" in messages
    assert "audio/webm" in messages
    assert "MediaRecorder" in script
    assert "getUserMedia" in script
    assert "Nothing is sent automatically" in script
    assert "✓✓ Read" in bubbles
    assert "✓✓ Delivered" in bubbles
    assert "message-audio" in bubbles



def test_incoming_voice_call_is_visible_app_wide_and_rejectable(tmp_path):
    app = make_app(tmp_path)
    caller_client = app.test_client()
    callee_client = app.test_client()
    register_web(caller_client, "patient", "call-a@example.com", "Caller A")
    register_web(callee_client, "patient", "call-b@example.com", "Caller B")
    login_web(callee_client, "patient", "call-b@example.com")

    caller = _user(app, "call-a@example.com")
    callee = _user(app, "call-b@example.com")

    with app.app_context():
        conversation = start_conversation(
            caller,
            {"target_user_id": callee["id"], "context_type": "direct"},
        )
        with pytest.raises(PermissionError, match="target account"):
            create_communication_permission(
                caller,
                {
                    "requester_id": caller["id"],
                    "target_user_id": callee["id"],
                    "allow_voice": True,
                },
            )

        create_communication_permission(
            callee,
            {
                "requester_id": caller["id"],
                "target_user_id": callee["id"],
                "allow_chat": True,
                "allow_voice": True,
                "allow_video": False,
            },
        )
        assert can_call(caller, callee["id"])["allowed"] is True

        call = create_call(
            caller,
            conversation["id"],
            "voice",
            '{"type":"offer","sdp":"v=0\\r\\nZENDOC test offer"}',
        )

    incoming = callee_client.get("/calls/incoming")
    assert incoming.status_code == 200
    calls = incoming.get_json()["calls"]
    assert calls
    assert calls[0]["id"] == call["id"]
    assert calls[0]["initiator_name"] == "Caller A"
    assert calls[0]["call_type"] == "voice"

    call_page = callee_client.get(f"/calls/{call['id']}")
    assert call_page.status_code == 200
    assert b"Private browser call" in call_page.data
    assert b"Media path" in call_page.data
    assert b"Round trip" in call_page.data
    assert b"No call recording is implemented" in call_page.data

    token = csrf(call_page.data.decode())
    rejected = callee_client.post(
        f"/calls/{call['id']}/answer",
        data={"csrf_token": token, "accept": "0", "answer_json": ""},
    )
    assert rejected.status_code == 200
    assert rejected.get_json()["call"]["status"] == "rejected"


def test_call_ui_uses_real_peer_state_and_measured_diagnostics():
    base = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    call_template = (ROOT / "templates" / "call.html").read_text(encoding="utf-8")
    call_script = (ROOT / "static" / "calls.js").read_text(encoding="utf-8")
    incoming_script = (ROOT / "static" / "incoming_calls.js").read_text(encoding="utf-8")
    sw = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")

    assert "zendoc-incoming-call" in base
    assert "incoming_calls.js" in base
    assert "call-diagnostics" in call_template
    assert "pc.getStats()" in call_script
    assert "TURN relay" in call_script
    assert "Direct / STUN path" in call_script
    assert "currentRoundTripTime" in call_script
    assert "Reconnecting" in call_script
    assert "navigator.vibrate" in incoming_script
    match = re.search(r'const STATIC_CACHE = "zendoc-static-v(\d+)[^"]*";', sw)
    assert match is not None
    assert int(match.group(1)) >= 4
    assert 'zendoc-static-v1' not in sw
    assert 'zendoc-static-v2' not in sw
    assert 'zendoc-static-v3' not in sw
    assert '"/static/calls.js"' in sw
    assert '"/static/incoming_calls.js"' in sw
    assert '"/static/messages_composer.js"' in sw



def test_expired_explicit_call_permission_fails_closed(tmp_path):
    app = make_app(tmp_path)
    first = app.test_client()
    second = app.test_client()
    register_web(first, "patient", "expired-call-a@example.com", "Expired A")
    register_web(second, "patient", "expired-call-b@example.com", "Expired B")
    caller = _user(app, "expired-call-a@example.com")
    callee = _user(app, "expired-call-b@example.com")

    with app.app_context():
        create_communication_permission(
            callee,
            {
                "requester_id": caller["id"],
                "target_user_id": callee["id"],
                "allow_voice": True,
                "expires_at": "2020-01-01T00:00:00+00:00",
            },
        )
        decision = can_call(caller, callee["id"])
        assert decision["allowed"] is False
        assert "family consent" in decision["reason"].lower()



def test_explicit_permission_is_visible_and_revocable_by_either_participant(tmp_path):
    app = make_app(tmp_path)
    first = app.test_client()
    second = app.test_client()
    third = app.test_client()
    register_web(first, "patient", "grant-a@example.com", "Grant A")
    register_web(second, "patient", "grant-b@example.com", "Grant B")
    register_web(third, "patient", "grant-c@example.com", "Grant C")
    requester = _user(app, "grant-a@example.com")
    target = _user(app, "grant-b@example.com")
    outsider = _user(app, "grant-c@example.com")

    with app.app_context():
        conversation = start_conversation(
            requester,
            {"target_user_id": target["id"], "context_type": "direct"},
        )
        grant = create_communication_permission(
            target,
            {
                "requester_id": requester["id"],
                "target_user_id": target["id"],
                "allow_chat": True,
                "allow_voice": True,
                "allow_video": False,
                "allow_record_sharing": False,
            },
        )

        requester_view = list_communication_permissions(
            requester,
            related_user_id=target["id"],
        )
        target_view = list_communication_permissions(
            target,
            related_user_id=requester["id"],
        )
        assert requester_view[0]["id"] == grant["id"]
        assert requester_view[0]["effective"] is True
        assert target_view[0]["effective"] is True

        with pytest.raises(PermissionError, match="participant or admin"):
            revoke_communication_permission(outsider, grant["id"])

        revoked = revoke_communication_permission(requester, grant["id"])
        assert revoked["status"] == "revoked"
        assert revoked["revoked_at"]
        assert can_call(requester, target["id"])["allowed"] is False

    login_web(second, "patient", "grant-b@example.com")
    page = second.get(f"/messages?conversation_id={conversation['id']}")
    assert page.status_code == 200
    assert b"Explicit communication access" in page.data
    assert b"Grant A may contact Grant B" in page.data
    assert b"Revoked" in page.data


def test_communication_permission_api_rejects_self_grant_and_allows_target_revoke(tmp_path):
    app = make_app(tmp_path)
    requester_client = app.test_client()
    target_client = app.test_client()
    register_web(requester_client, "patient", "api-grant-a@example.com", "API Grant A")
    register_web(target_client, "patient", "api-grant-b@example.com", "API Grant B")
    requester = _user(app, "api-grant-a@example.com")
    target = _user(app, "api-grant-b@example.com")

    requester_token = requester_client.post(
        "/api/v1/auth/login",
        json={
            "email": "api-grant-a@example.com",
            "password": "StrongPass123",
            "role": "patient",
        },
    ).get_json()["token"]
    denied = requester_client.post(
        "/api/v1/communication-permissions",
        json={
            "requester_id": requester["id"],
            "target_user_id": target["id"],
            "allow_voice": True,
        },
        headers={"Authorization": f"Bearer {requester_token}"},
    )
    assert denied.status_code == 403
    assert "target account" in denied.get_json()["error"]["message"]

    target_token = target_client.post(
        "/api/v1/auth/login",
        json={
            "email": "api-grant-b@example.com",
            "password": "StrongPass123",
            "role": "patient",
        },
    ).get_json()["token"]
    granted = target_client.post(
        "/api/v1/communication-permissions",
        json={
            "requester_id": requester["id"],
            "target_user_id": target["id"],
            "allow_chat": True,
            "allow_voice": True,
        },
        headers={"Authorization": f"Bearer {target_token}"},
    )
    assert granted.status_code == 201
    permission_id = granted.get_json()["communication_permission"]["id"]

    visible = target_client.get(
        f"/api/v1/communication-permissions?related_user_id={requester['id']}",
        headers={"Authorization": f"Bearer {target_token}"},
    )
    assert visible.status_code == 200
    assert visible.get_json()["communication_permissions"][0]["effective"] is True

    revoked = target_client.post(
        f"/api/v1/communication-permissions/{permission_id}/revoke",
        headers={"Authorization": f"Bearer {target_token}"},
    )
    assert revoked.status_code == 200
    assert revoked.get_json()["communication_permission"]["status"] == "revoked"
