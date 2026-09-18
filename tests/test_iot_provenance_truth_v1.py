from tests.test_milestone1 import api_token, login_web, make_client, register_web
from tests.test_milestone6 import headers
from zendoc.db import get_db


def test_registered_device_is_not_connected_or_synced(tmp_path):
    app, client = make_client(tmp_path)
    token = api_token(client, "iot-truth@example.com")

    response = client.post(
        "/api/v1/iot/devices",
        json={"device_name": "Home BP Monitor", "device_type": "blood_pressure_monitor"},
        headers=headers(token),
    )
    assert response.status_code == 201
    device = response.get_json()["health_device"]
    assert device["status"] == "registered"
    assert device["last_synced_at"] is None
    assert device["device_identifier"] is None
    assert device["live_device_sync"] is False

    with app.app_context():
        row = get_db().execute("SELECT * FROM health_devices WHERE id=?", (device["id"],)).fetchone()
        assert row["status"] == "registered"
        assert row["last_synced_at"] is None


def test_public_iot_sync_fails_closed_and_creates_no_device_measurement(tmp_path):
    app, client = make_client(tmp_path)
    token = api_token(client, "iot-sync-boundary@example.com")
    device = client.post(
        "/api/v1/iot/devices",
        json={"device_name": "Pulse Oximeter", "device_type": "pulse_oximeter"},
        headers=headers(token),
    ).get_json()["health_device"]

    response = client.post(
        f"/api/v1/iot/devices/{device['id']}/sync",
        json={"metric_type": "oxygen_saturation", "metric_value": 98, "unit": "%"},
        headers=headers(token),
    )
    assert response.status_code == 409
    payload = response.get_json()
    assert payload["status"] == "integration_required"
    assert payload["trusted_device_provenance_created"] is False
    assert "Health Monitoring" in payload["error"]["message"]

    with app.app_context():
        count = get_db().execute(
            "SELECT COUNT(*) c FROM health_metrics WHERE source='device'"
        ).fetchone()["c"]
        assert count == 0


def test_iot_page_has_no_manual_fake_device_sync_form(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "iot-page@example.com", "IoT Page")
    login_web(client, "patient", "iot-page@example.com")

    response = client.get("/iot-hub")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Registration only · no live device provenance" in body
    assert 'name="action" value="sync"' not in body
    assert "Enter a manual measurement in Health Monitoring" in body


def test_ai_iot_guidance_never_claims_live_connection(tmp_path):
    _app, client = make_client(tmp_path)
    token = api_token(client, "iot-ai@example.com")

    response = client.post(
        "/api/v1/ai/message",
        json={"message": "connect my smartwatch"},
        headers=headers(token),
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["intent"] == "iot_hub"
    message = payload["message"].lower()
    assert "integration required" in message
    assert "do not create trusted device provenance" in message
    assert "connects your smartwatch" not in message
