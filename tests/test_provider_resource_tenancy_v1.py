from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from zendoc.db import get_db, now_iso
from zendoc.diagnostic_service import (
    complete_diagnostic_test,
    list_diagnostic_refresh_queue,
    reconfirm_diagnostic_offer,
)
from zendoc.inventory_service import (
    list_inventory_refresh_queue,
    reconfirm_inventory_observation,
    update_inventory_observation,
)
from zendoc.organization_service import (
    approve_membership,
    bind_provider_profile,
    create_location,
    create_organization,
    provider_resource_context,
    request_membership,
    verify_organization,
)
from zendoc.provider_service import available_slots, book_provider_slot, create_schedule
from zendoc.telehealth import get_consultation, request_consultation
from tests.test_milestone1 import make_app


PASSWORD = "StrongPass123"


def _register(client, email, role):
    created = client.post(
        "/api/v1/auth/register",
        json={"name": email, "email": email, "password": PASSWORD, "role": role},
    )
    assert created.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert login.status_code == 200


def _user(app, email):
    with app.app_context():
        return dict(
            get_db().execute(
                "SELECT * FROM users WHERE email_normalized=?",
                (email.lower(),),
            ).fetchone()
        )


def _owner(app):
    with app.app_context():
        return dict(
            get_db().execute(
                "SELECT * FROM users WHERE email_normalized='admin@example.com'"
            ).fetchone()
        )


def _profile(app, user, provider_type):
    with app.app_context():
        db = get_db()
        now = now_iso()
        profile_id = db.execute(
            """
            INSERT INTO provider_profiles
            (user_id, provider_type, specialty, organization, verification_status, created_at, updated_at)
            VALUES (?, ?, 'General', ?, 'verified', ?, ?)
            """,
            (user["id"], provider_type, f"{provider_type.title()} Standalone", now, now),
        ).lastrowid
        db.commit()
        return int(profile_id)


def _bind_verified_org(app, actor, profile_id, org_name, org_type="hospital", location_name="Main Branch"):
    with app.app_context():
        owner = _owner(app)
        org = create_organization(actor, {"name": org_name, "organization_type": org_type})
        verify_organization(owner, org["id"], "verified")
        location = create_location(
            actor,
            org["id"],
            {"name": location_name, "location_type": "branch", "city": "Kalyani"},
        )
        profile = bind_provider_profile(actor, org["id"], location["id"])
        assert profile["id"] == profile_id
        return org, location


def _future_date_for_weekday(weekday):
    day = datetime.now(timezone.utc).date() + timedelta(days=2)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day


