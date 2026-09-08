import pytest

from zendoc.care_journey_store import (
    advance_persisted_journey,
    create_persisted_journey,
    get_persisted_journey,
)
from zendoc.db import get_db, now_iso
from tests.test_milestone10_connected_care import make_m10_app


def test_persisted_care_journey_records_history(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?, 'patient',1,?,?)",
            ("Journey User", "journey@example.com", "journey@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.commit()
        actor = {"id": patient_id, "role": "patient"}
        created = create_persisted_journey(actor, provenance={"source": "unit_test"})
        assert created["state"] == "NEW"

        updated = advance_persisted_journey(
            actor,
            created["id"],
            target_state="CONTEXT_READY",
            reason="Self context authorized",
            provenance={"consent": "self"},
        )
        assert updated["state"] == "CONTEXT_READY"
        assert len(updated["history"]) == 1
        assert updated["history"][0]["previous_state"] == "NEW"
        assert updated["provenance"]["consent"] == "self"


def test_persisted_journey_blocks_cross_patient_access(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        p1 = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?, 'patient',1,?,?)",
            ("P1", "p1journey@example.com", "p1journey@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        p2 = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?, 'patient',1,?,?)",
            ("P2", "p2journey@example.com", "p2journey@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.commit()
        journey = create_persisted_journey({"id": p1, "role": "patient"})
        with pytest.raises(PermissionError):
            get_persisted_journey(journey["id"], {"id": p2, "role": "patient"})


def test_care_journey_api_requires_auth(tmp_path):
    app = make_m10_app(tmp_path)
    client = app.test_client()
    response = client.post("/api/v1/care-journeys", json={})
    assert response.status_code == 401
