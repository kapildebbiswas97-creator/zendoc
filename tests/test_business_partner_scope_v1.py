from zendoc.business_api import create_business_api_client, issue_business_api_key
from zendoc.db import get_db
from zendoc.institution_pilots import create_institution_pilot
from tests.test_milestone1 import make_app


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def create_verified_provider(db):
    now = "2026-09-08T00:00:00+00:00"
    user_id = db.execute(
        """
        INSERT INTO users
        (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
        VALUES (?,?,?,?,?,1,?,?)
        """,
        ("Dr Scope", "scope-doctor@example.com", "scope-doctor@example.com", "x", "doctor", now, now),
    ).lastrowid
    profile_id = db.execute(
        """
        INSERT INTO provider_profiles
        (user_id,provider_type,specialty,qualifications,license_identifier,organization,address,city,state,
         postal_code,public_phone,verification_status,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,'verified',?,?)
        """,
        (
            user_id, "doctor", "Cardiology", "MBBS", "REG-SCOPE", "Scope Clinic",
            "1 Road", "Kalyani", "West Bengal", "741235", "1234567890", now, now,
        ),
    ).lastrowid
    db.commit()
    return int(profile_id)


def test_partner_pilot_endpoint_is_tenant_scoped(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    with app.app_context():
        pilot_a = create_institution_pilot(
            owner_actor(),
            {"organization_name": "Org A", "organization_type": "hospital", "status": "active"},
        )
        pilot_b = create_institution_pilot(
            owner_actor(),
            {"organization_name": "Org B", "organization_type": "hospital", "status": "active"},
        )

        client_a = create_business_api_client(
            owner_actor(),
            {
                "name": "Org A API",
                "client_type": "hospital",
                "pilot_id": pilot_a["id"],
                "allowed_scopes": ["pilot_metrics.read"],
            },
        )
        key_a = issue_business_api_key(owner_actor(), client_a["id"], expires_in_days=30)

    response = client.get(
        "/api/v1/business/pilot",
        headers={"X-ZENDOC-Partner-Key": key_a["api_key"]},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["pilot"]["id"] == pilot_a["id"]
    assert payload["pilot"]["organization_name"] == "Org A"
    assert payload["pilot"]["id"] != pilot_b["id"]
    assert payload["patient_data_access"] is False


def test_provider_profile_endpoint_requires_provider_profile_scope(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    with app.app_context():
        profile_id = create_verified_provider(get_db())

        allowed_client = create_business_api_client(
            owner_actor(),
            {
                "name": "Provider Reader",
                "client_type": "employer",
                "allowed_scopes": ["provider_profile.read"],
            },
        )
        allowed_key = issue_business_api_key(owner_actor(), allowed_client["id"], expires_in_days=30)

        denied_client = create_business_api_client(
            owner_actor(),
            {
                "name": "Directory Only",
                "client_type": "ngo",
                "allowed_scopes": ["public_directory.read"],
            },
        )
        denied_key = issue_business_api_key(owner_actor(), denied_client["id"], expires_in_days=30)

    allowed = client.get(
        f"/api/v1/business/providers/{profile_id}",
        headers={"X-ZENDOC-Partner-Key": allowed_key["api_key"]},
    )
    assert allowed.status_code == 200
    payload = allowed.get_json()
    assert payload["provider"]["verification_status"] == "verified"
    assert payload["patient_data_access"] is False
    assert "license_identifier" not in payload["provider"]

    denied = client.get(
        f"/api/v1/business/providers/{profile_id}",
        headers={"X-ZENDOC-Partner-Key": denied_key["api_key"]},
    )
    assert denied.status_code == 401