def test_standalone_provider_resource_context_remains_null(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register(client, "standalone-doctor@example.com", "doctor")
    doctor = _user(app, "standalone-doctor@example.com")
    _profile(app, doctor, "doctor")

    with app.app_context():
        assert provider_resource_context(doctor["id"]) == {
            "organization_id": None,
            "organization_location_id": None,
        }


def test_bound_provider_schedule_and_appointment_are_tenant_stamped(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register(client, "tenant-doctor@example.com", "doctor")
    _register(client, "tenant-patient@example.com", "patient")
    doctor = _user(app, "tenant-doctor@example.com")
    patient = _user(app, "tenant-patient@example.com")
    profile_id = _profile(app, doctor, "doctor")

    with app.app_context():
        org, location = _bind_verified_org(
            app, doctor, profile_id, "Tenant Hospital", "hospital", "OPD Branch"
        )
        target_date = _future_date_for_weekday(2)
        create_schedule(
            doctor,
            {
                "weekday": target_date.weekday(),
                "start_time": "10:00",
                "end_time": "12:00",
                "slot_minutes": 30,
            },
        )
        schedule = get_db().execute(
            "SELECT * FROM provider_schedules WHERE provider_profile_id=? ORDER BY id DESC LIMIT 1",
            (profile_id,),
        ).fetchone()
        assert schedule["organization_id"] == org["id"]
        assert schedule["organization_location_id"] == location["id"]

        slots = available_slots(profile_id, target_date.isoformat())
        assert slots
        appointment_time = slots[0]
        book_provider_slot(patient, profile_id, appointment_time, "Tenant test")

        appointment = get_db().execute(
            "SELECT * FROM appointments WHERE provider_profile_id=? ORDER BY id DESC LIMIT 1",
            (profile_id,),
        ).fetchone()
        assert appointment["organization_id"] == org["id"]
        assert appointment["organization_location_id"] == location["id"]


def test_old_unscoped_schedule_not_promoted_after_branch_binding(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register(client, "schedule-doctor@example.com", "doctor")
    doctor = _user(app, "schedule-doctor@example.com")
    profile_id = _profile(app, doctor, "doctor")

    with app.app_context():
        target_date = _future_date_for_weekday(3)
        db = get_db()
        db.execute(
            """
            INSERT INTO provider_schedules
            (provider_profile_id, weekday, start_time, end_time, slot_minutes, active, created_at, updated_at)
            VALUES (?, ?, '09:00', '10:00', 30, 1, ?, ?)
            """,
            (profile_id, target_date.weekday(), now_iso(), now_iso()),
        )
        db.commit()

        _bind_verified_org(app, doctor, profile_id, "Scoped Hospital", "hospital", "New Branch")
        assert available_slots(profile_id, target_date.isoformat()) == []


def test_inventory_observation_inherits_pharmacy_tenant(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register(client, "tenant-pharmacy@example.com", "pharmacy")
    pharmacy = _user(app, "tenant-pharmacy@example.com")
    profile_id = _profile(app, pharmacy, "pharmacy")

    with app.app_context():
        org, location = _bind_verified_org(
            app, pharmacy, profile_id, "Tenant Pharmacy Network", "pharmacy_network", "Kalyani Store"
        )
        db = get_db()
        sku = db.execute(
            """
            INSERT INTO medication_skus
            (sku_code,name,generic_name,form,pack_size,pack_unit,mrp_inr,rx_required,data_mode,created_at)
            VALUES ('TEN-SKU-1','Tenant Medicine','Tenant Generic','tablet',1,'tablet',10,0,'LIVE',?)
            """,
            (now_iso(),),
        )
        db.commit()
        observation = update_inventory_observation(
            pharmacy["id"], sku.lastrowid, 5, 8.0, stock_status="CONFIRMED"
        )
        assert observation["organization_id"] == org["id"]
        assert observation["organization_location_id"] == location["id"]


def test_diagnostic_booking_inherits_assigned_lab_tenant_and_rejects_moved_branch(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register(client, "diag-patient-tenant@example.com", "patient")
    _register(client, "diag-lab-tenant@example.com", "hospital")
    patient = _user(app, "diag-patient-tenant@example.com")
    lab = _user(app, "diag-lab-tenant@example.com")
    profile_id = _profile(app, lab, "diagnostic_centre")

    with app.app_context():
        org, location = _bind_verified_org(
            app, lab, profile_id, "Diagnostic Network", "diagnostic_network", "Lab Branch A"
        )
        db = get_db()
        test_id = db.execute(
            """
            INSERT INTO diagnostic_catalog
            (code,name,category,fasting_required,sample_type,tat_hours,standard_price_inr,created_at)
            VALUES ('TEN-DIAG','Tenant Diagnostic','general',0,'blood',24,100,?)
            """,
            (now_iso(),),
        ).lastrowid
        db.execute(
            """
            INSERT INTO diagnostic_bookings
            (booking_uid,patient_id,booked_by,lab_id,test_id,collection_type,scheduled_date,address,status,
             price_inr,organization_id,organization_location_id,created_at,updated_at)
            VALUES ('tenant-diag-booking',?,?,?,?,'lab_visit','2026-12-20','Lab','requested',100,?,?,?,?)
            """,
            (
                patient["id"], patient["id"], lab["id"], test_id,
                org["id"], location["id"], now_iso(), now_iso()
            ),
        )
        db.commit()
        booking_id = db.execute(
            "SELECT id FROM diagnostic_bookings WHERE booking_uid='tenant-diag-booking'"
        ).fetchone()["id"]

        location_b = create_location(
            lab, org["id"], {"name": "Lab Branch B", "location_type": "branch", "city": "Kalyani"}
        )
        bind_provider_profile(lab, org["id"], location_b["id"])

        with pytest.raises(PermissionError):
            complete_diagnostic_test(lab, booking_id, "Completed")


def test_telehealth_consultation_and_room_keep_doctor_tenant(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register(client, "tele-patient@example.com", "patient")
    _register(client, "tele-doctor@example.com", "doctor")
    patient = _user(app, "tele-patient@example.com")
    doctor = _user(app, "tele-doctor@example.com")
    profile_id = _profile(app, doctor, "doctor")

    with app.app_context():
        org, location = _bind_verified_org(
            app, doctor, profile_id, "Tele Hospital", "hospital", "Tele Branch"
        )
        consultation = request_consultation(
            patient,
            {
                "doctor_id": doctor["id"],
                "consultation_type": "chat",
                "reason": "Follow up",
            },
        )
        assert consultation["organization_id"] == org["id"]
        assert consultation["organization_location_id"] == location["id"]

        from zendoc.telehealth import update_consultation_status
        updated = update_consultation_status(doctor, consultation["id"], "accepted")
        assert updated["room_id"] is not None
        room = get_db().execute(
            "SELECT * FROM consultation_rooms WHERE consultation_id=?",
            (consultation["id"],),
        ).fetchone()
        assert room["organization_id"] == org["id"]
        assert room["organization_location_id"] == location["id"]


def test_cross_branch_doctor_cannot_access_old_tenant_consultation_after_move(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register(client, "move-patient@example.com", "patient")
    _register(client, "move-doctor@example.com", "doctor")
    patient = _user(app, "move-patient@example.com")
    doctor = _user(app, "move-doctor@example.com")
    profile_id = _profile(app, doctor, "doctor")

    with app.app_context():
        org, location_a = _bind_verified_org(
            app, doctor, profile_id, "Move Hospital", "hospital", "Branch A"
        )
        consultation = request_consultation(
            patient,
            {"doctor_id": doctor["id"], "consultation_type": "chat", "reason": "Initial"},
        )
        location_b = create_location(
            doctor, org["id"], {"name": "Branch B", "location_type": "branch", "city": "Kalyani"}
        )
        bind_provider_profile(doctor, org["id"], location_b["id"])
        with pytest.raises(PermissionError):
            get_consultation(doctor, consultation["id"])


def test_moved_branch_pharmacy_cannot_operate_old_branch_order(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register(client, "move-pharmacy@example.com", "pharmacy")
    _register(client, "move-order-patient@example.com", "patient")
    pharmacy = _user(app, "move-pharmacy@example.com")
    patient = _user(app, "move-order-patient@example.com")
    profile_id = _profile(app, pharmacy, "pharmacy")

    with app.app_context():
        org, location_a = _bind_verified_org(
            app, pharmacy, profile_id, "Move Pharmacy Network", "pharmacy_network", "Store A"
        )
        db = get_db()
        order_id = db.execute(
            """
            INSERT INTO medicine_orders
            (patient_id, ordered_by, pharmacy_id, items_json, delivery_address, status, tracking_status,
             organization_id, organization_location_id, created_at, updated_at)
            VALUES (?, ?, ?, '[]', 'Test Address', 'pending', 'SUBMITTED', ?, ?, ?, ?)
            """,
            (
                patient["id"], patient["id"], pharmacy["id"],
                org["id"], location_a["id"], now_iso(), now_iso()
            ),
        ).lastrowid
        db.commit()

        location_b = create_location(
            pharmacy, org["id"], {"name": "Store B", "location_type": "branch", "city": "Kalyani"}
        )
        bind_provider_profile(pharmacy, org["id"], location_b["id"])

        from zendoc.order_service import acknowledge_order
        with pytest.raises(PermissionError):
            acknowledge_order(pharmacy, order_id, "accept")


def test_moved_branch_doctor_cannot_update_old_branch_appointment(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register(client, "move-appt-doctor@example.com", "doctor")
    _register(client, "move-appt-patient@example.com", "patient")
    doctor = _user(app, "move-appt-doctor@example.com")
    patient = _user(app, "move-appt-patient@example.com")
    profile_id = _profile(app, doctor, "doctor")

    with app.app_context():
        org, location_a = _bind_verified_org(
            app, doctor, profile_id, "Appointment Hospital", "hospital", "Branch A"
        )
        db = get_db()
        appointment_id = db.execute(
            """
            INSERT INTO appointments
            (patient_id, provider_id, provider_profile_id, provider_name, scheduled_for, reason, status,
             organization_id, organization_location_id, created_at, updated_at)
            VALUES (?, ?, ?, 'Move Doctor', '2026-12-24T10:00', 'Review', 'requested', ?, ?, ?, ?)
            """,
            (
                patient["id"], doctor["id"], profile_id,
                org["id"], location_a["id"], now_iso(), now_iso()
            ),
        ).lastrowid
        db.commit()

        location_b = create_location(
            doctor, org["id"], {"name": "Branch B", "location_type": "branch", "city": "Kalyani"}
        )
        bind_provider_profile(doctor, org["id"], location_b["id"])

    from tests.test_milestone1 import login_web, csrf
    login_web(client, "doctor", "move-appt-doctor@example.com")
    page = client.get("/appointments")
    token = csrf(page.data.decode())
    response = client.post(
        f"/appointments/{appointment_id}/status",
        data={"csrf_token": token, "status": "confirmed"},
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_verified_lab_offer_is_tenant_stamped_and_unverified_provider_is_blocked(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register(client, "offer-lab@example.com", "hospital")
    _register(client, "offer-pending@example.com", "hospital")
    lab = _user(app, "offer-lab@example.com")
    pending = _user(app, "offer-pending@example.com")
    lab_profile = _profile(app, lab, "diagnostic_centre")

    with app.app_context():
        org, location = _bind_verified_org(
            app, lab, lab_profile, "Offer Diagnostic Network", "diagnostic_network", "Offer Branch"
        )
        db = get_db()
        test_id = db.execute(
            """
            INSERT INTO diagnostic_catalog
            (code,name,category,fasting_required,sample_type,tat_hours,standard_price_inr,created_at)
            VALUES ('TEN-OFFER','Tenant Offer Test','general',0,'blood',24,120,?)
            """,
            (now_iso(),),
        ).lastrowid
        db.execute(
            """
            INSERT INTO provider_profiles
            (user_id,provider_type,specialty,organization,verification_status,created_at,updated_at)
            VALUES (?, 'diagnostic_centre','General','Pending Lab','pending',?,?)
            """,
            (pending["id"], now_iso(), now_iso()),
        )
        db.commit()

        from zendoc.diagnostic_service import upsert_diagnostic_offer
        offer = upsert_diagnostic_offer(lab, test_id, 100, True, 10)
        assert offer["organization_id"] == org["id"]
        assert offer["organization_location_id"] == location["id"]

        with pytest.raises(PermissionError):
            upsert_diagnostic_offer(pending, test_id, 90, True, 5)

def test_pharmacy_refresh_queue_and_reconfirm_preserve_tenant(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register(client, "refresh-pharmacy@example.com", "pharmacy")
    pharmacy = _user(app, "refresh-pharmacy@example.com")
    profile_id = _profile(app, pharmacy, "pharmacy")

    with app.app_context():
        org, location = _bind_verified_org(
            app, pharmacy, profile_id, "Refresh Pharmacy Network", "pharmacy_network", "Store A"
        )
        db = get_db()
        sku_id = db.execute(
            """
            INSERT INTO medication_skus
            (sku_code,name,generic_name,form,pack_size,pack_unit,mrp_inr,rx_required,data_mode,created_at)
            VALUES ('REF-SKU-1','Refresh Medicine','Refresh Generic','tablet',1,'tablet',10,0,'LIVE',?)
            """,
            (now_iso(),),
        ).lastrowid
        db.commit()
        observation = update_inventory_observation(
            pharmacy["id"], sku_id, 9, 8.0, stock_status="CONFIRMED"
        )

        old = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
        db.execute(
            "UPDATE inventory_observations SET observed_at=?, updated_at=? WHERE id=?",
            (old, old, observation["id"]),
        )
        db.commit()

        queue = list_inventory_refresh_queue(pharmacy)
        queued = next(item for item in queue["items"] if item["id"] == observation["id"])
        assert queued["needs_refresh"] is True
        assert queued["effective_status"] == "STALE"

        with pytest.raises(ValueError):
            reconfirm_inventory_observation(pharmacy, observation["id"], confirmed_unchanged=False)

        refreshed = reconfirm_inventory_observation(pharmacy, observation["id"], confirmed_unchanged=True)
        assert refreshed["effective_status"] == "CONFIRMED"
        assert refreshed["organization_id"] == org["id"]
        assert refreshed["organization_location_id"] == location["id"]


def test_moved_branch_pharmacy_cannot_reconfirm_old_inventory(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register(client, "refresh-move-pharmacy@example.com", "pharmacy")
    pharmacy = _user(app, "refresh-move-pharmacy@example.com")
    profile_id = _profile(app, pharmacy, "pharmacy")

    with app.app_context():
        org, location_a = _bind_verified_org(
            app, pharmacy, profile_id, "Refresh Move Pharmacy", "pharmacy_network", "Store A"
        )
        db = get_db()
        sku_id = db.execute(
            """
            INSERT INTO medication_skus
            (sku_code,name,generic_name,form,pack_size,pack_unit,mrp_inr,rx_required,data_mode,created_at)
            VALUES ('REF-MOVE-SKU','Move Medicine','Move Generic','tablet',1,'tablet',10,0,'LIVE',?)
            """,
            (now_iso(),),
        ).lastrowid
        db.commit()
        observation = update_inventory_observation(
            pharmacy["id"], sku_id, 4, 7.0, stock_status="CONFIRMED"
        )

        location_b = create_location(
            pharmacy, org["id"], {"name": "Store B", "location_type": "branch", "city": "Kalyani"}
        )
        bind_provider_profile(pharmacy, org["id"], location_b["id"])

        with pytest.raises(PermissionError):
            reconfirm_inventory_observation(pharmacy, observation["id"], confirmed_unchanged=True)


def test_diagnostic_refresh_queue_and_reconfirm_preserve_tenant(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register(client, "refresh-lab@example.com", "hospital")
    lab = _user(app, "refresh-lab@example.com")
    profile_id = _profile(app, lab, "diagnostic_centre")

    with app.app_context():
        org, location = _bind_verified_org(
            app, lab, profile_id, "Refresh Diagnostic Network", "diagnostic_network", "Lab A"
        )
        db = get_db()
        test_id = db.execute(
            """
            INSERT INTO diagnostic_catalog
            (code,name,category,fasting_required,sample_type,tat_hours,standard_price_inr,created_at)
            VALUES ('REF-DIAG','Refresh Diagnostic','general',0,'blood',24,100,?)
            """,
            (now_iso(),),
        ).lastrowid
        old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        offer_id = db.execute(
            """
            INSERT INTO diagnostic_offers
            (lab_id,test_id,price_inr,home_collection_available,home_collection_fee_inr,verified,
             data_mode,observed_at,organization_id,organization_location_id,created_at)
            VALUES (?,?,100,1,0,1,'LIVE',?,?,?,?)
            """,
            (lab["id"], test_id, old, org["id"], location["id"], old),
        ).lastrowid
        db.commit()

        queue = list_diagnostic_refresh_queue(lab)
        queued = next(item for item in queue["items"] if item["id"] == offer_id)
        assert queued["needs_refresh"] is True
        assert queued["availability_state"] == "STALE"

        with pytest.raises(ValueError):
            reconfirm_diagnostic_offer(lab, offer_id, confirmed_unchanged=False)

        refreshed = reconfirm_diagnostic_offer(lab, offer_id, confirmed_unchanged=True)
        assert refreshed["availability_state"] == "CONFIRMED"
        assert refreshed["organization_id"] == org["id"]
        assert refreshed["organization_location_id"] == location["id"]


def test_moved_branch_lab_cannot_reconfirm_old_offer(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register(client, "refresh-move-lab@example.com", "hospital")
    lab = _user(app, "refresh-move-lab@example.com")
    profile_id = _profile(app, lab, "diagnostic_centre")

    with app.app_context():
        org, location_a = _bind_verified_org(
            app, lab, profile_id, "Refresh Move Diagnostic", "diagnostic_network", "Lab A"
        )
        db = get_db()
        test_id = db.execute(
            """
            INSERT INTO diagnostic_catalog
            (code,name,category,fasting_required,sample_type,tat_hours,standard_price_inr,created_at)
            VALUES ('REF-MOVE-DIAG','Refresh Move Diagnostic','general',0,'blood',24,100,?)
            """,
            (now_iso(),),
        ).lastrowid
        offer_id = db.execute(
            """
            INSERT INTO diagnostic_offers
            (lab_id,test_id,price_inr,home_collection_available,home_collection_fee_inr,verified,
             data_mode,observed_at,organization_id,organization_location_id,created_at)
            VALUES (?,?,100,1,0,1,'LIVE',?,?,?,?)
            """,
            (lab["id"], test_id, now_iso(), org["id"], location_a["id"], now_iso()),
        ).lastrowid
        db.commit()

        location_b = create_location(
            lab, org["id"], {"name": "Lab B", "location_type": "branch", "city": "Kalyani"}
        )
        bind_provider_profile(lab, org["id"], location_b["id"])

        with pytest.raises(PermissionError):
            reconfirm_diagnostic_offer(lab, offer_id, confirmed_unchanged=True)

