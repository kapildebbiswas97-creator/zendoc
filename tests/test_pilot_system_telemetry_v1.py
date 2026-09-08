from zendoc.business_api import authenticate_business_api_key, create_business_api_client, issue_business_api_key
from zendoc.db import get_db
from zendoc.provider_network import create_provider_prospect, update_provider_prospect
from zendoc.institution_pilots import create_institution_pilot, pilot_execution_summary, pilot_system_telemetry
from tests.test_milestone1 import make_app


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}



def create_verified_pilot_doctor(db):
    now = "2026-09-08T00:00:00+00:00"
    user_id = db.execute(
        """
        INSERT INTO users
        (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
        VALUES ('Dr Pilot','pilot-doctor@example.com','pilot-doctor@example.com','x','doctor',1,?,?)
        """,
        (now, now),
    ).lastrowid
    profile_id = db.execute(
        """
        INSERT INTO provider_profiles
        (user_id,provider_type,specialty,qualifications,license_identifier,organization,address,city,state,
         postal_code,public_phone,verification_status,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,'verified',?,?)
        """,
        (
            user_id, "doctor", "General Medicine", "MBBS", "REG-PILOT",
            "Pilot Clinic", "1 Road", "Kalyani", "West Bengal", "741235",
            "1234567890", now, now,
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


def test_pilot_system_telemetry_derives_only_linked_b2b_activity(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        pilot = create_institution_pilot(
            owner_actor(),
            {"organization_name": "Telemetry Hospital", "organization_type": "hospital"},
        )
        client = create_business_api_client(
            owner_actor(),
            {
                "name": "Telemetry Client",
                "client_type": "hospital",
                "pilot_id": pilot["id"],
                "allowed_scopes": ["public_directory.read"],
            },
        )
        key = issue_business_api_key(owner_actor(), client["id"], expires_in_days=30)

        authenticate_business_api_key(
            key["api_key"],
            required_scope="public_directory.read",
            endpoint="/api/v1/business/public-directory",
            method="GET",
        )
        authenticate_business_api_key(
            key["api_key"],
            required_scope="public_directory.read",
            endpoint="/api/v1/business/public-directory",
            method="GET",
        )

        telemetry = pilot_system_telemetry(owner_actor(), pilot["id"], days=30)
        assert telemetry["linked_api_clients"] == 1
        assert telemetry["active_api_clients"] == 1
        assert telemetry["api_requests"] >= 2
        assert telemetry["source_type"] == "system_derived"
        assert "patient_users" not in telemetry
        assert "completed_appointments" not in telemetry

        execution = pilot_execution_summary(owner_actor(), pilot["id"])
        assert execution["system_telemetry"]["linked_api_clients"] == 1
        assert execution["latest_usage"] is None


def test_pilot_system_telemetry_derives_real_provider_activation(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        pilot = create_institution_pilot(
            owner_actor(),
            {
                "organization_name": "Activation Pilot Hospital",
                "organization_type": "hospital",
                "target_provider_seats": 2,
            },
        )
        user_id, profile_id = create_verified_pilot_doctor(get_db())

        prospect = create_provider_prospect(
            owner_actor(),
            {
                "provider_type": "doctor",
                "source_type": "institution_pilot",
                "linked_pilot_id": pilot["id"],
                "organization_name": "Pilot Clinic",
                "status": "registered",
                "linked_user_id": user_id,
            },
        )
        update_provider_prospect(
            owner_actor(),
            prospect["id"],
            {
                "status": "activated",
                "linked_user_id": user_id,
                "linked_provider_profile_id": profile_id,
                "linked_pilot_id": pilot["id"],
            },
        )

        telemetry = pilot_system_telemetry(owner_actor(), pilot["id"])
        network = telemetry["provider_network"]
        assert network["prospect_count"] == 1
        assert network["linked_registered_accounts"] == 1
        assert network["linked_provider_profiles"] == 1
        assert network["linked_verified_profiles"] == 1
        assert network["activated_providers"] == 1
        assert network["activation_rate"] == 1.0

        execution = pilot_execution_summary(owner_actor(), pilot["id"])
        assert execution["system_provider_progress"]["actual"] == 1
        assert execution["system_provider_progress"]["target"] == 2
        assert execution["system_provider_progress"]["progress_rate"] == 0.5
