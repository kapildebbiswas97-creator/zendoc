"""
Clinician Intelligence & Provider OS Test Suite.
Verifies pre-consultation intelligence briefing, longitudinal patient snapshot,
SOAP clinical notes drafting, human-in-the-loop review guarantee,
and post-consultation workflow automation.
"""
import pytest
from tests.test_milestone1 import api_token, make_client
from zendoc.db import get_db, now_iso
from zendoc.clinician_intelligence import (
    build_pre_consultation_briefing,
    finalize_clinical_consultation,
)


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_pre_consultation_briefing_assembly(tmp_path):
    app, client = make_client(tmp_path)
    with app.app_context():
        db = get_db()
        p_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) "
            "VALUES ('Patient Sneha', 'sneha@example.com', 'sneha@example.com', 'hash', 'patient', 1, ?, ?)",
            (now_iso(), now_iso()),
        ).lastrowid
        d_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) "
            "VALUES ('Dr. Subhash', 'subhash@example.com', 'subhash@example.com', 'hash', 'doctor', 1, ?, ?)",
            (now_iso(), now_iso()),
        ).lastrowid

        # Profile
        db.execute(
            "INSERT INTO patient_health_profiles (patient_id, blood_group, allergies, chronic_conditions, created_at, updated_at) "
            "VALUES (?, 'B+', '[\"Penicillin\"]', '[\"Hypertension\"]', ?, ?)",
            (p_id, now_iso(), now_iso()),
        )
        # Appointment
        appt_id = db.execute(
            "INSERT INTO appointments (patient_id, provider_id, provider_name, scheduled_for, reason, status, created_at, updated_at) "
            "VALUES (?, ?, 'Dr. Subhash', '2026-10-10T10:00:00Z', 'Quarterly hypertension checkup', 'confirmed', ?, ?)",
            (p_id, d_id, now_iso(), now_iso()),
        ).lastrowid
        db.commit()

        doctor_actor = {"id": d_id, "name": "Dr. Subhash", "role": "doctor"}
        briefing = build_pre_consultation_briefing(doctor_actor, p_id, appointment_id=appt_id)

        assert briefing["patient"]["name"] == "Patient Sneha"
        assert briefing["chief_complaint"] == "Quarterly hypertension checkup"
        assert "Penicillin" in briefing["longitudinal_snapshot"]["declared_allergies"]
        assert "Hypertension" in briefing["longitudinal_snapshot"]["chronic_conditions"]

        soap = briefing["draft_soap_note"]
        assert soap["status"] == "DRAFT_REQUIRES_CLINICIAN_REVIEW"
        assert "Subjective" in soap["subjective"] or "presents" in soap["subjective"]
        assert "Objective" in soap["objective"] or "vitals" in soap["objective"]
        assert "human_in_the_loop_guarantee" in soap
        assert "NOT finalized" in soap["human_in_the_loop_guarantee"]
        assert "ZENDOC does not independently diagnose" in briefing["disclaimer"]


def test_clinician_consultation_finalization_and_automation(tmp_path):
    app, client = make_client(tmp_path)
    with app.app_context():
        db = get_db()
        p_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) "
            "VALUES ('Patient Amit', 'amit@example.com', 'amit@example.com', 'hash', 'patient', 1, ?, ?)",
            (now_iso(), now_iso()),
        ).lastrowid
        d_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) "
            "VALUES ('Dr. Clinician', 'doc2@example.com', 'doc2@example.com', 'hash', 'doctor', 1, ?, ?)",
            (now_iso(), now_iso()),
        ).lastrowid
        appt_id = db.execute(
            "INSERT INTO appointments (patient_id, provider_id, provider_name, scheduled_for, reason, status, created_at, updated_at) "
            "VALUES (?, ?, 'Dr. Clinician', '2026-10-12T11:00:00Z', 'Routine follow-up', 'confirmed', ?, ?)",
            (p_id, d_id, now_iso(), now_iso()),
        ).lastrowid
        db.commit()

        doctor_actor = {"id": d_id, "name": "Dr. Clinician", "role": "doctor"}
        outcome = finalize_clinical_consultation(
            doctor_actor,
            appt_id,
            {
                "subjective": "Patient reports well-managed blood pressure.",
                "objective": "Sitting BP 124/80 mmHg, HR 72 bpm regular.",
                "assessment": "Essential hypertension, well-controlled on current regimen.",
                "plan": "Continue Telmisartan 40mg daily. Repeat serum creatinine and electrolytes in 6 months.",
                "patient_instructions": "Maintain low-sodium diet and exercise 30 minutes daily.",
                "follow_up_days": 180,
            },
        )

        assert outcome["status"] == "completed"
        assert outcome["appointment_id"] == appt_id
        assert outcome["post_consultation_automation"]["timeline_recorded"] is True
        assert outcome["post_consultation_automation"]["appointment_status"] == "completed"

        # Check appointment status in DB
        appt_row = db.execute("SELECT status FROM appointments WHERE id=?", (appt_id,)).fetchone()
        assert appt_row["status"] == "completed"

        # Check consultation event in timeline
        timeline_ev = db.execute(
            "SELECT * FROM health_timeline_events WHERE patient_id=? AND event_type='consultation'",
            (p_id,),
        ).fetchone()
        assert timeline_ev is not None
        assert timeline_ev["source"] == "PROVIDER_RECORDED"
        assert "Essential hypertension" in timeline_ev["summary"]


def test_provider_os_api_routes(tmp_path):
    app, client = make_client(tmp_path)
    doc_token = api_token(client, "doctor-os@example.com", role="doctor")
    pat_token = api_token(client, "patient-os@example.com", role="patient")

    with app.app_context():
        p_id = get_db().execute("SELECT id FROM users WHERE email='patient-os@example.com'").fetchone()["id"]
        d_id = get_db().execute("SELECT id FROM users WHERE email='doctor-os@example.com'").fetchone()["id"]
        appt_id = get_db().execute(
            "INSERT INTO appointments (patient_id, provider_id, provider_name, scheduled_for, reason, status, created_at, updated_at) "
            "VALUES (?, ?, 'Dr. OS', '2026-10-15T09:00:00Z', 'Migraine review', 'confirmed', ?, ?)",
            (p_id, d_id, now_iso(), now_iso()),
        ).lastrowid
        get_db().commit()

    # Patient cannot access briefing
    forbidden_resp = client.get(f"/api/v1/provider/patient/{p_id}/briefing", headers=headers(pat_token))
    assert forbidden_resp.status_code == 403

    # Doctor accesses briefing
    briefing_resp = client.get(f"/api/v1/provider/patient/{p_id}/briefing?appointment_id={appt_id}", headers=headers(doc_token))
    assert briefing_resp.status_code == 200
    assert "draft_soap_note" in briefing_resp.json["briefing"]

    # Doctor finalizes consultation
    finalize_resp = client.post(
        f"/api/v1/provider/consultation/{appt_id}/finalize",
        json={
            "assessment": "Tension-type headache responding to rest.",
            "plan": "Hydration, sleep hygiene, PRN Paracetamol 500mg.",
        },
        headers=headers(doc_token),
    )
    assert finalize_resp.status_code == 200
    assert finalize_resp.json["status"] == "completed"
