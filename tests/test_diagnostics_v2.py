from datetime import datetime, timedelta, timezone

import pytest

from zendoc.db import get_db, now_iso
from zendoc.diagnostic_service import (
    AVAILABILITY_CONFIRMED,
    AVAILABILITY_STALE,
    AVAILABILITY_UNKNOWN,
    book_diagnostic_test,
    diagnostic_availability_state,
    normalize_diagnostic_test,
    search_lab_offers,
)
from tests.test_milestone10_connected_care import make_m10_app


def test_diagnostic_availability_truth_states():
    now = datetime.now(timezone.utc)
    assert diagnostic_availability_state({}) == AVAILABILITY_UNKNOWN
    assert diagnostic_availability_state({"verified": 1}) == AVAILABILITY_UNKNOWN

    fresh = {
        "verified": 1,
        "observed_at": (now - timedelta(hours=1)).isoformat(),
    }
    stale = {
        "verified": 1,
        "observed_at": (now - timedelta(hours=48)).isoformat(),
    }
    assert diagnostic_availability_state(fresh, now=now) == AVAILABILITY_CONFIRMED
    assert diagnostic_availability_state(stale, now=now) == AVAILABILITY_STALE


def test_diagnostic_alias_resolution(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        db.execute(
            "UPDATE diagnostic_catalog SET aliases_json=? WHERE code='CBC'",
            ('["complete blood count", "full blood count"]',),
        )
        db.commit()
        item = normalize_diagnostic_test("full blood count")
        assert item is not None
        assert item["code"] == "CBC"


def test_search_marks_stale_offer_without_promoting_it(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        lab_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?, 'hospital',1,?,?)",
            ("Old Lab", "oldlab@example.com", "oldlab@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.execute(
            "INSERT INTO provider_profiles (user_id,organization,provider_type,city,verification_status,created_at,updated_at) VALUES (?,?,'lab','Kolkata','verified',?,?)",
            (lab_id, "Old Lab", now_iso(), now_iso()),
        )
        old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        db.execute(
            "INSERT INTO diagnostic_offers (lab_id,test_id,price_inr,home_collection_available,home_collection_fee_inr,verified,data_mode,observed_at,created_at) VALUES (?,1,500,1,0,1,'LIVE',?,?)",
            (lab_id, old, old),
        )
        db.commit()

        offers = search_lab_offers("CBC", city="Kolkata")
        assert len(offers) == 1
        assert offers[0]["availability_state"] == AVAILABILITY_STALE
        assert offers[0]["availability_confirmed"] is False


def test_stale_diagnostic_offer_cannot_be_booked(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?, 'patient',1,?,?)",
            ("Patient", "diagpatient@example.com", "diagpatient@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        lab_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?, 'hospital',1,?,?)",
            ("Stale Lab", "stalelab@example.com", "stalelab@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.execute(
            "INSERT INTO provider_profiles (user_id,organization,provider_type,city,verification_status,created_at,updated_at) VALUES (?,?,'lab','Kolkata','verified',?,?)",
            (lab_id, "Stale Lab", now_iso(), now_iso()),
        )
        old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        db.execute(
            "INSERT INTO diagnostic_offers (lab_id,test_id,price_inr,home_collection_available,home_collection_fee_inr,verified,data_mode,observed_at,created_at) VALUES (?,1,500,1,0,1,'LIVE',?,?)",
            (lab_id, old, old),
        )
        db.commit()

        with pytest.raises(ValueError) as exc:
            book_diagnostic_test(
                actor={"id": patient_id, "role": "patient"},
                patient_id=patient_id,
                test_id=1,
                lab_id=lab_id,
                scheduled_date="2026-09-20",
                address="Kolkata address",
                collection_type="home_collection",
                user_confirmed=True,
            )
        assert "stale" in str(exc.value).lower()
