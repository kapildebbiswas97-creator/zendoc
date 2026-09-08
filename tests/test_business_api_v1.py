from zendoc.business_api import (
    authenticate_business_api_key,
    create_business_api_client,
    issue_business_api_key,
    revoke_business_api_key,
)
from zendoc.db import get_db
from tests.test_milestone1 import make_app, make_client


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def test_business_api_key_is_hashed_scoped_and_revocable(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        client = create_business_api_client(
            owner_actor(),
            {
                "name": "Pilot Partner",
                "client_type": "hospital",
                "allowed_scopes": ["public_directory.read"],
                "rate_limit_per_minute": 10,
            },
        )
        issued = issue_business_api_key(owner_actor(), client["id"], expires_in_days=30)
        assert issued["api_key"].startswith("zd_biz_")

        row = get_db().execute(
            "SELECT key_hash,key_prefix,status FROM business_api_keys WHERE id=?",
            (issued["key_id"],),
        ).fetchone()
        assert row["key_hash"] != issued["api_key"]
        assert issued["api_key"] not in str(dict(row))
        assert row["key_prefix"] == issued["key_prefix"]

        identity = authenticate_business_api_key(
            issued["api_key"],
            required_scope="public_directory.read",
            endpoint="/test",
            method="GET",
        )
        assert identity["client_id"] == client["id"]
        assert "public_directory.read" in identity["scopes"]

        blocked = False
        try:
            authenticate_business_api_key(
                issued["api_key"],
                required_scope="provider_availability.read",
                endpoint="/test",
            )
        except PermissionError:
            blocked = True
        assert blocked is True

        revoke_business_api_key(owner_actor(), issued["key_id"])
        revoked = False
        try:
            authenticate_business_api_key(issued["api_key"], endpoint="/test")
        except PermissionError:
            revoked = True
        assert revoked is True


def test_business_ping_requires_partner_key_and_exposes_no_patient_data(tmp_path):
    app, client = make_client(tmp_path)

    denied = client.get("/api/v1/business/ping")
    assert denied.status_code == 401

    with app.app_context():
        partner = create_business_api_client(
            owner_actor(),
            {
                "name": "Ping Partner",
                "client_type": "diagnostic_centre",
                "allowed_scopes": ["public_directory.read"],
            },
        )
        issued = issue_business_api_key(owner_actor(), partner["id"], expires_in_days=30)

    allowed = client.get(
        "/api/v1/business/ping",
        headers={"X-ZENDOC-Partner-Key": issued["api_key"]},
    )
    assert allowed.status_code == 200
    payload = allowed.get_json()
    assert payload["patient_data_access"] is False
    assert "patient" not in payload["client"]
    assert "clinical" not in payload["client"]


def test_business_api_rate_limit_is_enforced(tmp_path):
    app, client = make_client(tmp_path)
    with app.app_context():
        partner = create_business_api_client(
            owner_actor(),
            {
                "name": "Rate Limited Partner",
                "client_type": "ngo",
                "allowed_scopes": ["public_directory.read"],
                "rate_limit_per_minute": 1,
            },
        )
        issued = issue_business_api_key(owner_actor(), partner["id"], expires_in_days=30)

    first = client.get(
        "/api/v1/business/ping",
        headers={"X-ZENDOC-Partner-Key": issued["api_key"]},
    )
    second = client.get(
        "/api/v1/business/ping",
        headers={"X-ZENDOC-Partner-Key": issued["api_key"]},
    )
    assert first.status_code == 200
    assert second.status_code == 429


def test_business_api_management_is_owner_only(tmp_path):
    _app, client = make_client(tmp_path)

    denied = client.get("/api/v1/admin/startup/business-api-clients")
    assert denied.status_code in {302, 401, 403}

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminStrong123"},
    )
    token = login.get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/v1/admin/startup/business-api-clients",
        headers=headers,
        json={
            "name": "API Managed Partner",
            "client_type": "hospital",
            "allowed_scopes": ["public_directory.read"],
        },
    )
    assert created.status_code == 201
    client_id = created.get_json()["client"]["id"]

    key = client.post(
        f"/api/v1/admin/startup/business-api-clients/{client_id}/keys",
        headers=headers,
        json={"expires_in_days": 30},
    )
    assert key.status_code == 201
    assert key.get_json()["key"]["api_key"].startswith("zd_biz_")


def test_business_api_client_suspend_revokes_active_keys(tmp_path):
    from zendoc.business_api import update_business_api_client

    app = make_app(tmp_path)
    with app.app_context():
        partner = create_business_api_client(
            owner_actor(),
            {
                "name": "Suspend Partner",
                "client_type": "hospital",
                "allowed_scopes": ["public_directory.read"],
            },
        )
        issued = issue_business_api_key(owner_actor(), partner["id"], expires_in_days=30)

        updated = update_business_api_client(
            owner_actor(),
            partner["id"],
            {"status": "suspended", "allowed_scopes": ["public_directory.read"], "rate_limit_per_minute": 60},
        )
        assert updated["status"] == "suspended"

        row = get_db().execute(
            "SELECT status,revoked_at FROM business_api_keys WHERE id=?",
            (issued["key_id"],),
        ).fetchone()
        assert row["status"] == "revoked"
        assert row["revoked_at"] is not None

        blocked = False
        try:
            authenticate_business_api_key(issued["api_key"], endpoint="/test")
        except PermissionError:
            blocked = True
        assert blocked is True


def test_business_api_key_cannot_be_issued_for_suspended_client(tmp_path):
    from zendoc.business_api import update_business_api_client

    app = make_app(tmp_path)
    with app.app_context():
        partner = create_business_api_client(
            owner_actor(),
            {
                "name": "No Key Partner",
                "client_type": "ngo",
                "allowed_scopes": ["public_directory.read"],
            },
        )
        update_business_api_client(
            owner_actor(),
            partner["id"],
            {"status": "suspended", "allowed_scopes": ["public_directory.read"], "rate_limit_per_minute": 60},
        )

        failed = False
        try:
            issue_business_api_key(owner_actor(), partner["id"], expires_in_days=30)
        except ValueError:
            failed = True
        assert failed is True
