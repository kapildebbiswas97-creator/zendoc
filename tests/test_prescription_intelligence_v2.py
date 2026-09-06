import pytest

from zendoc.db import get_db, now_iso
from zendoc.prescription_intelligence import (
    FULFILMENT_READY,
    REVIEW_REQUIRED,
    prescription_intelligence_state,
)
from zendoc.prescription_service import create_prescription
from tests.test_milestone10_connected_care import make_m10_app


def test_prescription_intelligence_low_confidence_requires_review(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?, 'patient',1,?,?)",
            ("Rx Review", "rxreview@example.com", "rxreview@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.commit()
        rx = create_prescription(
            patient_id=patient_id,
            prescriber_name="Dr Review",
            items=[{"medicine_name": "Unknown Medicine 10mg", "extraction_confidence": 0.60}],
        )
        state = prescription_intelligence_state(rx["id"], actor={"id": patient_id, "role": "patient"})
        assert state["overall_stage"] == REVIEW_REQUIRED
        assert state["needs_review"] is True
        assert state["fulfilment_ready"] is False
        assert state["items"][0]["stage"] in {"LOW_CONFIDENCE", "REVIEW_REQUIRED", "AMBIGUOUS"}


def test_exact_verified_prescription_becomes_fulfilment_ready(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?, 'patient',1,?,?)",
            ("Rx Ready", "rxready@example.com", "rxready@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.commit()
        rx = create_prescription(
            patient_id=patient_id,
            prescriber_name="Dr Exact",
            items=[{"medicine_name": "Metformin 500 mg", "sku_id": 2, "extraction_confidence": 0.99}],
        )
        state = prescription_intelligence_state(rx["id"], actor={"id": patient_id, "role": "patient"})
        assert state["overall_stage"] == FULFILMENT_READY
        assert state["fulfilment_ready"] is True
        assert all(value is False for value in state["safety"].values())
