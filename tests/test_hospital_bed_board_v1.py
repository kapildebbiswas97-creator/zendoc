"""Hospital ward/bed board API authorization, privacy, transitions and audit tests."""
from __future__ import annotations

from zendoc.db import get_db, now_iso
from tests.test_milestone1 import make_app


def _register(client, email, role):
    result = client.post("/api/v1/auth/register", json={
        "name": email, "email": email, "password": "StrongPass123",
        "role": role, "accept_privacy": True, "accept_terms": True,
    })
    assert result.status_code == 201, result.get_json()
    login = client.post("/api/v1/auth/login", json={
        "email": email, "password": "StrongPass123",
    })
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.get_json()['token']}"}


def _verified_hospital(app, email):
    with app.app_context():
        db = get_db()
        user_id = db.execute(
            "SELECT id FROM users WHERE email_normalized=?", (email,)
        ).fetchone()["id"]
        stamp = now_iso()
        db.execute(
            """INSERT INTO provider_profiles
               (user_id,provider_type,organization,verification_status,created_at,updated_at)
               VALUES (?,'hospital',?,'verified',?,?)""",
            (user_id, "Independent Hospital", stamp, stamp),
        )
        db.commit()


def _create(client, token, *, ward="General", code="A-1"):
    return client.post("/api/v1/hospital/beds", json={
        "ward_name": ward, "bed_code": code,
    }, headers=token)


def _state(client, token, bed_id, version, state, reason="Manual ward count"):
    return client.post(f"/api/v1/hospital/beds/{bed_id}/state", json={
        "expected_version": version, "state": state, "reason": reason,
    }, headers=token)


def test_unauthed_patient_doctor_and_pending_hospital_cannot_access_board(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    assert client.get("/api/v1/hospital/beds").status_code == 401
    for role in ("patient", "doctor", "hospital"):
        token = _register(client, f"{role}@example.com", role)
        assert client.get("/api/v1/hospital/beds", headers=token).status_code == 403
        assert _create(client, token).status_code == 403


def test_private_board_create_list_duplicate_and_no_patient_data(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    hospital = _register(client, "ward-a@example.com", "hospital")
    _verified_hospital(app, "ward-a@example.com")
    created = _create(client, hospital)
    assert created.status_code == 201, created.get_json()
    bed = created.get_json()["bed"]
    assert bed["occupancy_state"] == "available"
    assert bed["version"] == 0
    assert "patient" not in str(bed).lower()
    listed = client.get("/api/v1/hospital/beds", headers=hospital)
    assert listed.status_code == 200
    payload = listed.get_json()
    assert payload["status"] == "OPERATOR_ATTESTED_ONLY"
    assert payload["live_public_availability_verified"] is False
    assert payload["counts"]["available"] == 1
    assert len(payload["beds"]) == 1
    assert _create(client, hospital).status_code == 400
    assert client.post("/api/v1/hospital/beds", headers=hospital, json={
        "ward_name": "General", "bed_code": "A-2", "patient_id": 999,
    }).status_code == 400


def test_ward_transitions_are_audited_and_optimistic_versioned(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    hospital = _register(client, "bed-ops@example.com", "hospital")
    _verified_hospital(app, "bed-ops@example.com")
    bed_id = _create(client, hospital).get_json()["bed"]["id"]
    occupied = _state(client, hospital, bed_id, 0, "occupied")
    assert occupied.status_code == 200
    assert occupied.get_json()["bed"]["version"] == 1
    assert _state(client, hospital, bed_id, 0, "maintenance").status_code == 409
    assert _state(client, hospital, bed_id, 1, "available").status_code == 400
    cleaned = _state(client, hospital, bed_id, 1, "cleaning")
    assert cleaned.status_code == 200
    freed = _state(client, hospital, bed_id, 2, "available")
    assert freed.status_code == 200
    assert freed.get_json()["bed"]["version"] == 3
    history = client.get(f"/api/v1/hospital/beds/{bed_id}/history", headers=hospital)
    assert history.status_code == 200
    h = history.get_json()["history"]
    assert len(h) == 3
    assert [event["next_state"] for event in h] == ["available", "cleaning", "occupied"]
    with app.app_context():
        total = get_db().execute(
            "SELECT COUNT(*) AS n FROM hospital_bed_events WHERE bed_id=?", (bed_id,),
        ).fetchone()["n"]
        assert total == 3


def test_strict_tenant_isolation_and_hospital_revocation(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    a = _register(client, "tenant-one-hospital@example.com", "hospital")
    b = _register(client, "tenant-two-hospital@example.com", "hospital")
    _verified_hospital(app, "tenant-one-hospital@example.com")
    _verified_hospital(app, "tenant-two-hospital@example.com")
    bed_id = _create(client, a, ward="ICU", code="I-1").get_json()["bed"]["id"]
    assert client.get("/api/v1/hospital/beds", headers=b).get_json()["beds"] == []
    assert _state(client, b, bed_id, 0, "occupied").status_code == 404
    assert client.get(f"/api/v1/hospital/beds/{bed_id}/history", headers=b).status_code == 404
    with app.app_context():
        db = get_db()
        db.execute("""UPDATE provider_profiles SET verification_status='suspended'
                      WHERE user_id=(SELECT id FROM users WHERE email_normalized=?)""",
                   ("tenant-one-hospital@example.com",))
        db.commit()
    assert client.get("/api/v1/hospital/beds", headers=a).status_code == 403
    assert _state(client, a, bed_id, 0, "occupied").status_code == 403


def test_invalid_fields_or_explicit_patient_notes_are_rejected(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    token = _register(client, "inputs-hospital@example.com", "hospital")
    _verified_hospital(app, "inputs-hospital@example.com")
    assert _create(client, token, ward="../outside").status_code == 400
    assert _create(client, token, code=" " * 3).status_code == 400
    created = _create(client, token)
    bed_id = created.get_json()["bed"]["id"]
    assert _state(client, token, bed_id, 0, "occupied", "  ").status_code == 400
    assert client.post(f"/api/v1/hospital/beds/{bed_id}/state", headers=token, json={
        "state": "occupied", "reason": "Manual ward count",
        "expected_version": 0, "patient_name": "Sensitive",
    }).status_code == 400
    assert client.post(f"/api/v1/hospital/beds/{bed_id}/state", headers=token, json={
        "state": "occupied", "reason": "Manual ward count",
        "expected_version": True,
    }).status_code == 400
