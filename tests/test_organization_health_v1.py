from zendoc.db import get_db, now_iso
from zendoc.organization_health_service import (
    create_benefit_plan,
    organization_health_snapshot,
    request_health_organization_membership,
    review_organization_membership,
)
from zendoc.organization_service import create_organization, verify_organization
from tests.test_milestone1 import login_web, make_app, make_client, register_web


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def _create_verified_employer():
    org = create_organization(
        owner_actor(),
        {
            "name": "Pilot Employer",
            "organization_type": "employer",
            "city": "Kalyani",
            "state": "West Bengal",
        },
    )
    return verify_organization(owner_actor(), org["id"], "verified")


def _user(db, email):
    return dict(db.execute(
        "SELECT * FROM users WHERE email_normalized=?",
        (email,),
    ).fetchone())


def test_verified_organization_member_join_and_benefits(tmp_path):
    app, client = make_client(tmp_path)
    with app.app_context():
        org = _create_verified_employer()
        create_benefit_plan(
            owner_actor(),
            org["id"],
            {
                "name": "Preventive screening",
                "benefit_type": "preventive_care",
                "description": "Recorded organization benefit for controlled beta.",
            },
        )

    register_web(client, "patient", "org-member@example.com", "Org Member")
    with app.app_context():
        db = get_db()
        member = _user(db, "org-member@example.com")
        membership = request_health_organization_membership(member, org["organization_uid"])
        assert membership["status"] == "pending"
        row = db.execute(
            "SELECT id FROM organization_memberships WHERE organization_id=? AND user_id=?",
            (org["id"], member["id"]),
        ).fetchone()
        db.execute(
            "UPDATE organization_memberships SET status='active',approved_by=1,updated_at=? WHERE id=?",
            (now_iso(), row["id"]),
        )
        db.commit()

    login_web(client, "patient", "org-member@example.com")
    page = client.get(f"/organizations/{org['id']}")
    assert page.status_code == 200
    assert b"Preventive screening" in page.data
    assert b"Health Command Center" not in page.data


