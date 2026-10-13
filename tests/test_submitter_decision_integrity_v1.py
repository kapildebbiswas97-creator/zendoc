"""Regression: missing named submit buttons may never authorize approvals.

Browser disabling a clicked submit button used to remove its form name/value.
Server must fail closed even when JavaScript, proxies or navigation fail.
"""
from pathlib import Path

from zendoc.db import get_db
from zendoc.organization_service import create_organization, request_membership
from tests.test_milestone1 import make_app, login_web, register_web


ROOT = Path(__file__).resolve().parents[1]


def _setup_owner_and_pending_membership(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "org-member@example.test", "Member")
    with app.app_context():
        db = get_db()
        owner = dict(db.execute(
            "SELECT * FROM users WHERE email_normalized='admin@example.com'"
        ).fetchone())
        member = dict(db.execute(
            "SELECT * FROM users WHERE email_normalized='org-member@example.test'"
        ).fetchone())
        org = create_organization(owner, {
            "name": "Consent-First Test Hospital",
            "organization_type": "hospital",
        })
        membership = request_membership(member, org["id"], "member")
    assert login_web(client, "admin", "admin@example.com", "AdminStrong123").status_code == 200
    with client.session_transaction() as sess:
        csrf = sess["csrf_token"]
    return app, client, org["id"], membership["id"], csrf


def _statuses(app, org_id, membership_id):
    with app.app_context():
        db = get_db()
        org = db.execute(
            "SELECT verification_status FROM provider_organizations WHERE id=?",
            (org_id,),
        ).fetchone()["verification_status"]
        membership = db.execute(
            "SELECT status FROM organization_memberships WHERE id=?",
            (membership_id,),
        ).fetchone()["status"]
        return org, membership


def test_missing_submit_status_never_approves_membership_or_verifies_org(tmp_path):
    app, client, org_id, membership_id, csrf = _setup_owner_and_pending_membership(tmp_path)
    assert _statuses(app, org_id, membership_id) == ("pending", "pending")

    review_url = f"/organizations/{org_id}/memberships/{membership_id}/review"
    organization_url = f"/organizations/{org_id}/verify"
    assert client.post(review_url, data={"csrf_token": csrf}).status_code == 302
    assert client.post(organization_url, data={"csrf_token": csrf}).status_code == 302
    assert _statuses(app, org_id, membership_id) == ("pending", "pending")

    assert client.post(review_url, data={"csrf_token": csrf, "status": ""}).status_code == 302
    assert client.post(organization_url, data={"csrf_token": csrf, "status": ""}).status_code == 302
    assert _statuses(app, org_id, membership_id) == ("pending", "pending")


def test_explicit_rejection_and_verification_are_honored(tmp_path):
    app, client, org_id, membership_id, csrf = _setup_owner_and_pending_membership(tmp_path)
    review_url = f"/organizations/{org_id}/memberships/{membership_id}/review"
    organization_url = f"/organizations/{org_id}/verify"
    assert client.post(review_url, data={"csrf_token": csrf, "status": "rejected"}).status_code == 302
    assert _statuses(app, org_id, membership_id) == ("pending", "rejected")
    assert client.post(organization_url, data={"csrf_token": csrf, "status": "verified"}).status_code == 302
    assert _statuses(app, org_id, membership_id) == ("verified", "rejected")


def test_shared_js_retains_submitter_decision_and_recovers_after_cancel_navigation():
    source = (ROOT / "static/app.js").read_text(encoding="utf-8")
    assert "event.submitter" in source
    assert "proxy.name = submitter.name" in source
    assert "proxy.value = submitter.value" in source
    assert 'proxy.type = "hidden"' in source
    assert "form.appendChild(proxy)" in source
    assert "if (event.defaultPrevented) resetSubmittingForm(form)" in source
    assert 'window.addEventListener("pageshow"' in source
    assert "control.disabled = control.dataset.zendocWasDisabled" in source


def test_server_routes_never_supply_approval_defaults():
    source = (ROOT / "zendoc/organization_health_routes.py").read_text(encoding="utf-8")
    assert 'request.form.get("status", "active")' not in source
    assert 'request.form.get("status", "verified")' not in source
