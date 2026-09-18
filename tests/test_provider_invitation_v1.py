import re

from tests.test_milestone1 import csrf, login_web, make_client
from zendoc.db import get_db


def _token_from_mail(text):
    match = re.search(r"[?&]token=([A-Za-z0-9_\-]+)", text)
    assert match, text
    return match.group(1)


def test_owner_can_invite_provider_and_acceptance_remains_unverified(tmp_path, monkeypatch):
    app, client = make_client(tmp_path)
    app.config.update(
        EMAIL_PROVIDER="smtp",
        SMTP_HOST="smtp.example.test",
        SMTP_FROM_EMAIL="noreply@zendoc.example.test",
        SMTP_USE_TLS=True,
        PUBLIC_BASE_URL="https://zendoc.example.test",
    )

    sent = []
    from zendoc import routes
    monkeypatch.setattr(
        routes,
        "send_transactional_email",
        lambda to_email, subject, text_body: sent.append((to_email, subject, text_body)) or {"status": "sent"},
    )

    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    admin = client.get("/admin")
    token = csrf(admin.get_data(as_text=True))
    invited = client.post(
        "/admin/provider-invitations",
        data={
            "csrf_token": token,
            "name": "Dr Invite",
            "email": "invite-doctor@example.com",
            "role": "doctor",
        },
        follow_redirects=False,
    )
    assert invited.status_code == 302
    assert len(sent) == 1
    assert sent[0][0] == "invite-doctor@example.com"
    invite_token = _token_from_mail(sent[0][2])

    client.get("/logout", follow_redirects=False)
    review = client.get(f"/provider-invitation/accept?token={invite_token}")
    assert review.status_code == 200
    review_body = review.get_data(as_text=True)
    assert "Provider verification remains separate" in review_body

    accepted = client.post(
        "/provider-invitation/accept",
        data={
            "csrf_token": csrf(review_body),
            "token": invite_token,
            "name": "Dr Invite",
            "password": "StrongPass123",
            "accept_privacy": "1",
            "accept_terms": "1",
        },
        follow_redirects=False,
    )
    assert accepted.status_code == 302
    assert "/login/doctor" in accepted.headers["Location"]

    with app.app_context():
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email_normalized=?",
            ("invite-doctor@example.com",),
        ).fetchone()
        assert user is not None
        assert user["role"] == "doctor"
        assert user["verified"] == 0
        assert user["active"] == 1

        email_status = db.execute(
            "SELECT verified_email,verified_at FROM user_email_verifications WHERE user_id=?",
            (user["id"],),
        ).fetchone()
        assert email_status["verified_email"] == "invite-doctor@example.com"
        assert email_status["verified_at"]

        policies = db.execute(
            "SELECT policy_type,source FROM user_policy_acceptances WHERE user_id=? ORDER BY policy_type",
            (user["id"],),
        ).fetchall()
        assert [(p["policy_type"], p["source"]) for p in policies] == [
            ("privacy", "provider_invitation"),
            ("terms", "provider_invitation"),
        ]

        assert db.execute(
            "SELECT id FROM provider_profiles WHERE user_id=?",
            (user["id"],),
        ).fetchone() is None

        invitation = db.execute(
            "SELECT accepted_user_id,accepted_at FROM provider_invitations WHERE email_normalized=?",
            ("invite-doctor@example.com",),
        ).fetchone()
        assert invitation["accepted_user_id"] == user["id"]
        assert invitation["accepted_at"]

    replay = client.get(f"/provider-invitation/accept?token={invite_token}", follow_redirects=False)
    assert replay.status_code == 400


def test_non_owner_cannot_create_provider_invitation(tmp_path):
    _app, client = make_client(tmp_path)

    page = client.get("/register/patient")
    token = csrf(page.get_data(as_text=True))
    client.post(
        "/register/patient",
        data={
            "csrf_token": token,
            "name": "Patient",
            "email": "patient-invite@example.com",
            "password": "StrongPass123",
        },
    )
    login_web(client, "patient", "patient-invite@example.com")

    dashboard = client.get("/dashboard")
    token = csrf(dashboard.get_data(as_text=True))
    response = client.post(
        "/admin/provider-invitations",
        data={
            "csrf_token": token,
            "email": "blocked-doctor@example.com",
            "role": "doctor",
        },
        follow_redirects=False,
    )
    assert response.status_code in {302, 403}


def test_provider_invitation_rejects_public_role_escalation_and_duplicate_email(tmp_path, monkeypatch):
    app, client = make_client(tmp_path)
    app.config.update(
        EMAIL_PROVIDER="smtp",
        SMTP_HOST="smtp.example.test",
        SMTP_FROM_EMAIL="noreply@zendoc.example.test",
        SMTP_USE_TLS=True,
    )
    from zendoc import routes
    monkeypatch.setattr(
        routes,
        "send_transactional_email",
        lambda *_args, **_kwargs: {"status": "sent"},
    )

    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    admin = client.get("/admin")
    token = csrf(admin.get_data(as_text=True))

    invalid_role = client.post(
        "/admin/provider-invitations",
        data={
            "csrf_token": token,
            "email": "government-invite@example.com",
            "role": "government",
        },
        follow_redirects=True,
    )
    assert invalid_role.status_code == 200
    assert "must be doctor, hospital, or pharmacy" in invalid_role.get_data(as_text=True)

    duplicate = client.post(
        "/admin/provider-invitations",
        data={
            "csrf_token": csrf(client.get("/admin").get_data(as_text=True)),
            "email": "admin@example.com",
            "role": "doctor",
        },
        follow_redirects=True,
    )
    assert duplicate.status_code == 200
    assert "already exists" in duplicate.get_data(as_text=True)


def test_new_provider_invitation_revokes_older_pending_role_for_same_email(tmp_path, monkeypatch):
    app, client = make_client(tmp_path)
    app.config.update(
        EMAIL_PROVIDER="smtp",
        SMTP_HOST="smtp.example.test",
        SMTP_FROM_EMAIL="noreply@zendoc.example.test",
        SMTP_USE_TLS=True,
        PUBLIC_BASE_URL="https://zendoc.example.test",
    )
    sent = []
    from zendoc import routes
    monkeypatch.setattr(
        routes,
        "send_transactional_email",
        lambda to_email, subject, text_body: sent.append((to_email, subject, text_body)) or {"status": "sent"},
    )

    login_web(client, "admin", "admin@example.com", "AdminStrong123")

    first_page = client.get("/admin")
    first = client.post(
        "/admin/provider-invitations",
        data={
            "csrf_token": csrf(first_page.get_data(as_text=True)),
            "email": "role-change@example.com",
            "role": "doctor",
        },
    )
    assert first.status_code == 302
    first_token = _token_from_mail(sent[-1][2])

    second_page = client.get("/admin")
    second = client.post(
        "/admin/provider-invitations",
        data={
            "csrf_token": csrf(second_page.get_data(as_text=True)),
            "email": "role-change@example.com",
            "role": "pharmacy",
        },
    )
    assert second.status_code == 302
    second_token = _token_from_mail(sent[-1][2])

    assert client.get(f"/provider-invitation/accept?token={first_token}").status_code == 400
    fresh = client.get(f"/provider-invitation/accept?token={second_token}")
    assert fresh.status_code == 200
    assert "Pharmacy" in fresh.get_data(as_text=True)
