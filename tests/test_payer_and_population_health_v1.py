"""
ZENDOC Payer & Financial OS and Population & Public Health OS Test Suite v1.
Verifies insurance coverage verification, prior authorization decisions,
non-binding benefit estimation, health cohorts, public health campaigns,
and aggregate de-identified analytics.
"""
import pytest
from tests.test_milestone1 import api_token, make_client
from zendoc.db import get_db, now_iso
from zendoc.payer_financial_os import (
    NON_BINDING_DISCLAIMER,
    estimate_patient_benefit,
    list_coverage_requests,
    list_prior_authorizations,
    record_prior_auth_decision,
    submit_coverage_verification_request,
    submit_prior_authorization,
    update_coverage_request_status,
)
from zendoc.population_health_os import (
    create_health_cohort,
    create_public_health_campaign,
    enroll_patient_in_campaign,
    enroll_patient_in_cohort,
    get_campaign_analytics,
    get_cohort_aggregate_analytics,
    list_campaigns,
    list_cohort_members,
    list_cohorts,
)


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def get_admin_token(client):
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminStrong123", "role": "admin"},
    )
    assert res.status_code == 200, res.data
    return res.json["token"]


def get_user_id(app, email):
    with app.app_context():
        db = get_db()
        row = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        return row["id"] if row else None


def test_payer_coverage_verification_lifecycle(tmp_path):
    app, client = make_client(tmp_path)
    patient_token = api_token(client, "patient1@zendoc.test", role="patient")
    patient_id = get_user_id(app, "patient1@zendoc.test")

    doctor_token = api_token(client, "doc1@zendoc.test", role="doctor")
    doctor_id = get_user_id(app, "doc1@zendoc.test")

    with app.app_context():
        # Submit coverage verification
        req = submit_coverage_verification_request(
            actor={"id": patient_id, "role": "patient"},
            patient_id=patient_id,
            insurer_name="Star Health Insurance",
            coverage_type="outpatient",
            service_type="Cardiology Consultation",
            policy_number="POL-992819",
            estimated_cost_inr=1500.0,
        )
        assert req["status"] == "PENDING_VERIFICATION"
        assert req["integration_status"] == "BLOCKED_EXTERNAL"
        assert "not yet connected" in req["integration_note"]

        # Patient lists coverage requests
        reqs = list_coverage_requests(
            actor={"id": patient_id, "role": "patient"},
            patient_id=patient_id,
        )
        assert len(reqs) == 1
        assert reqs[0]["insurer_name"] == "Star Health Insurance"

        # Update coverage request status (operator/doctor)
        updated = update_coverage_request_status(
            actor={"id": doctor_id, "role": "doctor"},
            request_uid=req["request_uid"],
            new_status="VERIFIED_COVERED",
            verification_notes="Confirmed via payer portal phone verification.",
        )
        assert updated["status"] == "VERIFIED_COVERED"
        assert "not an autonomous ZENDOC determination" in updated["truthful_status_note"]


def test_payer_prior_authorization_lifecycle(tmp_path):
    app, client = make_client(tmp_path)
    patient_token = api_token(client, "patient2@zendoc.test", role="patient")
    patient_id = get_user_id(app, "patient2@zendoc.test")

    doctor_token = api_token(client, "doc2@zendoc.test", role="doctor")
    doctor_id = get_user_id(app, "doc2@zendoc.test")

    with app.app_context():
        # Doctor submits prior auth
        pa = submit_prior_authorization(
            actor={"id": doctor_id, "role": "doctor"},
            patient_id=patient_id,
            insurer_name="HDFC ERGO",
            treatment_type="MRI Lumbar Spine",
            policy_number="HE-44820",
            icd10_codes=["M54.5"],
            cpt_codes=["72148"],
            requesting_provider="Dr. Sharma",
            clinical_notes="Chronic lower back pain refractory to conservative therapy.",
        )
        assert pa["status"] == "SUBMITTED"
        assert pa["integration_status"] == "BLOCKED_EXTERNAL"

        # List prior auths
        auths = list_prior_authorizations(
            actor={"id": patient_id, "role": "patient"},
            patient_id=patient_id,
        )
        assert len(auths) == 1
        assert auths[0]["treatment_type"] == "MRI Lumbar Spine"

        # Record decision
        decision = record_prior_auth_decision(
            actor={"id": doctor_id, "role": "doctor"},
            request_uid=pa["request_uid"],
            decision="APPROVED",
            payer_response="Approved for 1 MRI scan within 30 days.",
            payer_auth_number="AUTH-2026-9921",
        )
        assert decision["decision"] == "APPROVED"
        assert decision["payer_auth_number"] == "AUTH-2026-9921"
        assert "All decisions come from the insurer" in decision["truthful_status_note"]


def test_non_binding_benefit_estimation(tmp_path):
    app, client = make_client(tmp_path)
    patient_token = api_token(client, "patient3@zendoc.test", role="patient")
    patient_id = get_user_id(app, "patient3@zendoc.test")

    with app.app_context():
        estimate = estimate_patient_benefit(
            actor={"id": patient_id, "role": "patient"},
            patient_id=patient_id,
            service_type="Comprehensive Health Check",
            estimated_cost_inr=5000.0,
            estimated_coverage_pct=80.0,
        )
        assert estimate["is_binding"] is False
        assert estimate["estimated_cost_inr"] == 5000.0
        assert estimate["estimated_coverage_inr"] == 4000.0
        assert estimate["estimated_out_of_pocket_inr"] == 1000.0
        assert NON_BINDING_DISCLAIMER in estimate["non_binding_disclaimer"]


