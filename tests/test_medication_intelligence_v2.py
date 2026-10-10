"""
Medication & Prescription Intelligence v2 Test Suite.
Verifies duplicate therapy checks, drug-drug interaction alerts,
allergy contraindications, condition contraindications, medication reconciliation,
and absolute preservation of the non-autonomous prescribing boundary.
"""
import pytest
from zendoc.prescription_intelligence import (
    AUTONOMOUS_PRESCRIBING_MUST_REMAIN_DISABLED,
    check_medication_safety,
    reconcile_prescriptions,
    prescription_intelligence_state,
)
from zendoc.prescription_service import create_prescription
from tests.test_milestone10_connected_care import make_m10_app
from zendoc.db import get_db, now_iso


def test_autonomous_prescribing_boundary():
    assert AUTONOMOUS_PRESCRIBING_MUST_REMAIN_DISABLED is True


def test_duplicate_therapy_detection():
    # Prescribing two NSAIDs together
    items = [
        {"medicine_name": "Ibuprofen 400 mg"},
        {"medicine_name": "Diclofenac 50 mg"},
    ]
    result = check_medication_safety(items)
    assert result["safe"] is True  # Moderate severity does not block safety flag, but records alert
    assert len(result["duplicate_therapies"]) == 1
    dup = result["duplicate_therapies"][0]
    assert dup["class_name"] == "nsaid"
    assert "Ibuprofen" in dup["medications"][0]
    assert "Diclofenac" in dup["medications"][1]


def test_drug_drug_interaction_detection():
    # Warfarin + Aspirin (Critical bleeding risk)
    items = [
        {"medicine_name": "Warfarin 5 mg"},
        {"medicine_name": "Aspirin 75 mg"},
    ]
    result = check_medication_safety(items)
    assert result["safe"] is False
    assert result["critical_alerts_count"] >= 1
    assert len(result["interactions"]) == 1
    ddi = result["interactions"][0]
    assert ddi["severity"] == "CRITICAL"
    assert "Bleeding" in ddi["title"]


def test_allergy_contraindication_detection():
    # Penicillin allergy + Amoxicillin
    items = [{"medicine_name": "Amoxicillin 500 mg"}]
    allergies = ["Penicillin"]
    result = check_medication_safety(items, patient_allergies=allergies)
    assert result["safe"] is False
    assert result["critical_alerts_count"] >= 1
    assert len(result["allergy_alerts"]) == 1
    al = result["allergy_alerts"][0]
    assert al["allergy_family"] == "penicillin"
    assert al["severity"] == "CRITICAL"


def test_condition_contraindication_detection():
    # Asthma + Propranolol
    items = [{"medicine_name": "Propranolol 40 mg"}]
    conditions = ["asthma"]
    result = check_medication_safety(items, patient_conditions=conditions)
    assert result["safe"] is False
    assert result["high_alerts_count"] >= 1
    assert len(result["condition_alerts"]) == 1
    cd = result["condition_alerts"][0]
    assert cd["condition"] == "asthma"
    assert cd["severity"] == "HIGH"


def test_medication_reconciliation():
    current = [
        {"medicine_name": "Metformin 500 mg", "dosage": "500 mg BID"},
        {"medicine_name": "Telmisartan 40 mg", "dosage": "40 mg QD"},
    ]
    historical = [
        {"medicine_name": "Metformin 500 mg", "dosage": "500 mg QD"},
        {"medicine_name": "Amlodipine 5 mg", "dosage": "5 mg QD"},
    ]
    recon = reconcile_prescriptions(current, historical)
    assert recon["status"] == "RECONCILED"
    assert len(recon["continued_medications"]) == 1
    assert recon["continued_medications"][0]["status"] == "CONTINUED"
    assert len(recon["new_medications"]) == 1
    assert recon["new_medications"][0]["medicine_name"] == "Telmisartan 40 mg"
    assert len(recon["unmentioned_prior_medications"]) == 1
    assert recon["unmentioned_prior_medications"][0]["medicine_name"] == "Amlodipine 5 mg"


def test_prescription_state_includes_safety_analysis(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?, 'patient',1,?,?)",
            ("Safety Patient", "safety@example.com", "safety@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.commit()

        # Create prescription with single safe medicine
        rx = create_prescription(
            patient_id=patient_id,
            prescriber_name="Dr Safety",
            items=[{"medicine_name": "Paracetamol 500 mg", "sku_id": 1, "extraction_confidence": 0.95}],
        )
        state = prescription_intelligence_state(rx["id"], actor={"id": patient_id, "role": "patient"})
        assert "safety_analysis" in state
        assert state["safety_analysis"]["safe"] is True
        assert state["safety"]["autonomous_prescribing"] is False
