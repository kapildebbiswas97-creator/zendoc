from datetime import datetime, timedelta, timezone

from tests.test_milestone1 import make_client, register_web
from zendoc.db import get_db
from zendoc.security import hash_token


def _past_iso():
    return (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(timespec="seconds")


def test_api_login_issues_expiring_access_and_refresh_tokens(tmp_path):
    app, client = make_client(tmp_path)
    email = "token-life@example.com"
    register_web(client, "patient", email, "Token Life")

    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPass123"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["token"] == data["access_token"]
    assert data["access_token_expires_at"]
    assert data["refresh_token"]
    assert data["refresh_token_expires_at"]

    with app.app_context():
        rows = get_db().execute(
            """
            SELECT token_type,expires_at
            FROM api_tokens
            WHERE user_id=(SELECT id FROM users WHERE email_normalized=?)
              AND token_type IN ('access','refresh')
            ORDER BY id
            """,
            (email,),
        ).fetchall()
        assert [row["token_type"] for row in rows[-2:]] == ["access", "refresh"]
        assert all(row["expires_at"] for row in rows[-2:])


def test_expired_access_token_is_rejected(tmp_path):
    app, client = make_client(tmp_path)
    email = "expired-access@example.com"
    register_web(client, "patient", email, "Expired Access")
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPass123"},
    ).get_json()
    access = login["access_token"]

    with app.app_context():
        get_db().execute(
            "UPDATE api_tokens SET expires_at=? WHERE token_hash=? AND token_type='access'",
            (_past_iso(), hash_token(access)),
        )
        get_db().commit()

    response = client.get(
        "/api/v1/dashboard",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 401


def test_refresh_token_rotates_and_old_refresh_cannot_be_reused(tmp_path):
    _app, client = make_client(tmp_path)
    email = "refresh-rotate@example.com"
    register_web(client, "patient", email, "Refresh Rotate")
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPass123"},
    ).get_json()

    old_refresh = login["refresh_token"]
    refreshed = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert refreshed.status_code == 200
    data = refreshed.get_json()
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["refresh_token"] != old_refresh

    reused = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert reused.status_code == 401

    dashboard = client.get(
        "/api/v1/dashboard",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    assert dashboard.status_code == 200


def test_logout_revokes_access_and_supplied_refresh_token(tmp_path):
    _app, client = make_client(tmp_path)
    email = "logout-tokens@example.com"
    register_web(client, "patient", email, "Logout Tokens")
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPass123"},
    ).get_json()

    logged_out = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {login['access_token']}"},
        json={"refresh_token": login["refresh_token"]},
    )
    assert logged_out.status_code == 200

    access_denied = client.get(
        "/api/v1/dashboard",
        headers={"Authorization": f"Bearer {login['access_token']}"},
    )
    assert access_denied.status_code == 401

    refresh_denied = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login["refresh_token"]},
    )
    assert refresh_denied.status_code == 401


def test_public_release_rejects_indefinite_legacy_access_token(tmp_path):
    app, client = make_client(tmp_path)
    email = "legacy-token@example.com"
    register_web(client, "patient", email, "Legacy Token")

    raw_token = "legacy-public-access-token"
    with app.app_context():
        user = get_db().execute(
            "SELECT id FROM users WHERE email_normalized=?",
            (email,),
        ).fetchone()
        get_db().execute(
            """
            INSERT INTO api_tokens
            (user_id,token_hash,token_type,expires_at,created_at)
            VALUES (?,?,'access',NULL,?)
            """,
            (user["id"], hash_token(raw_token), datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        get_db().commit()
        app.config["PUBLIC_RELEASE_REQUIRED"] = True

    denied = client.get(
        "/api/v1/dashboard",
        headers={"Authorization": f"Bearer {raw_token}"},
    )
    assert denied.status_code == 401
