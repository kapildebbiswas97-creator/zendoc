from zendoc.business_api import create_business_api_client, issue_business_api_key
from zendoc.db import get_db
from tests.test_milestone1 import make_app


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def create_verified_provider(db, email, name, specialty, city):
    now = "2026-09-08T00:00:00+00:00"
    user_id = db.execute(
        """
        INSERT INTO users
        (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
        VALUES (?,?,?,?,?,1,?,?)
        """,
        (name, email, email, "x", "doctor", now, now),
    ).lastrowid
    profile_id = db.execute(
        """
        INSERT INTO provider_profiles
        (user_id,provider_type,specialty,qualifications,license_identifier,organization,address,city,state,
         postal_code,public_phone,verification_status,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,'verified',?,?)
        """,
        (
            user_id, "doctor", specialty, "MBBS", f"REG-{user_id}", f"{name} Clinic",
            "1 Road", city, "West Bengal", "741235", "1234567890", now, now,
        ),
    ).lastrowid
    return int(profile_id)


def test_partner_verified_provider_discovery_requires_scope(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    with app.app_context():
        create_verified_provider(get_db(), "cardio@example.com", "Dr Cardio", "Cardiology", "Kalyani")
        get_db().commit()

        reader = create_business_api_client(
            owner_actor(),
            {
                "name": "Provider Search Partner",
                "client_type": "employer",
                "allowed_scopes": ["provider_profile.read"],
            },
        )
        reader_key = issue_business_api_key(owner_actor(), reader["id"], expires_in_days=30)

        no_scope = create_business_api_client(
            owner_actor(),
            {
                "name": "No Provider Scope",
                "client_type": "ngo",
                "allowed_scopes": ["public_directory.read"],
            },
        )
        no_scope_key = issue_business_api_key(owner_actor(), no_scope["id"], expires_in_days=30)

    allowed = client.get(
        "/api/v1/business/providers?specialty=Cardiology&location=Kalyani",
        headers={"X-ZENDOC-Partner-Key": reader_key["api_key"]},
    )
    assert allowed.status_code == 200
    payload = allowed.get_json()
    assert payload["count"] == 1
    assert payload["patient_data_access"] is False
    assert payload["results"][0]["verification_status"] == "verified"
    assert "license_identifier" not in payload["results"][0]

    denied = client.get(
        "/api/v1/business/providers",
        headers={"X-ZENDOC-Partner-Key": no_scope_key["api_key"]},
    )
    assert denied.status_code == 401


def test_partner_usage_endpoint_is_self_scoped(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    with app.app_context():
        partner_a = create_business_api_client(
            owner_actor(),
            {
                "name": "Partner A",
                "client_type": "hospital",
                "allowed_scopes": ["public_directory.read"],
            },
        )
        key_a = issue_business_api_key(owner_actor(), partner_a["id"], expires_in_days=30)

        partner_b = create_business_api_client(
            owner_actor(),
            {
                "name": "Partner B",
                "client_type": "ngo",
                "allowed_scopes": ["public_directory.read"],
            },
        )
        key_b = issue_business_api_key(owner_actor(), partner_b["id"], expires_in_days=30)

    client.get(
        "/api/v1/business/ping",
        headers={"X-ZENDOC-Partner-Key": key_a["api_key"]},
    )
    client.get(
        "/api/v1/business/ping",
        headers={"X-ZENDOC-Partner-Key": key_a["api_key"]},
    )
    client.get(
        "/api/v1/business/ping",
        headers={"X-ZENDOC-Partner-Key": key_b["api_key"]},
    )

    usage_a = client.get(
        "/api/v1/business/usage?days=30",
        headers={"X-ZENDOC-Partner-Key": key_a["api_key"]},
    )
    usage_b = client.get(
        "/api/v1/business/usage?days=30",
        headers={"X-ZENDOC-Partner-Key": key_b["api_key"]},
    )

    assert usage_a.status_code == 200
    assert usage_b.status_code == 200
    payload_a = usage_a.get_json()["usage"]
    payload_b = usage_b.get_json()["usage"]

    assert payload_a["client_uid"] != payload_b["client_uid"]
    assert payload_a["request_count"] >= 3
    assert payload_b["request_count"] >= 2
    assert all(item["endpoint"] for item in payload_a["recent_requests"])
