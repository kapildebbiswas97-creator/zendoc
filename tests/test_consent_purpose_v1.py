from zendoc.db import get_db
from zendoc.health_access import has_active_grant

from tests.test_milestone1 import api_token, make_client
from tests.test_milestone4 import headers, user_id, verified_provider


def test_health_access_grant_persists_and_lists_purpose(tmp_path):
    app, client = make_client(tmp_path)
    _provider_token, provider_profile_id, provider_id = verified_provider(app, client, "purpose-provider@example.com")
    patient_token = api_token(client, "purpose-patient@example.com")
    patient_id = user_id(app, "purpose-patient@example.com")

    created = client.post(
        "/api/v1/health-access",
        json={
            "provider_profile_id": provider_profile_id,
            "scopes": ["profile", "timeline"],
            "purpose": "consultation",
        },
        headers=headers(patient_token),
    )
    assert created.status_code == 201

    listed = client.get("/api/v1/health-access", headers=headers(patient_token))
    assert listed.status_code == 200
    grant = next(item for item in listed.json["grants"] if item["id"] == created.json["grant_id"])
    assert grant["purpose"] == "consultation"
    assert grant["scopes"] == ["profile", "timeline"]

    with app.app_context():
        assert has_active_grant(patient_id, provider_id, "profile", purpose="consultation") is True
        assert has_active_grant(patient_id, provider_id, "profile", purpose="diagnostics") is False


def test_invalid_consent_purpose_is_rejected(tmp_path):
    app, client = make_client(tmp_path)
    _provider_token, provider_profile_id, _provider_id = verified_provider(app, client, "purpose-invalid-provider@example.com")
    patient_token = api_token(client, "purpose-invalid-patient@example.com")

    response = client.post(
        "/api/v1/health-access",
        json={
            "provider_profile_id": provider_profile_id,
            "scopes": ["profile"],
            "purpose": "marketing",
        },
        headers=headers(patient_token),
    )
    assert response.status_code == 400
    assert "Unsupported consent purpose" in response.json["error"]["message"]


def test_other_patient_cannot_revoke_purpose_bound_grant(tmp_path):
    app, client = make_client(tmp_path)
    _provider_token, provider_profile_id, _provider_id = verified_provider(app, client, "purpose-idor-provider@example.com")
    owner_token = api_token(client, "purpose-owner@example.com")
    attacker_token = api_token(client, "purpose-attacker@example.com")

    created = client.post(
        "/api/v1/health-access",
        json={
            "provider_profile_id": provider_profile_id,
            "scopes": ["reports"],
            "purpose": "second_opinion",
        },
        headers=headers(owner_token),
    )
    assert created.status_code == 201

    denied = client.delete(
        f"/api/v1/health-access/{created.json['grant_id']}",
        headers=headers(attacker_token),
    )
    assert denied.status_code == 404

    owner_list = client.get("/api/v1/health-access", headers=headers(owner_token))
    grant = next(item for item in owner_list.json["grants"] if item["id"] == created.json["grant_id"])
    assert grant["active"] is True
    assert grant["purpose"] == "second_opinion"


def test_legacy_grant_without_context_defaults_to_care_coordination(tmp_path):
    app, client = make_client(tmp_path)
    _provider_token, provider_profile_id, provider_id = verified_provider(app, client, "purpose-legacy-provider@example.com")
    patient_token = api_token(client, "purpose-legacy-patient@example.com")
    patient_id = user_id(app, "purpose-legacy-patient@example.com")

    with app.app_context():
        now = "2026-09-11T00:00:00+00:00"
        cursor = get_db().execute(
            """
            INSERT INTO health_access_grants
            (patient_id,provider_id,provider_profile_id,scopes,expires_at,revoked_at,created_at,updated_at)
            VALUES (?,?,?,?,NULL,NULL,?,?)
            """,
            (patient_id, provider_id, provider_profile_id, '["profile"]', now, now),
        )
        legacy_grant_id = cursor.lastrowid
        get_db().commit()

    listed = client.get("/api/v1/health-access", headers=headers(patient_token))
    grant = next(item for item in listed.json["grants"] if item["id"] == legacy_grant_id)
    assert grant["purpose"] == "care_coordination"

    with app.app_context():
        assert has_active_grant(patient_id, provider_id, "profile", purpose="care_coordination") is True
        assert has_active_grant(patient_id, provider_id, "profile", purpose="consultation") is False
