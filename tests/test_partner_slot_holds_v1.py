from datetime import datetime, timedelta, timezone

from zendoc.business_api import authenticate_business_api_key, create_business_api_client, issue_business_api_key
from zendoc.db import get_db
from zendoc.partner_handoffs import (
    create_partner_booking_handoff,
    provider_update_partner_booking_handoff,
)
from zendoc.provider_service import available_slots
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
        ("Dr Hold", "hold-doctor@example.com", "hold-doctor@example.com", "x", "doctor", now, now),
    ).lastrowid
    profile_id = db.execute(
        """
        INSERT INTO provider_profiles
        (user_id,provider_type,specialty,qualifications,license_identifier,organization,address,city,state,
         postal_code,public_phone,verification_status,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,'verified',?,?)
        """,
        (
            user_id, "doctor", "Cardiology", "MBBS", "REG-HOLD", "Hold Clinic",
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
    return int(user_id), int(profile_id), target_date.isoformat(), target_date.isoformat() + "T09:00+00:00"


def partner_identity(name):
    partner = create_business_api_client(
        owner_actor(),
        {"name": name, "client_type": "hospital", "allowed_scopes": ["booking_handoff.write"]},
    )
    key = issue_business_api_key(owner_actor(), partner["id"], expires_in_days=30)
    return authenticate_business_api_key(
        key["api_key"],
        required_scope="booking_handoff.write",
        endpoint="/test",
    )


def test_active_partner_hold_removes_slot_and_blocks_competing_partner(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        _provider_user, profile_id, target_date, slot = create_verified_provider_with_schedule(get_db())
        identity_a = partner_identity("Hold A")
        identity_b = partner_identity("Hold B")

        handoff = create_partner_booking_handoff(
            identity_a,
            provider_profile_id=profile_id,
            partner_reference="HOLD-A-1",
            requested_for=slot,
        )
        assert handoff["booking_confirmed"] is False
        assert slot[:16] not in available_slots(profile_id, target_date)

        blocked = False
        try:
            create_partner_booking_handoff(
                identity_b,
                provider_profile_id=profile_id,
                partner_reference="HOLD-B-1",
                requested_for=slot,
            )
        except ValueError:
            blocked = True
        assert blocked is True


def test_same_partner_reference_remains_idempotent_while_slot_is_held(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        _provider_user, profile_id, _target_date, slot = create_verified_provider_with_schedule(get_db())
        identity = partner_identity("Idempotent Partner")

        first = create_partner_booking_handoff(
            identity,
            provider_profile_id=profile_id,
            partner_reference="IDEMP-1",
            requested_for=slot,
        )
        second = create_partner_booking_handoff(
            identity,
            provider_profile_id=profile_id,
            partner_reference="IDEMP-1",
            requested_for=slot,
        )
        assert second["id"] == first["id"]


def test_rejection_releases_slot_and_acceptance_extends_hold_without_confirming_booking(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        provider_user, profile_id, target_date, slot = create_verified_provider_with_schedule(get_db())
        identity = partner_identity("Review Partner")

        handoff = create_partner_booking_handoff(
            identity,
            provider_profile_id=profile_id,
            partner_reference="REVIEW-1",
            requested_for=slot,
        )
        first_expiry = get_db().execute(
            "SELECT expires_at FROM partner_slot_holds WHERE handoff_id=?",
            (handoff["id"],),
        ).fetchone()["expires_at"]

        actor = {"id": provider_user, "role": "doctor", "active": 1}
        accepted = provider_update_partner_booking_handoff(
            actor,
            handoff["id"],
            status="accepted",
            status_note="Accepted for coordination.",
        )
        assert accepted["handoff_accepted"] is True
        assert accepted["booking_confirmed"] is False
        accepted_expiry = get_db().execute(
            "SELECT expires_at FROM partner_slot_holds WHERE handoff_id=?",
            (handoff["id"],),
        ).fetchone()["expires_at"]
        assert accepted_expiry >= first_expiry
        assert slot[:16] not in available_slots(profile_id, target_date)

        provider_update_partner_booking_handoff(
            actor,
            handoff["id"],
            status="rejected",
            status_note="Unable to coordinate.",
        )
        hold = get_db().execute(
            "SELECT status FROM partner_slot_holds WHERE handoff_id=?",
            (handoff["id"],),
        ).fetchone()
        assert hold["status"] == "released"
        assert slot[:16] in available_slots(profile_id, target_date)
