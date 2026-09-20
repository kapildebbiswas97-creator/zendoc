import hashlib
import hmac
import json

from zendoc.carefin_cases import (
    apply_carefin_partner_response,
    create_carefin_case,
    request_case_verification,
    submit_case_evidence,
)
from zendoc.db import get_db
from tests.test_milestone1 import make_app, register_web


def _user(app,email):
    with app.app_context():
        return dict(get_db().execute("SELECT * FROM users WHERE email_normalized=?",(email,)).fetchone())


def test_signed_carefin_partner_can_authoritatively_confirm_case(monkeypatch,tmp_path):
    monkeypatch.setenv("ZENDOC_CAREFIN_PARTNER_NAME","authorized_test_insurer")
    monkeypatch.setenv("ZENDOC_CAREFIN_WEBHOOK_SECRET","carefin-secret")
    monkeypatch.setenv("ZENDOC_CAREFIN_PARTNER_VERIFIED","true")
    app=make_app(tmp_path)
    client=app.test_client()
    register_web(client,"patient","partner-case@example.com","Partner Case")
    user=_user(app,"partner-case@example.com")
    with app.app_context():
        case=create_carefin_case(user,"lic")
        case=submit_case_evidence(
            user,case["id"],evidence_type="POLICY_REFERENCE",evidence_reference="POLICY-123"
        )
        case=request_case_verification(user,case["id"])
        payload={
            "event_id":"insurer-event-1",
            "case_id":case["id"],
            "target_state":"CONFIRMED",
            "evidence_type":"INSURER_RESPONSE",
            "evidence_reference":"INSURER-CONFIRM-9",
        }
        raw=json.dumps(payload,separators=(",",":")).encode()
        sig=hmac.new(b"carefin-secret",raw,hashlib.sha256).hexdigest()
        try:
            apply_carefin_partner_response(payload,raw,"bad")
            assert False
        except PermissionError:
            pass
        result=apply_carefin_partner_response(payload,raw,sig)
        assert result["state"]=="CONFIRMED"
        assert result["authoritative_confirmation"]==1
        again=apply_carefin_partner_response(payload,raw,sig)
        assert again["state"]=="CONFIRMED"
        count=get_db().execute(
            "SELECT COUNT(*) c FROM carefin_partner_events WHERE provider_event_id='insurer-event-1'"
        ).fetchone()["c"]
        assert int(count)==1
