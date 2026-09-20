import hashlib
import hmac
import json

from zendoc.db import get_db
from zendoc.identity_verification import (
    apply_external_result,
    create_identity_case,
    get_identity_case,
    owner_review_identity_case,
)
from tests.test_milestone1 import make_app, register_web


def _user(app,email):
    with app.app_context():
        return dict(get_db().execute("SELECT * FROM users WHERE email_normalized=?",(email,)).fetchone())


def test_identity_case_rejects_full_identifier_and_manual_is_not_external(tmp_path):
    app=make_app(tmp_path)
    client=app.test_client()
    register_web(client,"patient","idv@example.com","IDV User")
    user=_user(app,"idv@example.com")
    with app.app_context():
        try:
            create_identity_case(user,{
                "purpose":"account_identity","identifier_type":"aadhaar_last4",
                "identifier_last4":"123456789012","consent":"yes"
            })
            assert False
        except ValueError:
            pass
        case=create_identity_case(user,{
            "purpose":"account_identity","identifier_type":"aadhaar_last4",
            "identifier_last4":"9012","consent":"yes","evidence_reference":"DOC-REF-1"
        })
        assert case["status"]=="manual_review_required"
        owner=dict(get_db().execute("SELECT * FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone())
        reviewed=owner_review_identity_case(owner,case["id"],decision="verified_manual",evidence_reference="DOC-REF-1")
        assert reviewed["manual_identity_reviewed"] is True
        assert reviewed["external_ekyc_verified"] is False


def test_signed_external_ekyc_callback_is_required(monkeypatch,tmp_path):
    monkeypatch.setenv("ZENDOC_EKYC_PROVIDER","authorized_test_provider")
    monkeypatch.setenv("ZENDOC_EKYC_WEBHOOK_SECRET","test-secret")
    monkeypatch.setenv("ZENDOC_EKYC_VERIFIED","true")
    app=make_app(tmp_path)
    client=app.test_client()
    register_web(client,"patient","external-idv@example.com","External IDV")
    user=_user(app,"external-idv@example.com")
    with app.app_context():
        case=create_identity_case(user,{
            "purpose":"account_identity","identifier_type":"pan_last4",
            "identifier_last4":"9ABC","consent":"yes"
        })
        assert case["status"]=="pending_external"
        payload={"case_uid":case["case_uid"],"event_id":"evt-1","status":"verified","provider_reference":"provider-ref-99"}
        raw=json.dumps(payload,separators=(",",":")).encode()
        signature=hmac.new(b"test-secret",raw,hashlib.sha256).hexdigest()
        try:
            apply_external_result(payload,raw,"bad")
            assert False
        except PermissionError:
            pass
        result=apply_external_result(payload,raw,signature)
        assert result["status"]=="verified_external"
        fetched=get_identity_case(user,case["id"])
        assert fetched["external_ekyc_verified"] is True


def test_identity_case_is_private(tmp_path):
    app=make_app(tmp_path)
    a=app.test_client(); b=app.test_client()
    register_web(a,"patient","idv-a@example.com","IDV A")
    register_web(b,"patient","idv-b@example.com","IDV B")
    ua=_user(app,"idv-a@example.com"); ub=_user(app,"idv-b@example.com")
    with app.app_context():
        case=create_identity_case(ua,{
            "purpose":"account_identity","identifier_type":"other_last4",
            "identifier_last4":"A123","consent":"yes"
        })
        try:
            get_identity_case(ub,case["id"])
            assert False
        except PermissionError:
            pass
