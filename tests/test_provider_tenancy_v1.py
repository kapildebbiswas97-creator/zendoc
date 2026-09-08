from __future__ import annotations

import pytest

from zendoc.db import get_db, now_iso
from zendoc.human_operations import create_staff_task, upsert_staff_profile
from zendoc.organization_service import (
    active_membership,
    approve_membership,
    bind_provider_profile,
    create_organization,
    request_membership,
    verify_organization,
)
from tests.test_milestone1 import make_app
from tests.test_milestone7 import headers


PASSWORD = "StrongPass123"


def _register(client, email, role):
    r = client.post(
        "/api/v1/auth/register",
        json={"name": email, "email": email, "password": PASSWORD, "role": role},
    )
    assert r.status_code == 201
    l = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert l.status_code == 200
    return l.get_json()["token"]


def _user(app, email):
    with app.app_context():
        return dict(
            get_db().execute(
                "SELECT * FROM users WHERE email_normalized=?",
                (email.lower(),),
            ).fetchone()
        )


def _provider_profile(app, user_id, organization_text=""):
    with app.app_context():
        db = get_db()
        now = now_iso()
        pid = db.execute(
            """
            INSERT INTO provider_profiles
            (user_id, provider_type, specialty, organization, verification_status, created_at, updated_at)
            VALUES (?, 'doctor', 'General', ?, 'verified', ?, ?)
            """,
            (user_id, organization_text, now, now),
        ).lastrowid
        db.commit()
        return int(pid)


