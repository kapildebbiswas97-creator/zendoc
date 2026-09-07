from datetime import datetime, timedelta, timezone

from zendoc.db import get_db, now_iso
from zendoc.pilot_analytics import pilot_scorecard
from tests.test_milestone1 import make_client


def test_pilot_scorecard_exposes_truthful_operational_metrics(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?, 'patient',1,?,?)",
            ("Pilot Patient", "pilot-metrics-patient@example.com", "pilot-metrics-patient@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        pharmacy_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?, 'pharmacy',1,?,?)",
            ("Pilot Pharmacy", "pilot-metrics-pharmacy@example.com", "pilot-metrics-pharmacy@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        doctor_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?, 'doctor',1,?,?)",
            ("Pilot Doctor", "pilot-metrics-doctor@example.com", "pilot-metrics-doctor@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid

        old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        recent = datetime.now(timezone.utc).isoformat()

        db.execute(
            """
            INSERT INTO medicine_orders
            (patient_id,ordered_by,pharmacy_id,items_json,delivery_address,status,created_at,
             acknowledgement_status,acknowledged_at,tracking_status,data_mode,updated_at)
            VALUES (?,?,?,'[]','Pilot Address','pending',?,'accepted',?,'SUBMITTED','LIVE',?)
            """,
            (patient_id, patient_id, pharmacy_id, old, recent, recent),
        )
        db.execute(
            """
            INSERT INTO consultation_requests
            (patient_id,doctor_id,consultation_type,status,reason,created_at,updated_at)
            VALUES (?,?,'chat','rejected','Pilot reason',?,?)
            """,
            (patient_id, doctor_id, old, recent),
        )
        db.execute(
            """
            INSERT INTO inventory_observations
            (pharmacy_id,sku_id,stock_status,quantity_available,price_inr,price_available,
             discount_percent,source,observed_at,data_mode,created_at,updated_at)
            VALUES (?,1,'CONFIRMED',4,10,1,0,'pharmacy_manual',?,'LIVE',?,?)
            """,
            (pharmacy_id, old, old, old),
        )
        db.execute(
            """
            INSERT INTO diagnostic_offers
            (lab_id,test_id,price_inr,home_collection_available,home_collection_fee_inr,
             verified,data_mode,observed_at,created_at)
            VALUES (?,1,100,1,0,1,'LIVE',?,?)
            """,
            (doctor_id, old, old),
        )

        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        today = datetime.now(timezone.utc).isoformat()
        for correlation_id, stamp in (("pilot-yesterday", yesterday), ("pilot-today", today)):
            db.execute(
                """
                INSERT INTO request_observations
                (correlation_id,actor_id,actor_role,method,route_pattern,status_code,duration_ms,error_class,created_at)
                VALUES (?,?,'patient','GET','/api/v1/dashboard',200,25,NULL,?)
                """,
                (correlation_id, patient_id, stamp),
            )
        db.commit()

        payload = pilot_scorecard()
        assert payload["provider_responsiveness"]["medicine_orders"]["provider_responded"] >= 1
        assert payload["provider_responsiveness"]["consultations"]["provider_responded"] >= 1
        assert payload["data_freshness"]["pharmacy_inventory"]["needs_refresh"] >= 1
        assert payload["data_freshness"]["diagnostic_offers"]["needs_refresh"] >= 1
        assert payload["engagement"]["repeat_activity_users_30d"] >= 1
        assert payload["reliability"]["window_minutes"] == 60
        assert "cohort-retention claim" in payload["measurement_boundary"]


def test_pilot_scorecard_does_not_fake_missing_response_or_retention_metrics(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        payload = pilot_scorecard()

    assert payload["provider_responsiveness"]["medicine_orders"]["average_response_minutes"] is None
    assert payload["provider_responsiveness"]["medicine_orders"]["median_response_minutes"] is None
    assert payload["provider_responsiveness"]["consultations"]["average_response_minutes"] is None
    assert payload["engagement"]["repeat_activity_rate_percent"] is None

def test_pilot_signals_use_no_data_instead_of_fake_targets(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        payload = pilot_scorecard()

    signals = {item["key"]: item for item in payload["signals"]}
    assert signals["pharmacy_freshness"]["status"] == "NO_DATA"
    assert signals["diagnostic_freshness"]["status"] == "NO_DATA"
    assert signals["pharmacy_response"]["status"] == "NO_DATA"
    assert signals["consultation_response"]["status"] == "NO_DATA"
    assert signals["repeat_activity"]["status"] == "NO_DATA"


def test_pilot_signals_flag_stale_provider_data(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        db = get_db()
        pharmacy_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?, 'pharmacy',1,?,?)",
            ("Signal Pharmacy", "signal-pharmacy@example.com", "signal-pharmacy@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        lab_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?, 'hospital',1,?,?)",
            ("Signal Lab", "signal-lab@example.com", "signal-lab@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        db.execute(
            """
            INSERT INTO inventory_observations
            (pharmacy_id,sku_id,stock_status,quantity_available,price_inr,price_available,
             discount_percent,source,observed_at,data_mode,created_at,updated_at)
            VALUES (?,1,'CONFIRMED',3,10,1,0,'pharmacy_manual',?,'LIVE',?,?)
            """,
            (pharmacy_id, old, old, old),
        )
        db.execute(
            """
            INSERT INTO diagnostic_offers
            (lab_id,test_id,price_inr,home_collection_available,home_collection_fee_inr,
             verified,data_mode,observed_at,created_at)
            VALUES (?,1,100,1,0,1,'LIVE',?,?)
            """,
            (lab_id, old, old),
        )
        db.commit()

        payload = pilot_scorecard()
        signals = {item["key"]: item for item in payload["signals"]}
        assert signals["pharmacy_freshness"]["status"] == "ATTENTION"
        assert signals["diagnostic_freshness"]["status"] == "ATTENTION"

