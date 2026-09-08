from zendoc.db import get_db
from zendoc.public_data_ingestion import ingest_public_records
from zendoc.public_entity_claims import review_public_entity_claim, submit_public_entity_claim
from zendoc.provider_service import upsert_provider_profile
from tests.test_milestone1 import make_app


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def create_provider_user(db, *, email, role):
    now = "2026-09-08T00:00:00+00:00"
    cursor = db.execute(
        """
        INSERT INTO users
        (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
        VALUES (?,?,?,?,?,1,?,?)
        """,
        ("Provider", email, email, "x", role, now, now),
    )
    return {
        "id": int(cursor.lastrowid),
        "name": "Provider",
        "email": email,
        "role": role,
        "active": 1,
    }


def create_public_hospital():
    result = ingest_public_records(
        owner_actor(),
        source_id="data_gov_hospitals",
        ingestion_type="public_healthcare_entities",
        records=[
            {
                "source_record_id": "CLAIM-HOSP-1",
                "category": "hospital",
                "name": "Claimable Public Hospital",
                "state": "West Bengal",
                "district": "Nadia",
            }
        ],
        dry_run=False,
    )
    return int(result["applied"]["applied"][0]["entity_id"])


def test_provider_can_claim_public_listing_but_claim_does_not_auto_verify(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        provider = create_provider_user(db, email="hospital-claim@example.com", role="hospital")
        upsert_provider_profile(
            provider,
            {
                "organization": "Claimable Public Hospital",
                "license_identifier": "LIC-001",
                "address": "Nadia",
                "city": "Kalyani",
                "state": "West Bengal",
                "public_phone": "1234567890",
            },
        )
        db.commit()

        public_entity_id = create_public_hospital()
        claim = submit_public_entity_claim(
            provider,
            public_entity_id=public_entity_id,
            claimant_note="We operate this hospital.",
        )

        assert claim["status"] == "pending"
        profile = db.execute(
            "SELECT verification_status FROM provider_profiles WHERE user_id=?",
            (provider["id"],),
        ).fetchone()
        assert profile["verification_status"] == "pending"

        approved = review_public_entity_claim(
            owner_actor(),
            claim["id"],
            status="approved",
            review_note="Directory identity reviewed.",
        )
        assert approved["status"] == "approved"

        profile = db.execute(
            "SELECT verification_status FROM provider_profiles WHERE user_id=?",
            (provider["id"],),
        ).fetchone()
        assert profile["verification_status"] == "pending"
        assert "does not by itself verify" in approved["truth_notice"]


def test_non_provider_cannot_claim_public_listing(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient = create_provider_user(db, email="patient-claim@example.com", role="patient")
        public_entity_id = create_public_hospital()

        try:
            submit_public_entity_claim(patient, public_entity_id=public_entity_id)
            assert False, "patient claim should fail"
        except PermissionError:
            pass


def test_conflicting_second_approved_claim_is_blocked(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        hospital_a = create_provider_user(db, email="hosp-a@example.com", role="hospital")
        hospital_b = create_provider_user(db, email="hosp-b@example.com", role="hospital")

        for provider, license_id in ((hospital_a, "LIC-A"), (hospital_b, "LIC-B")):
            upsert_provider_profile(
                provider,
                {
                    "organization": "Claimable Public Hospital",
                    "license_identifier": license_id,
                    "address": "Nadia",
                    "city": "Kalyani",
                    "state": "West Bengal",
                    "public_phone": "1234567890",
                },
            )
        db.commit()

        public_entity_id = create_public_hospital()
        claim_a = submit_public_entity_claim(hospital_a, public_entity_id=public_entity_id)
        review_public_entity_claim(owner_actor(), claim_a["id"], status="approved")

        try:
            submit_public_entity_claim(hospital_b, public_entity_id=public_entity_id)
            assert False, "second provider must not claim approved listing"
        except PermissionError:
            pass


def test_claim_api_requires_provider_and_owner_review(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    with app.app_context():
        public_entity_id = create_public_hospital()

    register = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Claim API Hospital",
            "email": "claim-api-hospital@example.com",
            "password": "StrongPass123",
            "role": "hospital",
        },
    )
    assert register.status_code in {200, 201}
    login_provider = client.post(
        "/api/v1/auth/login",
        json={"email": "claim-api-hospital@example.com", "password": "StrongPass123"},
    )
    assert login_provider.status_code == 200
    provider_token = login_provider.get_json()["token"]

    with app.app_context():
        user = get_db().execute(
            "SELECT * FROM users WHERE email='claim-api-hospital@example.com'"
        ).fetchone()
        upsert_provider_profile(
            user,
            {
                "organization": "Claimable Public Hospital",
                "license_identifier": "LIC-API",
                "address": "Nadia",
                "city": "Kalyani",
                "state": "West Bengal",
                "public_phone": "1234567890",
            },
        )
        get_db().commit()

    created = client.post(
        "/api/v1/provider/public-entity-claims",
        headers={"Authorization": f"Bearer {provider_token}"},
        json={"public_entity_id": public_entity_id},
    )
    assert created.status_code == 201
    claim_id = created.get_json()["claim"]["id"]

    denied = client.post(
        f"/api/v1/admin/public-entity-claims/{claim_id}/review",
        headers={"Authorization": f"Bearer {provider_token}"},
        json={"status": "approved"},
    )
    assert denied.status_code == 403

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminStrong123"},
    )
    owner_token = login.get_json()["token"]
    approved = client.post(
        f"/api/v1/admin/public-entity-claims/{claim_id}/review",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"status": "approved"},
    )
    assert approved.status_code == 200
    assert approved.get_json()["claim"]["status"] == "approved"


def test_pharmacy_cannot_claim_hospital_listing(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        pharmacy = create_provider_user(db, email="pharmacy-role@example.com", role="pharmacy")
        upsert_provider_profile(
            pharmacy,
            {
                "organization": "Role Pharmacy",
                "license_identifier": "PH-ROLE-1",
                "address": "Nadia",
                "city": "Kalyani",
                "state": "West Bengal",
                "public_phone": "1234567890",
            },
        )
        db.commit()

        public_entity_id = create_public_hospital()
        blocked = False
        try:
            submit_public_entity_claim(pharmacy, public_entity_id=public_entity_id)
        except PermissionError:
            blocked = True
        assert blocked is True