def test_free_text_organization_does_not_create_trusted_membership(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register(client, "free-text-doctor@example.com", "doctor")
    doctor = _user(app, "free-text-doctor@example.com")
    _provider_profile(app, doctor["id"], "Apollo Hospitals")

    with app.app_context():
        assert active_membership(doctor["id"]) is None
        row = get_db().execute(
            "SELECT organization, organization_id FROM provider_profiles WHERE user_id=?",
            (doctor["id"],),
        ).fetchone()
        assert row["organization"] == "Apollo Hospitals"
        assert row["organization_id"] is None


def test_provider_can_create_org_and_receives_active_owner_membership(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register(client, "org-owner@example.com", "hospital")
    owner = _user(app, "org-owner@example.com")

    with app.app_context():
        org = create_organization(
            owner,
            {"name": "Kalyani Health Network", "organization_type": "hospital", "city": "Kalyani"},
        )
        membership = active_membership(owner["id"], org["id"])
        assert membership is not None
        assert membership["membership_role"] == "owner"
        assert membership["status"] == "active"


def test_membership_approval_is_tenant_scoped(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register(client, "org-a-owner@example.com", "hospital")
    _register(client, "org-b-owner@example.com", "hospital")
    _register(client, "member@example.com", "doctor")
    owner_a = _user(app, "org-a-owner@example.com")
    owner_b = _user(app, "org-b-owner@example.com")
    member = _user(app, "member@example.com")

    with app.app_context():
        org_a = create_organization(owner_a, {"name": "Org A", "organization_type": "hospital"})
        org_b = create_organization(owner_b, {"name": "Org B", "organization_type": "hospital"})
        pending = request_membership(member, org_a["id"], "doctor")

        with pytest.raises(PermissionError):
            approve_membership(owner_b, pending["id"], "active")

        approved = approve_membership(owner_a, pending["id"], "active")
        assert approved["status"] == "active"
        assert approved["organization_id"] == org_a["id"]
        assert approved["organization_id"] != org_b["id"]


def test_provider_profile_binding_requires_active_membership(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register(client, "bind-owner@example.com", "hospital")
    _register(client, "bind-doctor@example.com", "doctor")
    owner = _user(app, "bind-owner@example.com")
    doctor = _user(app, "bind-doctor@example.com")
    _provider_profile(app, doctor["id"], "Bind Org")

    with app.app_context():
        org = create_organization(owner, {"name": "Bind Org", "organization_type": "hospital"})
        request_membership(doctor, org["id"], "doctor")

        with pytest.raises(PermissionError):
            bind_provider_profile(doctor, org["id"])

        verify_organization(
            dict(get_db().execute("SELECT * FROM users WHERE email_normalized='admin@example.com'").fetchone()),
            org["id"],
            "verified",
        )

        pending = get_db().execute(
            "SELECT * FROM organization_memberships WHERE organization_id=? AND user_id=?",
            (org["id"], doctor["id"]),
        ).fetchone()
        approve_membership(owner, pending["id"], "active")

        profile = bind_provider_profile(doctor, org["id"])
        assert profile["organization_id"] == org["id"]


def test_cross_organization_staff_assignment_is_blocked(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register(client, "tenant-a-owner@example.com", "hospital")
    _register(client, "tenant-a-doctor@example.com", "doctor")
    _register(client, "tenant-b-owner@example.com", "hospital")
    _register(client, "tenant-b-staff@example.com", "doctor")
    _register(client, "tenant-patient@example.com", "patient")

    owner_a = _user(app, "tenant-a-owner@example.com")
    doctor_a = _user(app, "tenant-a-doctor@example.com")
    owner_b = _user(app, "tenant-b-owner@example.com")
    staff_b = _user(app, "tenant-b-staff@example.com")
    patient = _user(app, "tenant-patient@example.com")

    with app.app_context():
        org_a = create_organization(owner_a, {"name": "Tenant A", "organization_type": "hospital"})
        org_b = create_organization(owner_b, {"name": "Tenant B", "organization_type": "hospital"})

        ma = request_membership(doctor_a, org_a["id"], "doctor")
        approve_membership(owner_a, ma["id"], "active")
        mb = request_membership(staff_b, org_b["id"], "staff")
        approve_membership(owner_b, mb["id"], "active")

        # Staff profiles are owner-controlled. Bind the staff account to Org B directly
        # after verifying the active membership, mirroring the owner management flow.
        db = get_db()
        db.execute(
            """
            INSERT INTO staff_profiles
            (user_id, staff_type, service_area, status, verified, organization_id, created_at, updated_at)
            VALUES (?, 'care_coordinator', 'Kalyani', 'available', 1, ?, ?, ?)
            """,
            (staff_b["id"], org_b["id"], now_iso(), now_iso()),
        )
        db.execute(
            """
            INSERT INTO appointments
            (patient_id, provider_id, provider_name, scheduled_for, reason, status, created_at, updated_at)
            VALUES (?, ?, 'Tenant A Doctor', '2026-12-20T10:00', 'Review', 'confirmed', ?, ?)
            """,
            (patient["id"], doctor_a["id"], now_iso(), now_iso()),
        )
        db.commit()

        with pytest.raises(PermissionError):
            create_staff_task(
                doctor_a,
                {
                    "task_type": "follow_up",
                    "title": "Cross tenant task",
                    "patient_id": patient["id"],
                    "assigned_staff_id": staff_b["id"],
                },
            )


def test_owner_only_global_org_listing_endpoint(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    patient_token = _register(client, "org-list-patient@example.com", "patient")

    denied = client.get(
        "/api/v1/admin/provider-organizations",
        headers=headers(patient_token),
    )
    assert denied.status_code == 403

    owner_login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminStrong123"},
    )
    assert owner_login.status_code == 200
    allowed = client.get(
        "/api/v1/admin/provider-organizations",
        headers=headers(owner_login.get_json()["token"]),
    )
    assert allowed.status_code == 200
    assert "organizations" in allowed.get_json()


def test_unverified_organization_cannot_bind_provider_profile(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    _register(client, "pending-org-owner@example.com", "hospital")
    _register(client, "pending-org-doctor@example.com", "doctor")
    owner = _user(app, "pending-org-owner@example.com")
    doctor = _user(app, "pending-org-doctor@example.com")
    _provider_profile(app, doctor["id"], "Pending Org")

    with app.app_context():
        org = create_organization(owner, {"name": "Pending Org", "organization_type": "hospital"})
        membership = request_membership(doctor, org["id"], "doctor")
        approve_membership(owner, membership["id"], "active")
        with pytest.raises(PermissionError):
            bind_provider_profile(doctor, org["id"])
