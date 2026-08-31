from zendoc.db import get_db, init_db

from tests.test_milestone1 import api_token, login_web, make_client


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def user_id(app, email):
    with app.app_context():
        return get_db().execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()["id"]


def test_configured_admin_bootstrap_login_and_no_duplicate(tmp_path):
    app, client = make_client(tmp_path)

    wrong = login_web(client, "admin", "admin@example.com", "wrong-password")
    assert b"Email or password is incorrect." in wrong.data

    ok = login_web(client, "admin", "admin@example.com", "AdminStrong123")
    assert b"Admin Dashboard" in ok.data

    with app.app_context():
        init_db()
        rows = get_db().execute("SELECT email, password_hash FROM users WHERE role='admin'").fetchall()
        assert len(rows) == 1
        assert rows[0]["email"] == "admin@example.com"
        assert "AdminStrong123" not in rows[0]["password_hash"]


def test_admin_routes_reject_normal_users(tmp_path):
    _app, client = make_client(tmp_path)
    api_token(client, "ordinary@example.com")
    login_web(client, "patient", "ordinary@example.com")
    assert client.get("/admin").status_code == 403


def test_family_members_are_isolated_and_consent_is_explicit(tmp_path):
    _app, client = make_client(tmp_path)
    parent_token = api_token(client, "parent@example.com")
    child_token = api_token(client, "child@example.com")

    create = client.post(
        "/api/v1/family",
        json={"member_name": "Maa", "relationship": "mother", "city": "Kolkata"},
        headers=headers(parent_token),
    )
    assert create.status_code == 201
    member_id = create.json["family_member"]["id"]

    denied = client.get(f"/api/v1/family/{member_id}", headers=headers(child_token))
    assert denied.status_code == 404

    grant = client.post(
        "/api/v1/family/access-grants",
        json={"grantee_email": "child@example.com", "scopes": ["home_health", "pharmacy", "transport"]},
        headers=headers(parent_token),
    )
    assert grant.status_code == 201
    assert grant.json["family_access_grant"]["scopes"] == ["home_health", "pharmacy", "transport"]

    received = client.get("/api/v1/family/access-grants", headers=headers(child_token))
    assert received.status_code == 200
    assert received.json["received"][0]["grantor_email"] == "parent@example.com"


def test_remote_parent_service_requests_require_family_scope(tmp_path):
    app, client = make_client(tmp_path)
    parent_token = api_token(client, "care-parent@example.com")
    child_token = api_token(client, "care-child@example.com")
    parent_id = user_id(app, "care-parent@example.com")

    denied = client.post(
        "/api/v1/home-health/requests",
        json={
            "patient_id": parent_id,
            "service_type": "nurse_visit",
            "scheduled_date": "2026-09-02",
            "address": "Parent home",
            "city": "Kolkata",
        },
        headers=headers(child_token),
    )
    assert denied.status_code == 403

    client.post(
        "/api/v1/family/access-grants",
        json={"grantee_email": "care-child@example.com", "scopes": ["home_health", "pharmacy", "transport"]},
        headers=headers(parent_token),
    )
    allowed = client.post(
        "/api/v1/home-health/requests",
        json={
            "patient_id": parent_id,
            "service_type": "nurse_visit",
            "scheduled_date": "2026-09-02",
            "address": "Parent home",
            "city": "Kolkata",
        },
        headers=headers(child_token),
    )
    assert allowed.status_code == 201
    assert allowed.json["home_health_request"]["patient_id"] == parent_id

    transport = client.post(
        "/api/v1/ambulance/requests",
        json={
            "patient_id": parent_id,
            "transport_type": "patient_transport",
            "pickup_address": "Parent home",
            "destination_address": "Clinic",
        },
        headers=headers(child_token),
    )
    assert transport.status_code == 201
    assert transport.json["ambulance_request"]["status"] == "requested"