def test_population_health_cohort_and_analytics(tmp_path):
    app, client = make_client(tmp_path)
    admin_id = get_user_id(app, "admin@example.com")

    patient_token = api_token(client, "cohort_patient@zendoc.test", role="patient")
    patient_id = get_user_id(app, "cohort_patient@zendoc.test")

    with app.app_context():
        cohort = create_health_cohort(
            actor={"id": admin_id, "role": "admin"},
            name="Type 2 Diabetes High Risk",
            inclusion_criteria={"condition": "diabetes", "hba1c_min": 7.0},
            description="Patients with HbA1c >= 7.0 for targeted glycemic support.",
        )
        assert cohort["name"] == "Type 2 Diabetes High Risk"
        assert cohort["status"] == "active"

        # Enroll patient
        enrolled = enroll_patient_in_cohort(
            actor={"id": admin_id, "role": "admin"},
            cohort_uid=cohort["cohort_uid"],
            patient_id=patient_id,
            enrollment_reason="Elevated baseline biomarker.",
        )
        assert enrolled["patient_id"] == patient_id

        # List members
        members = list_cohort_members(
            actor={"id": admin_id, "role": "admin"},
            cohort_uid=cohort["cohort_uid"],
        )
        assert len(members) == 1
        assert members[0]["patient_id"] == patient_id

        # Aggregate analytics
        analytics = get_cohort_aggregate_analytics(
            actor={"id": admin_id, "role": "admin"},
            cohort_uid=cohort["cohort_uid"],
        )
        assert analytics["aggregate_member_count"] == 1
        assert "All metrics are aggregate counts only" in analytics["de_identified_note"]


def test_public_health_campaign_and_enrollment(tmp_path):
    app, client = make_client(tmp_path)
    admin_id = get_user_id(app, "admin@example.com")

    patient_token = api_token(client, "campaign_pat@zendoc.test", role="patient")
    patient_id = get_user_id(app, "campaign_pat@zendoc.test")

    with app.app_context():
        campaign = create_public_health_campaign(
            actor={"id": admin_id, "role": "admin"},
            title="National Hypertension Awareness 2026",
            campaign_type="screening",
            start_date="2026-10-01",
            target_condition="Hypertension",
            geographic_scope="All India",
        )
        assert campaign["title"] == "National Hypertension Awareness 2026"

        # Patient enrolls
        enrollment = enroll_patient_in_campaign(
            actor={"id": patient_id, "role": "patient"},
            campaign_uid=campaign["campaign_uid"],
            patient_id=patient_id,
        )
        assert enrollment["status"] == "enrolled"
        assert "Patient has opted into" in enrollment["consent_note"]

        # Public listing
        c_list = list_campaigns(status="active")
        assert len(c_list) >= 1
        assert any(c["campaign_uid"] == campaign["campaign_uid"] for c in c_list)

        # Analytics
        analytics = get_campaign_analytics(
            actor={"id": admin_id, "role": "admin"},
            campaign_uid=campaign["campaign_uid"],
        )
        assert analytics["enrolled_count"] == 1
        assert analytics["net_active_reach"] == 1


def test_api_routes_payer_and_population(tmp_path):
    app, client = make_client(tmp_path)
    patient_token = api_token(client, "api_pat@zendoc.test", role="patient")
    patient_id = get_user_id(app, "api_pat@zendoc.test")

    adm_token = get_admin_token(client)

    # Test POST /api/v1/payer/benefits/estimate
    res = client.post(
        "/api/v1/payer/benefits/estimate",
        headers=headers(patient_token),
        json={
            "service_type": "Dental Checkup",
            "estimated_cost_inr": 2000.0,
            "estimated_coverage_pct": 50.0,
        },
    )
    assert res.status_code == 200, res.data
    data = res.get_json()
    assert data["estimated_out_of_pocket_inr"] == 1000.0
    assert data["is_binding"] is False

    # Test POST /api/v1/payer/coverage/verify
    res = client.post(
        "/api/v1/payer/coverage/verify",
        headers=headers(patient_token),
        json={
            "insurer_name": "Bajaj Allianz",
            "coverage_type": "inpatient",
            "service_type": "Appendectomy",
            "estimated_cost_inr": 50000.0,
        },
    )
    assert res.status_code == 201, res.data
    cov = res.get_json()
    assert cov["status"] == "PENDING_VERIFICATION"

    # Test GET /api/v1/payer/coverage/requests
    res = client.get(
        "/api/v1/payer/coverage/requests",
        headers=headers(patient_token),
    )
    assert res.status_code == 200, res.data
    assert len(res.get_json()["coverage_requests"]) == 1

    # Test POST /api/v1/population/campaigns
    res = client.post(
        "/api/v1/population/campaigns",
        headers=headers(adm_token),
        json={
            "title": "Universal Diabetes Screening Drive",
            "campaign_type": "screening",
            "start_date": "2026-10-15",
            "target_condition": "Diabetes",
        },
    )
    assert res.status_code == 201, res.data
    camp_uid = res.get_json()["campaign_uid"]

    # Test public GET /api/v1/population/campaigns
    res = client.get("/api/v1/population/campaigns")
    assert res.status_code == 200, res.data
    assert res.get_json()["count"] >= 1
