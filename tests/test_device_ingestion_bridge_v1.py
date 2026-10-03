from zendoc.device_ingestion import (
    ingest_device_measurement,
    issue_device_ingestion_key,
    revoke_device_ingestion_keys,
)
from zendoc.db import get_db
from zendoc.iot_hub import connect_device
from zendoc.security import hash_token
from tests.test_milestone1 import make_app


def _patient(db):
    return db.execute(
        "SELECT * FROM users WHERE role='patient' ORDER BY id LIMIT 1"
    ).fetchone()


def test_device_ingestion_key_is_hashed_scoped_and_idempotent(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient = _patient(db)
        device = connect_device(patient, {
            "device_name": "Test Watch",
            "device_type": "smartwatch",
            "manufacturer": "Test",
            "model": "T1",
            "device_identifier": "test-watch-001",
        })
        issued = issue_device_ingestion_key(patient, device["id"])
        assert issued["ingestion_key"].startswith("zd_dev_")

        stored = db.execute(
            "SELECT key_hash FROM device_ingestion_keys WHERE id=?",
            (issued["key_id"],),
        ).fetchone()
        assert stored["key_hash"] == hash_token(issued["ingestion_key"])
        assert stored["key_hash"] != issued["ingestion_key"]

        payload = {
            "event_id": "evt-1",
            "metric_type": "heart_rate",
            "value": 72,
            "unit": "bpm",
            "recorded_at": "2026-10-03T09:00:00+00:00",
        }
        first = ingest_device_measurement(issued["ingestion_key"], payload)
        second = ingest_device_measurement(issued["ingestion_key"], payload)

        assert first["duplicate"] is False
        assert second["duplicate"] is True
        assert first["metric_id"] == second["metric_id"]
        metric = db.execute(
            "SELECT * FROM health_metrics WHERE id=?",
            (first["metric_id"],),
        ).fetchone()
        assert metric["user_id"] == patient["id"]
        assert metric["source"] == "device"
        assert metric["metric_type"] == "heart_rate"


def test_device_key_cannot_write_another_patients_data(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patients = db.execute(
            "SELECT * FROM users WHERE role='patient' ORDER BY id LIMIT 2"
        ).fetchall()
        if len(patients) < 2:
            now = "2026-10-03T00:00:00+00:00"
            user_id = db.execute(
                """
                INSERT INTO users
                (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
                VALUES ('Other','other-device@example.com','other-device@example.com','x','patient',1,?,?)
                """,
                (now, now),
            ).lastrowid
            db.commit()
            patients = [
                patients[0],
                db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone(),
            ]

        owner = patients[0]
        other = patients[1]
        device = connect_device(owner, {
            "device_name": "Owner Device",
            "device_type": "fitness_band",
            "device_identifier": "owner-device-001",
        })
        issued = issue_device_ingestion_key(owner, device["id"])

        result = ingest_device_measurement(issued["ingestion_key"], {
            "event_id": "owner-only",
            "metric_type": "steps",
            "value": 1234,
            "unit": "steps",
            "patient_id": other["id"],
            "device_id": 999999,
        })

        metric = db.execute(
            "SELECT * FROM health_metrics WHERE id=?",
            (result["metric_id"],),
        ).fetchone()
        assert metric["user_id"] == owner["id"]
        assert metric["user_id"] != other["id"]


def test_rotating_or_revoking_device_key_fails_closed(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient = _patient(db)
        device = connect_device(patient, {
            "device_name": "Rotate Device",
            "device_type": "smartwatch",
            "device_identifier": "rotate-device-001",
        })
        first = issue_device_ingestion_key(patient, device["id"])
        second = issue_device_ingestion_key(patient, device["id"])

        failed = False
        try:
            ingest_device_measurement(first["ingestion_key"], {
                "event_id": "old-key",
                "metric_type": "steps",
                "value": 10,
            })
        except PermissionError:
            failed = True
        assert failed is True

        revoke_device_ingestion_keys(patient, device["id"])
        failed = False
        try:
            ingest_device_measurement(second["ingestion_key"], {
                "event_id": "revoked-key",
                "metric_type": "steps",
                "value": 10,
            })
        except PermissionError:
            failed = True
        assert failed is True
