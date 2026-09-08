from datetime import datetime, timedelta, timezone

from zendoc.business_api import create_business_api_client, issue_business_api_key
from zendoc.db import get_db
from zendoc.partner_handoffs import (
    create_partner_booking_handoff,
    get_partner_booking_handoff,
    owner_update_partner_booking_handoff,
)
from tests.test_milestone1 import make_app


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def create_verified_provider_with_schedule(db):
    now = "2026-09-08T00:00:00+00:00"
    user_id = db.execute(
        """
        INSERT INTO users
        (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
        VALUES (?,?,?,?,?,1,?,?)
        """,
        ("Dr Handoff", "handoff-doctor@example.com", "handoff-doctor@example.com", "x", "doctor", now, now),
    ).lastrowid
    profile_id = db.execute(
        """
        INSERT INTO provider_profiles
        (user_id,provider_type,specialty,qualifications,license_identifier,organization,address,city,state,
         postal_code,public_phone,verification_status,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,'verified',?,?)
        """,
        (
            user_id, "doctor", "Cardiology", "MBBS", "REG-HANDOFF", "Handoff Clinic",
            "1 Road", "Kalyani", "West Bengal", "741235", "1234567890", now, now,
        ),
    ).lastrowid

    target_date = datetime.now(timezone.utc).date() + timedelta(days=1)
    weekday = target_date.weekday()
    db.execute(
        """
        INSERT INTO provider_schedules
        (provider_profile_id,weekday,start_time,end_time,slot_minutes,active,created_at,updated_at)
        VALUES (?,?,'09:00','10:00',30,1,?,?)
        """,
        (profile_id, weekday, now, now),
    )
    db.commit()
    return int(profile_id), target_date.isoformat() + "T09:00+00:00"


def test_partner_handoff_is_idempotent_and_not_confirmed_until_accepted(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        profile_id, slot = create_verified_provider_with_schedule(get_db())
        partner = create_business_api_client(
            owner_actor(),
            {
                "name": "Handoff Partner",
                "client_type": "employer",
                "allowed_scopes": ["booking_handoff.write"],
            },
        )
        key = issue_business_api_key(owner_actor(), partner["id"], expires_in_days=30)
        from zendoc.business_api import authenticate_business_api_key
        identity = authenticate_business_api_key(key["api_key"], required_scope="booking_handoff.write", endpoint="/test")

        first = create_partner_booking_handoff(
            identity,
            provider_profile_id=profile_id,
            partner_reference="EMP-001",
            requested_for=slot,
            contact_reference="member-ref-123",
        )
        second = create_partner_booking_handoff(
            identity,
            provider_profile_id=profile_id,
            partner_reference="EMP-001",
            requested_for=slot,
            contact_reference="member-ref-123",
        )
        assert first["id"] == second["id"]
        assert first["status"] == "received"
        assert first["booking_confirmed"] is False

        accepted = owner_update_partner_booking_handoff(
            owner_actor(),
            first["id"],
            status="accepted",
            status_note="Operationally accepted.",
        )
        assert accepted["status"] == "accepted"
        assert accepted["booking_confirmed"] is True


def test_partner_handoff_is_cross_tenant_isolated(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        profile_id, slot = create_verified_provider_with_schedule(get_db())
        from zendoc.business_api import authenticate_business_api_key

        client_a = create_business_api_client(
            owner_actor(),
            {"name": "A", "client_type": "hospital", "allowed_scopes": ["booking_handoff.write"]},
        )
        client_b = create_business_api_client(
            owner_actor(),
            {"name": "B", "client_type": "hospital", "allowed_scopes": ["booking_handoff.write"]},
        )
        key_a = issue_business_api_key(owner_actor(), client_a["id"], expires_in_days=30)
        key_b = issue_business_api_key(owner_actor(), client_b["id"], expires_in_days=30)
        identity_a = authenticate_business_api_key(key_a["api_key"], required_scope="booking_handoff.write", endpoint="/a")
        identity_b = authenticate_business_api_key(key_b["api_key"], required_scope="booking_handoff.write", endpoint="/b")

        handoff = create_partner_booking_handoff(
            identity_a,
            provider_profile_id=profile_id,
            partner_reference="A-1",
            requested_for=slot,
        )

        blocked = False
        try:
            get_partner_booking_handoff(identity_b, handoff["id"])
        except LookupError:
            blocked = True
        assert blocked is True


def test_unavailable_slot_is_rejected_and_schema_has_no_clinical_fields(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        profile_id, _slot = create_verified_provider_with_schedule(get_db())
        from zendoc.business_api import authenticate_business_api_key

        partner = create_business_api_client(
            owner_actor(),
            {"name": "Slot Partner", "client_type": "ngo", "allowed_scopes": ["booking_handoff.write"]},
        )
        key = issue_business_api_key(owner_actor(), partner["id"], expires_in_days=30)
        identity = authenticate_business_api_key(key["api_key"], required_scope="booking_handoff.write", endpoint="/test")

        unavailable = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat() + "T23:30+00:00"
        failed = False
        try:
            create_partner_booking_handoff(
                identity,
                provider_profile_id=profile_id,
                partner_reference="BAD-SLOT",
                requested_for=unavailable,
            )
        except ValueError:
            failed = True
        assert failed is True

        columns = {
            row["name"]
            for row in get_db().execute("PRAGMA table_info(partner_booking_handoffs)").fetchall()
        }
        forbidden = {"symptoms", "diagnosis", "prescription", "medical_history", "clinical_notes", "reason"}
        assert forbidden.isdisjoint(columns)
