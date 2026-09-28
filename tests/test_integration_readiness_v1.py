from zendoc.db import get_db, now_iso
from zendoc.operational_fulfilment import ensure_operational_fulfilment_schema
from zendoc.integration_readiness import integration_readiness_snapshot
from tests.test_milestone1 import login_web, make_client


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



def test_production_openstreetmap_fallback_is_configured_but_runtime_bounded(monkeypatch,tmp_path):
    monkeypatch.setenv("ZENDOC_ENV","production")
    monkeypatch.setenv("ZENDOC_PLACES_PROVIDER","none")
    monkeypatch.delenv("ZENDOC_GOOGLE_PLACES_API_KEY", raising=False)
    app,client=make_client(tmp_path)
    with app.app_context():
        snapshot=integration_readiness_snapshot()
        maps=next(item for item in snapshot["integrations"] if item["key"]=="maps")
        assert maps["status"]=="BETA"
        assert maps["external_required"] is True
        assert maps["configuration_present"] is True
        assert maps["required_config"] == []
        assert "production_openstreetmap_fallback" in maps["notes"]



def test_integration_center_explains_configuration_vs_runtime_dependency(monkeypatch,tmp_path):
    monkeypatch.setenv("ZENDOC_ENV","production")
    monkeypatch.setenv("ZENDOC_PLACES_PROVIDER","none")
    monkeypatch.delenv("ZENDOC_GOOGLE_PLACES_API_KEY", raising=False)
    _app,client=make_client(tmp_path)
    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    response=client.get("/admin/integrations")
    assert response.status_code==200
    body=response.data
    assert b"Configuration detected" in body
    assert b"External/runtime dependency" in body
    assert b"No additional credential is required" in body
    assert b"production_openstreetmap_fallback" in body



def test_real_world_fulfilment_rows_are_truth_bounded_without_providers(tmp_path):
    app,_client=make_client(tmp_path)
    with app.app_context():
        snapshot=integration_readiness_snapshot()
        rows={item["key"]:item for item in snapshot["integrations"]}
        assert rows["home_health_fulfilment"]["status"]=="INTEGRATION_REQUIRED"
        assert rows["home_health_fulfilment"]["external_required"] is True
        assert rows["pharmacy_fulfilment"]["status"]=="INTEGRATION_REQUIRED"
        assert rows["pharmacy_fulfilment"]["external_required"] is True
        assert rows["medical_transport_dispatch"]["status"]=="INTEGRATION_REQUIRED"
        assert rows["medical_transport_dispatch"]["external_required"] is True
        assert "does not confirm dispatch" in rows["medical_transport_dispatch"]["notes"]


def test_verified_provider_presence_enables_internal_fulfilment_workflow_without_claiming_delivery(tmp_path):
    app,_client=make_client(tmp_path)
    with app.app_context():
        db=get_db()
        stamp=now_iso()
        home_provider_id=db.execute(
            """
            INSERT INTO users
            (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
            VALUES ('Home Provider','home-ready@example.test','home-ready@example.test','x','hospital',1,?,?)
            """,
            (stamp,stamp),
        ).lastrowid
        db.execute(
            """
            INSERT INTO provider_profiles
            (user_id,provider_type,specialty,organization,verification_status,created_at,updated_at)
            VALUES (?,'hospital','General','Home Ready Hospital','verified',?,?)
            """,
            (home_provider_id,stamp,stamp),
        )
        pharmacy_id=db.execute(
            """
            INSERT INTO users
            (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
            VALUES ('Ready Pharmacy','ready-pharmacy@example.test','ready-pharmacy@example.test','x','pharmacy',1,?,?)
            """,
            (stamp,stamp),
        ).lastrowid
        db.execute(
            """
            INSERT INTO provider_profiles
            (user_id,provider_type,specialty,organization,verification_status,created_at,updated_at)
            VALUES (?,'pharmacy','','Ready Pharmacy','verified',?,?)
            """,
            (pharmacy_id,stamp,stamp),
        )
        ensure_operational_fulfilment_schema()
        db.execute(
            """
            INSERT INTO home_health_provider_services
            (provider_id,service_type,active,observed_at,created_at,updated_at)
            VALUES (?,'doctor_visit',1,?,?,?)
            """,
            (home_provider_id,stamp,stamp,stamp),
        )
        db.commit()

        snapshot=integration_readiness_snapshot()
        rows={item["key"]:item for item in snapshot["integrations"]}
        assert rows["home_health_fulfilment"]["status"]=="BETA"
        assert rows["home_health_fulfilment"]["external_required"] is False
        assert "acceptance/progress" in rows["home_health_fulfilment"]["notes"]
        assert rows["pharmacy_fulfilment"]["status"]=="BETA"
        assert rows["pharmacy_fulfilment"]["external_required"] is False
        assert "never inferred" in rows["pharmacy_fulfilment"]["notes"]
