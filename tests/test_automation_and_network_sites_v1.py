"""
Automation Engine & Network Sites Test Suite.
Verifies trigger-condition-action automation, deterministic state machine,
operator approvals, dead-letter handling, SiteProvisioningAgent, and multi-tenant site runtime.
"""
import pytest
from tests.test_milestone1 import api_token, make_client
from zendoc.db import get_db, now_iso
from zendoc.automation_engine import (
    create_automation_rule,
    list_automation_rules,
    evaluate_automation_rules,
    approve_automation_action,
    reject_automation_action,
    execute_automation_action,
    get_automation_ledger,
)
from zendoc.network_sites import (
    SiteProvisioningAgent,
    get_site_by_slug,
    list_network_sites,
)


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def make_admin(app, user_id):
    with app.app_context():
        db = get_db()
        db.execute("UPDATE users SET role='admin' WHERE id=?", (user_id,))
        db.commit()


def test_automation_rules_and_evaluation(tmp_path):
    app, client = make_client(tmp_path)
    with app.app_context():
        rule = create_automation_rule({
            "name": "Auto Reminder Delivery",
            "trigger_event": "order.delivered",
            "action_type": "set_medicine_reminder",
            "conditions": {"category": "chronic"},
            "requires_approval": False,
        })
        assert rule["name"] == "Auto Reminder Delivery"
        assert rule["trigger_event"] == "order.delivered"

        # Evaluate matching event
        event = {
            "event_type": "order.delivered",
            "payload": {"order_id": 101, "category": "chronic"},
        }
        actions = evaluate_automation_rules(event)
        assert len(actions) == 1
        act = actions[0]
        assert act["state"] == "PENDING"
        assert act["requires_approval"] is False

        # Execute action
        result = execute_automation_action(act["action_id"])
        assert result["state"] == "COMPLETED"
        assert result["attempt"] == 1


def test_operator_approval_and_rejection_workflow(tmp_path):
    app, client = make_client(tmp_path)
    operator = {"id": 1, "role": "admin"}

    with app.app_context():
        rule = create_automation_rule({
            "name": "Care Plan Escalation",
            "trigger_event": "vital.critical",
            "action_type": "notify_on_call_doctor",
            "conditions": {},
            "requires_approval": True,
        })

        event = {
            "event_type": "vital.critical",
            "payload": {"systolic_bp": 195},
        }
        actions = evaluate_automation_rules(event)
        assert len(actions) == 1
        act = actions[0]
        assert act["state"] == "WAITING_APPROVAL"

        # Test rejection on separate action
        act2 = evaluate_automation_rules(event)[0]
        rej_res = reject_automation_action(act2["action_id"], operator, reason="Spurious sensor artifact")
        assert rej_res["state"] == "REJECTED"

        # Test approval
        appr_res = approve_automation_action(act["action_id"], operator)
        assert appr_res["state"] == "COMPLETED"


def test_site_provisioning_agent_for_verified_provider(tmp_path):
    app, client = make_client(tmp_path)
    with app.app_context():
        db = get_db()
        u_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) "
            "VALUES ('Dr. Ananya Roy', 'ananya@example.com', 'ananya@example.com', 'hash', 'doctor', 1, ?, ?)",
            (now_iso(), now_iso()),
        ).lastrowid
        p_id = db.execute(
            "INSERT INTO provider_profiles (user_id, provider_type, organization, city, state, address, verification_status, created_at, updated_at) "
            "VALUES (?, 'doctor', 'Kalyani Heart Care', 'Kalyani', 'West Bengal', 'A-Block Main Road', 'verified', ?, ?)",
            (u_id, now_iso(), now_iso()),
        ).lastrowid
        db.commit()

        actor = {"id": u_id, "role": "doctor"}
        site = SiteProvisioningAgent.provision_site(
            actor=actor,
            entity_type="doctor",
            entity_id=p_id,
            slug="dr-ananya-roy-cardiology",
            custom_data={
                "services": ["Cardiology Consultation", "ECG Review", "Preventive Heart Screening"],
                "tagline": "Evidence-based preventive cardiology in Kalyani",
            },
        )
        assert site is not None
        assert site["slug"] == "dr-ananya-roy-cardiology"
        assert site["provenance"] == "VERIFIED"
        assert site["trust_tier"] == "ZENDOC_VERIFIED"
        assert site["booking_enabled"] == 1
        assert "ECG Review" in site["services"]
        assert site["location"]["city"] == "Kalyani"


def test_site_provisioning_from_public_directory(tmp_path):
    app, client = make_client(tmp_path)
    with app.app_context():
        db = get_db()
        ent_id = db.execute(
            """
            INSERT INTO public_healthcare_entities
            (source_id, source_record_id, name, category, address, city, state, source_trust, created_at, updated_at)
            VALUES ('wb_nhm', 'WB-SDH-01', 'Kalyani Sub-Divisional Hospital', 'hospital', 'Hospital Road', 'Kalyani', 'West Bengal', 'OFFICIAL_PUBLIC_DATA', ?, ?)
            """,
            (now_iso(), now_iso()),
        ).lastrowid
        db.commit()

        actor = {"id": 1, "role": "admin"}
        site = SiteProvisioningAgent.provision_site(
            actor=actor,
            entity_type="hospital",
            entity_id=ent_id,
            slug="kalyani-sdh",
        )
        assert site["slug"] == "kalyani-sdh"
        assert site["provenance"] == "OFFICIAL_SOURCE"
        assert site["trust_tier"] == "PUBLIC_DIRECTORY"
        assert site["booking_enabled"] == 0  # Unclaimed public listings cannot take live bookings


def test_network_site_http_routes(tmp_path):
    app, client = make_client(tmp_path)
    token = api_token(client, "doc-sites@example.com", role="doctor")

    # Provision site via API
    resp = client.post(
        "/api/v1/network-sites/provision",
        json={
            "entity_type": "clinic",
            "title": "Modern Wellness Clinic",
            "slug": "modern-wellness-clinic",
            "custom_data": {
                "services": ["General Practice", "Routine Labs"],
                "location": {"city": "Kolkata"},
            },
        },
        headers=headers(token),
    )
    assert resp.status_code == 201
    assert resp.json["site"]["slug"] == "modern-wellness-clinic"

    # Read via JSON API
    get_resp = client.get("/api/v1/network-sites/modern-wellness-clinic")
    assert get_resp.status_code == 200
    assert get_resp.json["site"]["title"] == "Modern Wellness Clinic"

    # List via API
    list_resp = client.get("/api/v1/network-sites?city=Kolkata")
    assert list_resp.status_code == 200
    assert list_resp.json["count"] >= 1

    # View page (HTML or JSON format)
    page_resp = client.get("/sites/modern-wellness-clinic?format=json")
    assert page_resp.status_code == 200
    assert page_resp.json["site"]["slug"] == "modern-wellness-clinic"