def test_pharmacy_orders_do_not_fabricate_stock_and_can_use_own_account(tmp_path):
    _app, client = make_client(tmp_path)
    token = api_token(client, "meds@example.com")

    search = client.get("/api/v1/pharmacy/medicines?q=amoxicillin", headers=headers(token))
    assert search.status_code == 200
    assert search.json["medicines"][0]["rx_required"] is True
    assert "in_stock" not in search.json["medicines"][0]

    order = client.post(
        "/api/v1/pharmacy/orders",
        json={"items": [{"name": "Paracetamol 500mg", "quantity": 1}], "delivery_address": "Home"},
        headers=headers(token),
    )
    assert order.status_code == 201
    assert order.json["medicine_order"]["items"][0]["name"] == "Paracetamol 500mg"


def test_iot_sync_records_device_provenance(tmp_path):
    _app, client = make_client(tmp_path)
    token = api_token(client, "device@example.com")

    device = client.post(
        "/api/v1/iot/devices",
        json={"device_name": "Home Pulse Watch", "device_type": "smartwatch", "device_identifier": "watch-001"},
        headers=headers(token),
    )
    assert device.status_code == 201
    device_id = device.json["health_device"]["id"]

    synced = client.post(
        f"/api/v1/iot/devices/{device_id}/sync",
        json={"metric_type": "heart_rate", "metric_value": 72, "unit": "bpm"},
        headers=headers(token),
    )
    assert synced.status_code == 201
    measurement = synced.json["synced_measurement"]
    assert measurement["source"] == "device"
    assert "Home Pulse Watch" in measurement["notes"]


def test_saved_locations_and_location_permission_boundary(tmp_path):
    _app, client = make_client(tmp_path)
    token = api_token(client, "location@example.com")

    empty = client.get("/api/v1/locations", headers=headers(token))
    assert empty.status_code == 200
    assert empty.json["saved_locations"] == []

    saved = client.post(
        "/api/v1/locations",
        json={
            "label": "Parents Home",
            "location_type": "parent_home",
            "address": "Lake Town",
            "city": "Kolkata",
            "state": "West Bengal",
            "country": "India",
            "is_default": True,
        },
        headers=headers(token),
    )
    assert saved.status_code == 201
    assert saved.json["saved_location"]["is_default"] == 1


def test_public_milestone6_pages_render_without_login(tmp_path):
    _app, client = make_client(tmp_path)

    assert client.get("/forgot-password").status_code == 200
    assert client.get("/reset-password?token=sample").status_code == 200
    assert client.get("/marketplace").status_code == 200
    assert client.get("/search?q=pharmacy").status_code == 200


def test_ai_routes_milestone6_services_with_emergency_precedence(tmp_path):
    _app, client = make_client(tmp_path)
    token = api_token(client, "m6-ai@example.com")

    home = client.post("/api/v1/ai/message", json={"message": "I need a nurse for my father tomorrow"}, headers=headers(token))
    assert home.status_code == 200
    assert home.json["intent"] in {"family_care", "home_health"}

    device = client.post("/api/v1/ai/message", json={"message": "connect my smartwatch"}, headers=headers(token))
    assert device.status_code == 200
    assert device.json["intent"] == "iot_hub"

    emergency = client.post("/api/v1/ai/message", json={"message": "I need an ambulance for chest pain"}, headers=headers(token))
    assert emergency.status_code == 200
    assert emergency.json["intent"] == "emergency"
    assert emergency.json["emergency"] is True


def test_new_milestone6_api_endpoints_require_auth(tmp_path):
    _app, client = make_client(tmp_path)
    endpoints = [
        ("GET", "/api/v1/family"),
        ("POST", "/api/v1/family"),
        ("GET", "/api/v1/family/care-tasks"),
        ("GET", "/api/v1/home-health/requests"),
        ("POST", "/api/v1/home-health/requests"),
        ("GET", "/api/v1/ambulance/requests"),
        ("POST", "/api/v1/ambulance/requests"),
        ("GET", "/api/v1/pharmacy/medicines"),
        ("GET", "/api/v1/iot/devices"),
        ("POST", "/api/v1/iot/devices"),
        ("GET", "/api/v1/locations"),
    ]

    for method, path in endpoints:
        response = client.get(path) if method == "GET" else client.post(path)
        assert response.status_code == 401
