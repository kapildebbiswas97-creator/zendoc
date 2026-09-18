from tests.test_milestone1 import csrf, make_client
from zendoc.db import get_db
from zendoc.policy_acceptance import PRIVACY_POLICY_VERSION, TERMS_POLICY_VERSION


def _registration_form(client, **overrides):
    page = client.get("/register/patient")
    token = csrf(page.get_data(as_text=True))
    data = {
        "csrf_token": token,
        "name": "Policy Patient",
        "email": "policy@example.com",
        "password": "StrongPass123",
    }
    data.update(overrides)
    return data


def test_public_web_registration_requires_privacy_and_terms(tmp_path):
    app, client = make_client(tmp_path)
    app.config["PUBLIC_RELEASE_REQUIRED"] = True

    missing = client.post("/register/patient", data=_registration_form(client))
    assert missing.status_code == 400
    assert "must accept both" in missing.get_data(as_text=True)

    accepted = client.post(
        "/register/patient",
        data=_registration_form(
            client,
            accept_privacy="1",
            accept_terms="1",
        ),
        follow_redirects=False,
    )
    assert accepted.status_code == 302

    with app.app_context():
        user = get_db().execute(
            "SELECT id FROM users WHERE email_normalized=?",
            ("policy@example.com",),
        ).fetchone()
        rows = get_db().execute(
            """
            SELECT policy_type,policy_version,source
            FROM user_policy_acceptances
            WHERE user_id=?
            ORDER BY policy_type
            """,
            (user["id"],),
        ).fetchall()
        assert [(r["policy_type"], r["policy_version"], r["source"]) for r in rows] == [
            ("privacy", PRIVACY_POLICY_VERSION, "web_registration"),
            ("terms", TERMS_POLICY_VERSION, "web_registration"),
        ]


def test_public_api_registration_requires_and_records_policy_acceptance(tmp_path):
    app, client = make_client(tmp_path)
    app.config["PUBLIC_RELEASE_REQUIRED"] = True

    missing = client.post(
        "/api/v1/auth/register",
        json={
            "name": "API Policy Patient",
            "email": "api-policy@example.com",
            "password": "StrongPass123",
            "role": "patient",
        },
    )
    assert missing.status_code == 400
    assert "accept_terms and accept_privacy" in missing.get_json()["error"]["message"]

    accepted = client.post(
        "/api/v1/auth/register",
        json={
            "name": "API Policy Patient",
            "email": "api-policy@example.com",
            "password": "StrongPass123",
            "role": "patient",
            "accept_privacy": True,
            "accept_terms": True,
        },
    )
    assert accepted.status_code == 201

    with app.app_context():
        user = get_db().execute(
            "SELECT id FROM users WHERE email_normalized=?",
            ("api-policy@example.com",),
        ).fetchone()
        rows = get_db().execute(
            """
            SELECT policy_type,policy_version,source
            FROM user_policy_acceptances
            WHERE user_id=?
            ORDER BY policy_type
            """,
            (user["id"],),
        ).fetchall()
        assert [(r["policy_type"], r["policy_version"], r["source"]) for r in rows] == [
            ("privacy", PRIVACY_POLICY_VERSION, "api_registration"),
            ("terms", TERMS_POLICY_VERSION, "api_registration"),
        ]


def test_partial_policy_acceptance_is_rejected_even_before_public_release(tmp_path):
    app, client = make_client(tmp_path)
    app.config["PUBLIC_RELEASE_REQUIRED"] = False

    partial = client.post(
        "/register/patient",
        data=_registration_form(client, accept_privacy="1"),
    )
    assert partial.status_code == 400

    api_partial = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Partial API",
            "email": "partial-api@example.com",
            "password": "StrongPass123",
            "role": "patient",
            "accept_privacy": True,
            "accept_terms": False,
        },
    )
    assert api_partial.status_code == 400


def test_registration_page_links_public_policy_documents(tmp_path):
    app, client = make_client(tmp_path)
    app.config["PUBLIC_RELEASE_REQUIRED"] = True

    response = client.get("/register/patient")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "/privacy" in body
    assert "/terms" in body
    assert 'name="accept_privacy"' in body
    assert 'name="accept_terms"' in body
    assert "required" in body


def test_public_release_blocks_government_self_registration(tmp_path):
    app, client = make_client(tmp_path)
    app.config["PUBLIC_RELEASE_REQUIRED"] = True

    web = client.get("/register/government")
    assert web.status_code == 403

    api = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Public Government Attempt",
            "email": "gov-public@example.com",
            "password": "StrongPass123",
            "role": "government",
            "accept_privacy": True,
            "accept_terms": True,
        },
    )
    assert api.status_code == 403
    assert "controlled provisioning" in api.get_json()["error"]["message"]
