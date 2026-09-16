from datetime import datetime, timedelta, timezone

import pytest

from tests.test_milestone1 import login_web, make_app
from zendoc.db import get_db
from zendoc.edgecare_demo_data import (
    DEMO_DOCTOR_EMAIL,
    DEMO_ORGANIZATION,
    DEMO_PATIENT_EMAIL,
    seed_edgecare_demo_data,
)


DEMO_PASSWORD = "LocalDemoPass123!"


def test_demo_fixture_refuses_production_before_writing(monkeypatch):
    monkeypatch.setenv("ZENDOC_ENV", "production")
    with pytest.raises(RuntimeError, match="disabled in production"):
        seed_edgecare_demo_data(password=DEMO_PASSWORD)


def test_demo_fixture_requires_local_password(tmp_path, monkeypatch):
    monkeypatch.delenv("ZENDOC_ENV", raising=False)
    monkeypatch.delenv("ZENDOC_DEMO_PASSWORD", raising=False)
    app = make_app(tmp_path)
    with pytest.raises(ValueError, match="at least 12 characters"):
        seed_edgecare_demo_data(password="short", app=app)


def test_demo_fixture_is_idempotent_and_visibly_synthetic(tmp_path, monkeypatch):
    monkeypatch.delenv("ZENDOC_ENV", raising=False)
    app = make_app(tmp_path)

    first = seed_edgecare_demo_data(password=DEMO_PASSWORD, app=app)
    second = seed_edgecare_demo_data(password=DEMO_PASSWORD, app=app)

    assert first["synthetic_demo_only"] is True
    assert first["provider_profile_id"] == second["provider_profile_id"]

    with app.app_context():
        db = get_db()
        users = db.execute(
            "SELECT email,name,role FROM users WHERE email IN (?,?) ORDER BY email",
            (DEMO_DOCTOR_EMAIL, DEMO_PATIENT_EMAIL),
        ).fetchall()
        assert len(users) == 2
        assert all("DEMO ONLY" in row["name"] for row in users)

        profile = db.execute(
            "SELECT * FROM provider_profiles WHERE id=?",
            (first["provider_profile_id"],),
        ).fetchone()
        assert profile is not None
        assert profile["organization"] == DEMO_ORGANIZATION
        assert profile["verification_status"] == "verified"
        assert "not a real clinician" in profile["qualifications"]
        assert profile["license_identifier"] == "DEMO-NOT-A-LICENSE"

        schedules = db.execute(
            "SELECT weekday,start_time,end_time,slot_minutes FROM provider_schedules WHERE provider_profile_id=? ORDER BY weekday",
            (first["provider_profile_id"],),
        ).fetchall()
        assert len(schedules) == 7
        assert [row["weekday"] for row in schedules] == list(range(7))
        assert all(row["start_time"] == "09:00" and row["end_time"] == "17:00" for row in schedules)


def test_seeded_demo_patient_can_search_provider_and_see_future_slots(tmp_path, monkeypatch):
    monkeypatch.delenv("ZENDOC_ENV", raising=False)
    monkeypatch.setenv("ZENDOC_PLACES_PROVIDER", "none")
    app = make_app(tmp_path)
    result = seed_edgecare_demo_data(password=DEMO_PASSWORD, app=app)
    client = app.test_client()

    login = login_web(client, "patient", DEMO_PATIENT_EMAIL, DEMO_PASSWORD)
    assert login.status_code == 200

    search = client.get("/universal-search?q=Kalyani&category=all")
    assert search.status_code == 200
    assert b"DEMO ONLY" in search.data
    assert b"Cardiology" in search.data
    assert f'/providers/{result["provider_profile_id"]}'.encode() in search.data

    future_date = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    detail = client.get(f'/providers/{result["provider_profile_id"]}?date={future_date}')
    assert detail.status_code == 200
    assert b"Synthetic competition fixture" in detail.data
    assert b"Request appointment" in detail.data