def test_organization_command_center_suppresses_small_group_usage(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        org = _create_verified_employer()
        snapshot = organization_health_snapshot(owner_actor(), org["id"], days=30)
        assert snapshot["privacy"]["suppressed"] is True
        assert snapshot["usage"] is None
        assert snapshot["privacy"]["minimum_group_size"] == 5


def test_organization_command_center_exposes_aggregate_not_clinical_content(tmp_path):
    app, client = make_client(tmp_path)
    with app.app_context():
        org = _create_verified_employer()

    member_ids = []
    for index in range(5):
        email = f"aggregate-member-{index}@example.com"
        register_web(client, "patient", email, f"Aggregate Member {index}")
        client.get("/logout")
        with app.app_context():
            db = get_db()
            user = _user(db, email)
            member_ids.append(int(user["id"]))
            db.execute(
                """
                INSERT INTO organization_memberships
                (organization_id,user_id,membership_role,status,requested_by,approved_by,created_at,updated_at)
                VALUES (?,?,'member','active',1,1,?,?)
                """,
                (org["id"], user["id"], now_iso(), now_iso()),
            )
            db.commit()

    with app.app_context():
        db = get_db()
        for user_id in member_ids:
            db.execute(
                """
                INSERT INTO product_analytics_events
                (user_id,event_type,category,geography_node_id,location_hash,result_count,useful_result,source_tiers_json,metadata_json,created_at)
                VALUES (?,'healthcare_search','doctor',NULL,NULL,1,1,'{}','{}',?)
                """,
                (user_id, now_iso()),
            )
        db.commit()

        snapshot = organization_health_snapshot(owner_actor(), org["id"], days=30)
        assert snapshot["privacy"]["suppressed"] is False
        assert snapshot["usage"]["healthcare_searches"] == 5
        assert snapshot["usage"]["searches_with_results"] == 5
        payload = str(snapshot).lower()
        assert "diagnosis" not in payload
        assert "journal" in snapshot["truth_notice"].lower()
        assert "clinical records" in snapshot["truth_notice"].lower()


def test_organization_web_home_allows_join_request_but_not_unverified_org(tmp_path):
    app, client = make_client(tmp_path)
    with app.app_context():
        org = create_organization(
            owner_actor(),
            {"name": "Pending Employer", "organization_type": "employer"},
        )

    register_web(client, "patient", "pending-join@example.com", "Pending Join")
    login_web(client, "patient", "pending-join@example.com")
    home = client.get("/organizations")
    assert home.status_code == 200
    token = home.data.decode().split('name="csrf_token" value="', 1)[1].split('"', 1)[0]
    response = client.post(
        "/organizations/join",
        data={"csrf_token": token, "organization_uid": org["organization_uid"]},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"not verified for member enrollment" in response.data



def test_provider_account_cannot_join_as_employee_health_member(tmp_path):
    app, client = make_client(tmp_path)
    with app.app_context():
        org = _create_verified_employer()

    register_web(client, "doctor", "org-doctor@example.com", "Org Doctor")
    with app.app_context():
        db = get_db()
        doctor = _user(db, "org-doctor@example.com")
        try:
            request_health_organization_membership(doctor, org["organization_uid"])
            assert False, "Provider account must not become an employee/member health account."
        except PermissionError:
            pass


def test_privacy_threshold_counts_patient_members_not_managers(tmp_path):
    app, client = make_client(tmp_path)
    with app.app_context():
        org = _create_verified_employer()

    patient_ids = []
    for index in range(4):
        email = f"privacy-member-{index}@example.com"
        register_web(client, "patient", email, f"Privacy Member {index}")
        client.get("/logout")
        with app.app_context():
            db = get_db()
            user = _user(db, email)
            patient_ids.append(int(user["id"]))
            db.execute(
                """
                INSERT INTO organization_memberships
                (organization_id,user_id,membership_role,status,requested_by,approved_by,created_at,updated_at)
                VALUES (?,?,'member','active',1,1,?,?)
                """,
                (org["id"], user["id"], now_iso(), now_iso()),
            )
            db.commit()

    with app.app_context():
        # The owner membership exists too, but must not make four patient members
        # satisfy the five-member privacy threshold.
        snapshot = organization_health_snapshot(owner_actor(), org["id"], days=30)
        assert snapshot["membership"]["eligible_active_members"] == 4
        assert snapshot["privacy"]["suppressed"] is True
        assert snapshot["usage"] is None


def test_membership_review_rejects_cross_organization_route_mismatch(tmp_path):
    app, client = make_client(tmp_path)
    with app.app_context():
        org_a = _create_verified_employer()
        org_b = create_organization(
            owner_actor(),
            {"name": "Second Employer", "organization_type": "employer"},
        )
        org_b = verify_organization(owner_actor(), org_b["id"], "verified")

    register_web(client, "patient", "cross-org-member@example.com", "Cross Org Member")
    with app.app_context():
        db = get_db()
        patient = _user(db, "cross-org-member@example.com")
        membership = request_health_organization_membership(patient, org_a["organization_uid"])
        try:
            review_organization_membership(
                owner_actor(),
                org_b["id"],
                membership["id"],
                "active",
            )
            assert False, "Cross-organization membership review must fail closed."
        except PermissionError:
            pass
        stored = db.execute(
            "SELECT status FROM organization_memberships WHERE id=?",
            (membership["id"],),
        ).fetchone()
        assert stored["status"] == "pending"



def test_non_patient_organization_home_does_not_offer_member_join_form(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "doctor", "org-home-doctor@example.com", "Org Home Doctor")
    login_web(client, "doctor", "org-home-doctor@example.com")
    response = client.get("/organizations")
    assert response.status_code == 200
    assert b"Request membership" not in response.data
    assert b"Employee/member health enrollment is available only to patient/member accounts" in response.data


def test_missing_organization_page_is_clean_404(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "missing-org@example.com", "Missing Org")
    login_web(client, "patient", "missing-org@example.com")
    response = client.get("/organizations/999999", follow_redirects=False)
    assert response.status_code == 404


def test_invalid_analytics_window_falls_back_without_500(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        org = _create_verified_employer()
        snapshot = organization_health_snapshot(owner_actor(), org["id"], days="not-a-number")
        assert snapshot["window_days"] == 30
