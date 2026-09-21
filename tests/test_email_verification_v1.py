import re

from tests.test_milestone1 import csrf, make_client
from zendoc.db import get_db


def _configure_public_email(app):
    app.config.update(
        PUBLIC_RELEASE_REQUIRED=True,
        EMAIL_PROVIDER="smtp",
        EMAIL_VERIFIED=True,
        SMTP_HOST="smtp.example.test",
        SMTP_FROM_EMAIL="noreply@zendoc.example.test",
        PUBLIC_BASE_URL="https://zendoc.example.test",
    )


def _extract_token(text):
    match = re.search(r"[?&]token=([A-Za-z0-9_\-]+)", text)
    assert match, text
    return match.group(1)


def test_public_web_registration_requires_email_verification_before_login(tmp_path, monkeypatch):
    app, client = make_client(tmp_path)
    _configure_public_email(app)

    sent = []
    from zendoc import routes

    monkeypatch.setattr(
        routes,
        "send_transactional_email",
        lambda to_email, subject, text_body: sent.append((to_email, subject, text_body)) or {"status": "sent"},
    )

    page = client.get("/register/patient")
    response = client.post(
        "/register/patient",
        data={
            "csrf_token": csrf(page.get_data(as_text=True)),
            "name": "Verify Web",
            "email": "verify-web@example.com",
            "password": "StrongPass123",
            "accept_privacy": "1",
            "accept_terms": "1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert len(sent) == 1
    assert sent[0][0] == "verify-web@example.com"
    assert sent[0][1] == "Verify your ZENDOC email address"
    token = _extract_token(sent[0][2])

    login_page = client.get("/login")
    blocked = client.post(
        "/login",
        data={
            "csrf_token": csrf(login_page.get_data(as_text=True)),
            "email": "verify-web@example.com",
            "password": "StrongPass123",
        },
    )
    assert blocked.status_code == 403
    assert "Email verification is required" in blocked.get_data(as_text=True)

    review = client.get(f"/verify-email?token={token}")
    assert review.status_code == 200
    review_body = review.get_data(as_text=True)
    assert "Verify this email" in review_body

    still_blocked = client.post(
        "/api/v1/auth/login",
        json={"email": "verify-web@example.com", "password": "StrongPass123"},
    )
    assert still_blocked.status_code == 403

    verified = client.post(
        "/verify-email",
        data={
            "csrf_token": csrf(review_body),
            "token": token,
        },
        follow_redirects=False,
    )
    assert verified.status_code == 302
    assert "/login" in verified.headers["Location"]

    login_page = client.get("/login")
    allowed = client.post(
        "/login",
        data={
            "csrf_token": csrf(login_page.get_data(as_text=True)),
            "email": "verify-web@example.com",
            "password": "StrongPass123",
        },
        follow_redirects=False,
    )
    assert allowed.status_code == 302
    assert "/dashboard" in allowed.headers["Location"]

    with app.app_context():
        row = get_db().execute(
            """
            SELECT verified_email,verified_at
            FROM user_email_verifications uev
            JOIN users u ON u.id=uev.user_id
            WHERE u.email_normalized=?
            """,
            ("verify-web@example.com",),
        ).fetchone()
        assert row["verified_email"] == "verify-web@example.com"
        assert row["verified_at"]


def test_public_api_registration_verify_and_login_flow(tmp_path, monkeypatch):
    app, client = make_client(tmp_path)
    _configure_public_email(app)

    sent = []
    from zendoc import routes

    monkeypatch.setattr(
        routes,
        "send_transactional_email",
        lambda to_email, subject, text_body: sent.append((to_email, subject, text_body)) or {"status": "sent"},
    )

    registered = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Verify API",
            "email": "verify-api@example.com",
            "password": "StrongPass123",
            "role": "patient",
            "accept_privacy": True,
            "accept_terms": True,
        },
    )
    assert registered.status_code == 201
    assert registered.get_json()["email_verification_required"] is True
    assert len(sent) == 1
    token = _extract_token(sent[0][2])

    blocked = client.post(
        "/api/v1/auth/login",
        json={"email": "verify-api@example.com", "password": "StrongPass123"},
    )
    assert blocked.status_code == 403
    assert blocked.get_json()["error"]["reason"] == "email_verification_required"

    verified = client.post(
        "/api/v1/auth/verify-email",
        json={"token": token},
    )
    assert verified.status_code == 200
    assert verified.get_json()["status"] == "verified"

    allowed = client.post(
        "/api/v1/auth/login",
        json={"email": "verify-api@example.com", "password": "StrongPass123"},
    )
    assert allowed.status_code == 200
    assert allowed.get_json()["token"]


def test_resend_verification_is_non_enumerating(tmp_path, monkeypatch):
    app, client = make_client(tmp_path)
    _configure_public_email(app)

    sent = []
    from zendoc import routes

    monkeypatch.setattr(
        routes,
        "send_transactional_email",
        lambda to_email, subject, text_body: sent.append((to_email, subject, text_body)) or {"status": "sent"},
    )

    registered = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Resend User",
            "email": "resend-user@example.com",
            "password": "StrongPass123",
            "role": "patient",
            "accept_privacy": True,
            "accept_terms": True,
        },
    )
    assert registered.status_code == 201
    initial_count = len(sent)

    existing = client.post(
        "/api/v1/auth/resend-verification",
        json={"email": "resend-user@example.com"},
    )
    missing = client.post(
        "/api/v1/auth/resend-verification",
        json={"email": "missing-resend@example.com"},
    )
    assert existing.status_code == 202
    assert missing.status_code == 202
    assert existing.get_json() == missing.get_json()
    assert len(sent) == initial_count + 1


def test_invalid_email_verification_token_fails_closed(tmp_path):
    app, client = make_client(tmp_path)
    _configure_public_email(app)

    api = client.post(
        "/api/v1/auth/verify-email",
        json={"token": "not-a-valid-token"},
    )
    assert api.status_code == 400

    web = client.get("/verify-email?token=not-a-valid-token", follow_redirects=False)
    assert web.status_code == 302
    assert "/resend-verification" in web.headers["Location"]
