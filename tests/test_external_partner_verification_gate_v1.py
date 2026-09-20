from zendoc.identity_verification import create_identity_case
from zendoc.carefin_cases import apply_carefin_partner_response
from zendoc.db import get_db
from tests.test_milestone1 import make_app,register_web


def _user(app,email):
    with app.app_context():
        return dict(get_db().execute("SELECT * FROM users WHERE email_normalized=?",(email,)).fetchone())


def test_unverified_ekyc_configuration_falls_back_to_manual(monkeypatch,tmp_path):
    monkeypatch.setenv("ZENDOC_EKYC_PROVIDER","configured_but_unverified")
    monkeypatch.setenv("ZENDOC_EKYC_WEBHOOK_SECRET","secret")
    monkeypatch.setenv("ZENDOC_EKYC_VERIFIED","false")
    app=make_app(tmp_path)
    client=app.test_client()
    register_web(client,"patient","unverified-idv@example.com","Unverified IDV")
    user=_user(app,"unverified-idv@example.com")
    with app.app_context():
        case=create_identity_case(user,{
            "purpose":"account_identity","identifier_type":"other_last4",
            "identifier_last4":"A123","consent":"yes"
        })
        assert case["provider"]=="manual_evidence_review"
        assert case["status"]=="manual_review_required"


def test_unverified_carefin_partner_cannot_change_cases(monkeypatch,tmp_path):
    monkeypatch.setenv("ZENDOC_CAREFIN_PARTNER_NAME","configured_but_unverified")
    monkeypatch.setenv("ZENDOC_CAREFIN_WEBHOOK_SECRET","secret")
    monkeypatch.setenv("ZENDOC_CAREFIN_PARTNER_VERIFIED","false")
    app=make_app(tmp_path)
    with app.app_context():
        try:
            apply_carefin_partner_response(
                {"event_id":"x","case_id":1,"target_state":"CONFIRMED"},
                b"{}","bad"
            )
            assert False
        except PermissionError as exc:
            assert "operator-verified" in str(exc)
