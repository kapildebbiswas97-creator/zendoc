from zendoc.integration_readiness import integration_readiness_snapshot
from tests.test_milestone1 import make_client


def test_integration_center_never_exposes_secret_values(monkeypatch,tmp_path):
    monkeypatch.setenv("ZENDOC_RAZORPAY_KEY_ID","rzp_live_publicish")
    monkeypatch.setenv("ZENDOC_RAZORPAY_KEY_SECRET","VERY_SECRET_PAYMENT")
    monkeypatch.setenv("ZENDOC_RAZORPAY_WEBHOOK_SECRET","VERY_SECRET_WEBHOOK")
    monkeypatch.setenv("ZENDOC_EKYC_PROVIDER","provider")
    monkeypatch.setenv("ZENDOC_EKYC_WEBHOOK_SECRET","VERY_SECRET_EKYC")
    app,client=make_client(tmp_path)
    with app.app_context():
        snapshot=integration_readiness_snapshot()
        rendered=repr(snapshot)
        assert "VERY_SECRET_PAYMENT" not in rendered
        assert "VERY_SECRET_WEBHOOK" not in rendered
        assert "VERY_SECRET_EKYC" not in rendered
        keys={item["key"] for item in snapshot["integrations"]}
        assert {"payments","external_ekyc","carefin_partner","durable_media","webrtc","affiliate"}.issubset(keys)
