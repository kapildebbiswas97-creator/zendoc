from zendoc.db import get_db
from zendoc.institution_pilots import create_institution_pilot
from zendoc.provider_network import (
    create_provider_prospect,
    list_provider_prospects,
    provider_network_metrics,
    update_provider_prospect,
)
from tests.test_milestone1 import make_app, make_client


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def create_verified_doctor(db):
    now = "2026-09-08T00:00:00+00:00"
    user_id = db.execute(
        """
        INSERT INTO users
        (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
        VALUES (?,?,?,?,?,1,?,?)
        """,
        ("Dr Network", "network-doctor@example.com", "network-doctor@example.com", "x", "doctor", now, now),
    ).lastrowid
    profile_id = db.execute(
        """
        INSERT INTO provider_profiles
        (user_id,provider_type,specialty,qualifications,license_identifier,organization,address,city,state,
         postal_code,public_phone,verification_status,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,'verified',?,?)
        """,
        (
            user_id,
            "doctor",
            "Cardiology",
            "MBBS",
            "REG-NETWORK",
            "Network Clinic",
            "1 Road",
            "Kalyani",
            "West Bengal",
            "741235",
            "1234567890",
            now,
            now,
        ),
    ).lastrowid
    db.execute(
        """
        INSERT INTO provider_schedules
        (provider_profile_id,weekday,start_time,end_time,slot_minutes,active,created_at,updated_at)
        VALUES (?,0,'09:00','12:00',30,1,?,?)
        """,
        (profile_id, now, now),
    )
    db.commit()
    return int(user_id), int(profile_id)


def test_provider_network_counts_only_recorded_prospects(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        prospect = create_provider_prospect(
            owner_actor(),
            {
                "provider_type": "doctor",
                "source_type": "manual_outreach",
                "organization_name": "Prospect Doctor",
                "contact_phone": "9999999999",
                "status": "discovered",
            },
        )
        assert prospect["status"] == "discovered"

        metrics = provider_network_metrics(owner_actor())
        assert metrics["prospect_count"] == 1
        assert metrics["status_counts"]["discovered"] == 1
        assert metrics["activated_count"] == 0
        assert metrics["activation_rate"] == 0


def test_provider_prospect_cannot_claim_verified_or_activated_without_real_links(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        prospect = create_provider_prospect(
            owner_actor(),
            {
                "provider_type": "doctor",
                "source_type": "public_directory",
                "organization_name": "Unlinked Doctor",
                "status": "discovered",
            },
        )

        failed_verified = False
        try:
            update_provider_prospect(
                owner_actor(),
                prospect["id"],
                {"status": "verified"},
            )
        except ValueError:
            failed_verified = True
        assert failed_verified is True

        failed_activated = False
        try:
            update_provider_prospect(
                owner_actor(),
                prospect["id"],
                {"status": "activated"},
            )
        except ValueError:
            failed_activated = True
        assert failed_activated is True


def test_provider_prospect_activation_requires_real_verified_profile_and_schedule(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        user_id, profile_id = create_verified_doctor(db)

        prospect = create_provider_prospect(
            owner_actor(),
            {
                "provider_type": "doctor",
                "source_type": "referral",
                "organization_name": "Network Clinic",
                "contact_name": "Dr Network",
                "status": "registered",
                "linked_user_id": user_id,
            },
        )

        updated = update_provider_prospect(
            owner_actor(),
            prospect["id"],
            {
                "status": "activated",
                "linked_user_id": user_id,
                "linked_provider_profile_id": profile_id,
            },
        )
        assert updated["status"] == "activated"
        assert updated["activated_at"] is not None
        assert updated["observed_onboarding"]["verification_status"] == "verified"
        assert updated["observed_onboarding"]["active_schedule_count"] == 1

        metrics = provider_network_metrics(owner_actor())
        assert metrics["activated_count"] == 1
        assert metrics["linked_verified_profile_count"] == 1


def test_provider_prospect_link_type_mismatch_is_rejected(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        user_id, profile_id = create_verified_doctor(db)

        failed = False
        try:
            create_provider_prospect(
                owner_actor(),
                {
                    "provider_type": "hospital",
                    "source_type": "manual_outreach",
                    "organization_name": "Wrong Type Hospital",
                    "status": "profile_created",
                    "linked_user_id": user_id,
                    "linked_provider_profile_id": profile_id,
                },
            )
        except ValueError:
            failed = True
        assert failed is True


def test_provider_network_dashboard_and_api_are_owner_only(tmp_path):
    _app, client = make_client(tmp_path)

    assert client.get("/admin/startup/provider-network").status_code in {302, 401, 403}
    assert client.get("/api/v1/admin/startup/provider-network").status_code in {302, 401, 403}

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminStrong123"},
    )
    token = login.get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/v1/admin/startup/provider-network",
        headers=headers,
        json={
            "provider_type": "pharmacy",
            "source_type": "inbound",
            "organization_name": "API Pharmacy",
            "contact_phone": "8888888888",
        },
    )
    assert created.status_code == 201

    listed = client.get("/api/v1/admin/startup/provider-network", headers=headers)
    assert listed.status_code == 200
    payload = listed.get_json()
    assert payload["metrics"]["prospect_count"] == 1
    assert len(payload["prospects"]) == 1


def test_institution_pilot_source_requires_real_linked_pilot(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        missing_link_failed = False
        try:
            create_provider_prospect(
                owner_actor(),
                {
                    "provider_type": "doctor",
                    "source_type": "institution_pilot",
                    "organization_name": "Pilot Doctor",
                    "status": "discovered",
                },
            )
        except ValueError:
            missing_link_failed = True
        assert missing_link_failed is True

        bad_link_failed = False
        try:
            create_provider_prospect(
                owner_actor(),
                {
                    "provider_type": "doctor",
                    "source_type": "institution_pilot",
                    "linked_pilot_id": 999999,
                    "organization_name": "Pilot Doctor",
                    "status": "discovered",
                },
            )
        except ValueError:
            bad_link_failed = True
        assert bad_link_failed is True

        pilot = create_institution_pilot(
            owner_actor(),
            {"organization_name": "Provider Pilot", "organization_type": "hospital"},
        )
        prospect = create_provider_prospect(
            owner_actor(),
            {
                "provider_type": "doctor",
                "source_type": "institution_pilot",
                "linked_pilot_id": pilot["id"],
                "organization_name": "Pilot Doctor",
                "status": "discovered",
            },
        )
        assert prospect["linked_pilot_id"] == pilot["id"]
        assert prospect["linked_pilot_name"] == "Provider Pilot"

        scoped = list_provider_prospects(owner_actor(), linked_pilot_id=pilot["id"])
        assert [item["id"] for item in scoped] == [prospect["id"]]

        metrics = provider_network_metrics(owner_actor())
        assert metrics["pilot_linked_prospect_count"] == 1
