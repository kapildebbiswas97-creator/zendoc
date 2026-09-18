from tests.test_milestone1 import api_token, make_client
from tests.test_milestone6 import headers
from zendoc.home_health import HOME_HEALTH_SERVICES


def test_home_health_catalog_is_request_intake_not_fake_availability():
    assert HOME_HEALTH_SERVICES
    assert all(item["status_badge"] == "Request Intake" for item in HOME_HEALTH_SERVICES)
    joined = " ".join(item["description"] for item in HOME_HEALTH_SERVICES).lower()
    assert "at your doorstep" not in joined
    assert "provider availability" in joined or "provider" in joined


def test_fresh_home_health_request_is_unconfirmed_and_unknown_type_rejected(tmp_path):
    _app, client = make_client(tmp_path)
    token = api_token(client, "home-truth@example.com")

    invalid = client.post(
        "/api/v1/home-health/requests",
        json={
            "service_type": "invented_service",
            "scheduled_date": "2026-10-01",
            "address": "Home",
            "city": "Kolkata",
        },
        headers=headers(token),
    )
    assert invalid.status_code == 400

    created = client.post(
        "/api/v1/home-health/requests",
        json={
            "service_type": "nurse_visit",
            "scheduled_date": "2026-10-01",
            "address": "Home",
            "city": "Kolkata",
        },
        headers=headers(token),
    )
    assert created.status_code == 201
    request = created.get_json()["home_health_request"]
    assert request["status"] == "requested"
    assert request["provider_assigned"] is False
    assert request["provider_confirmed"] is False
    assert request["fulfilment_status"] == "request_recorded_unconfirmed"


def test_emergency_transport_request_never_claims_dispatch(tmp_path):
    _app, client = make_client(tmp_path)
    token = api_token(client, "transport-truth@example.com")

    invalid = client.post(
        "/api/v1/ambulance/requests",
        json={"transport_type": "invented_vehicle", "pickup_address": "Home"},
        headers=headers(token),
    )
    assert invalid.status_code == 400

    created = client.post(
        "/api/v1/ambulance/requests",
        json={
            "transport_type": "emergency_ambulance",
            "pickup_address": "Home",
            "destination_address": "Hospital",
            "notes": "urgent transport request",
        },
        headers=headers(token),
    )
    assert created.status_code == 201
    request = created.get_json()["ambulance_request"]
    assert request["status"] == "requested"
    assert request["dispatch_confirmed"] is False
    assert request["provider_confirmed"] is False
    assert "did not dispatch" in request["safety_warning"].lower()
    assert "does not confirm dispatch" in request["truth_notice"].lower()


def test_ai_request_only_services_preserve_truth_boundaries(tmp_path):
    _app, client = make_client(tmp_path)
    token = api_token(client, "request-ai-truth@example.com")

    transport = client.post(
        "/api/v1/ai/message",
        json={"message": "I want patient transport for a routine clinic visit"},
        headers=headers(token),
    )
    assert transport.status_code == 200
    t = transport.get_json()["message"].lower()
    assert "not dispatch confirmation" in t

    home = client.post(
        "/api/v1/ai/message",
        json={"message": "I need home health nursing"},
        headers=headers(token),
    )
    assert home.status_code == 200
    h = home.get_json()["message"].lower()
    assert "request" in h
    assert "not a confirmed home visit" in h or "not a confirmed" in h

    pharmacy = client.post(
        "/api/v1/ai/message",
        json={"message": "I need a pharmacy medicine request"},
        headers=headers(token),
    )
    assert pharmacy.status_code == 200
    p = pharmacy.get_json()["message"].lower()
    assert "stock" in p
    assert "not confirmed" in p
