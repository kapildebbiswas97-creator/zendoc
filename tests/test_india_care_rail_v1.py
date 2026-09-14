import os

from zendoc import create_app
from zendoc.india_care_rail import get_india_care_rail_status
from tests.test_milestone1 import login_web, register_web


def make_client(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "india-care-rail.db"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "SECRET_KEY": "india-care-rail-test-secret",
            "ADMIN_EMAIL": "owner@zendoc.local",
            "ADMIN_PASSWORD": "OwnerPassword123!",
            "RATE_LIMIT_PER_MINUTE": 1000,
        }
    )
    return app, app.test_client()


def _clear_rail_env(monkeypatch):
    keys = (
        "ZENDOC_ABDM_MODE",
        "ZENDOC_ABDM_CLIENT_ID",
        "ZENDOC_ABDM_CLIENT_SECRET",
        "ZENDOC_ABDM_PRODUCTION_VERIFIED",
        "ZENDOC_UHI_MODE",
        "ZENDOC_UHI_PARTICIPANT_ID",
        "ZENDOC_UHI_CREDENTIALS_CONFIGURED",
        "ZENDOC_UHI_PRODUCTION_VERIFIED",
        "ZENDOC_NHCX_MODE",
        "ZENDOC_NHCX_PARTICIPANT_ID",
        "ZENDOC_NHCX_CREDENTIALS_CONFIGURED",
        "ZENDOC_NHCX_PRODUCTION_VERIFIED",
    )
    for key in keys:
        monkeypatch.delenv(key, raising=False)


def test_rails_default_to_not_connected(monkeypatch):
    _clear_rail_env(monkeypatch)
    payload = get_india_care_rail_status()
    assert payload["verified_count"] == 0
    assert payload["any_external_live"] is False
    assert {item["status"] for item in payload["rails"]} == {"NOT_CONNECTED"}
    assert all(item["external_execution"] is False for item in payload["rails"])


def test_sandbox_configuration_never_claims_production(monkeypatch):
    _clear_rail_env(monkeypatch)
    monkeypatch.setenv("ZENDOC_ABDM_MODE", "sandbox")
    monkeypatch.setenv("ZENDOC_ABDM_CLIENT_ID", "sandbox-client")
    monkeypatch.setenv("ZENDOC_ABDM_CLIENT_SECRET", "sandbox-secret")

    rail = next(item for item in get_india_care_rail_status()["rails"] if item["id"] == "abdm")
    assert rail["status"] == "SANDBOX_CONFIGURED"
    assert rail["production_verified"] is False
    assert rail["external_live"] is False
    assert rail["external_execution"] is False


def test_production_requires_explicit_verification(monkeypatch):
    _clear_rail_env(monkeypatch)
    monkeypatch.setenv("ZENDOC_ABDM_MODE", "production")
    monkeypatch.setenv("ZENDOC_ABDM_CLIENT_ID", "prod-client")
    monkeypatch.setenv("ZENDOC_ABDM_CLIENT_SECRET", "prod-secret")

    rail = next(item for item in get_india_care_rail_status()["rails"] if item["id"] == "abdm")
    assert rail["status"] == "PRODUCTION_UNVERIFIED"
    assert rail["external_live"] is False

    monkeypatch.setenv("ZENDOC_ABDM_PRODUCTION_VERIFIED", "true")
    verified = next(item for item in get_india_care_rail_status()["rails"] if item["id"] == "abdm")
    assert verified["status"] == "PRODUCTION_VERIFIED"
    assert verified["external_live"] is True
    assert verified["external_execution"] is False


def test_patient_can_view_rail_status_but_provider_cannot(tmp_path, monkeypatch):
    _clear_rail_env(monkeypatch)
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "rail-patient@example.com", "Rail Patient")
    login_web(client, "patient", "rail-patient@example.com")

    page = client.get("/india-care-rail")
    assert page.status_code == 200
    assert b"India Care Rail" in page.data
    assert b"Not connected" in page.data

    api = client.get("/api/v1/india-care-rail/status")
    assert api.status_code == 200
    assert api.get_json()["verified_count"] == 0

    other_app, other_client = make_client(tmp_path / "provider")
    register_web(other_client, "doctor", "rail-doctor@example.com", "Rail Doctor")
    login_web(other_client, "doctor", "rail-doctor@example.com")
    assert other_client.get("/india-care-rail").status_code == 403
