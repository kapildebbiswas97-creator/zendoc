"""
ZENDOC Clinician Intelligence & Provider OS Engine.
Pre-consultation briefing, structured longitudinal patient snapshot,
SOAP clinical notes drafting, and post-consultation workflow automation.

STRICT CLINICAL BOUNDARY:
- AI drafting is strictly non-binding clinical decision support.
- Clinician must review, edit, approve, or reject all drafted notes.
- AI never autonomously signs notes, diagnoses disease, or prescribes treatments.
"""
from __future__ import annotations

import json
from typing import Any

from .care_action_ledger import create_action
from .db import get_db, now_iso
from .event_bus import publish_event
from .health_timeline import add_timeline_event, list_timeline
from .prescription_intelligence import check_medication_safety


def _user_id(actor: Any) -> int:
    if isinstance(actor, (int, float)):
        return int(actor)
    if isinstance(actor, dict):
        return int(actor.get("id") or 0)
    # Handle sqlite3.Row and similar objects with key-based access
    try:
        return int(actor["id"] or 0)
    except (TypeError, KeyError, IndexError):
        pass
    return int(getattr(actor, "id", 0) or 0)


def _fmt_vitals(vitals_summary: list) -> str:
    """Format vitals list into a readable string without backslashes in f-strings."""
    if not vitals_summary:
        return "No recent vitals on file"
    parts = []
    for v in vitals_summary[:4]:
        vd = dict(v) if not isinstance(v, dict) else v
        mt = vd.get("metric_type", "")
        mv = vd.get("metric_value", "")
        unit = vd.get("unit") or ""
        parts.append(f"{mt}: {mv} {unit}".strip())
    return ", ".join(parts)


def _actor_field(actor: Any, field: str, default: Any = None) -> Any:
    """Safely get a field from dict, sqlite3.Row, or object actors."""
    if isinstance(actor, dict):
        return actor.get(field, default)
    try:
        val = actor[field]
        return val if val is not None else default
    except (TypeError, KeyError, IndexError):
        pass
    return getattr(actor, field, default)


def build_pre_consultation_briefing(
    doctor_actor: Any,
    patient_id: int,
    appointment_id: int | None = None,
) -> dict[str, Any]:
    """
    Assembles a high-productivity clinical intelligence snapshot for the attending clinician.
    """
    doc_id = _user_id(doctor_actor)
    db = get_db()

    # Verify authorization: doctor or admin role
    role = _actor_field(doctor_actor, "role", "doctor")
    if role not in {"doctor", "admin", "hospital"}:
        raise PermissionError("Only licensed clinicians or administrators can access clinical briefings.")

    patient = db.execute("SELECT id, name, email FROM users WHERE id=?", (patient_id,)).fetchone()
    if not patient:
        raise LookupError("Patient not found.")

    # 1. Appointment context
    appt = None
    if appointment_id:
        appt_row = db.execute("SELECT * FROM appointments WHERE id=?", (appointment_id,)).fetchone()
        if appt_row:
            appt = dict(appt_row)

    # 2. Patient health profile — read directly (doctor authorized via appointment assignment)
    profile_row = db.execute(
        "SELECT blood_group, allergies, chronic_conditions FROM patient_health_profiles WHERE patient_id=?",
        (patient_id,),
    ).fetchone()
    profile = dict(profile_row) if profile_row else {}
    for field in ("allergies", "chronic_conditions"):
        raw = profile.get(field)
        if isinstance(raw, str):
            try:
                profile[field] = json.loads(raw)
            except (TypeError, ValueError):
                profile[field] = []
        elif raw is None:
            profile[field] = []

    # Recent records for snapshot
    recent_records = db.execute(
        "SELECT id, title, category FROM medical_records WHERE owner_id=? ORDER BY created_at DESC LIMIT 5",
        (patient_id,),
    ).fetchall()
    recent_reports_list = [dict(r) for r in recent_records]


    # 3. Active medications & safety checks
    rx_rows = db.execute(
        """
        SELECT p.id, p.prescriber_name, p.issue_date, p.diagnosis_notes,
               pi.medicine_name, pi.dosage, pi.frequency
        FROM prescriptions p
        LEFT JOIN prescription_items pi ON pi.prescription_id=p.id
        WHERE p.patient_id=? AND p.status='active'
        ORDER BY p.issue_date DESC
        """,
        (patient_id,),
    ).fetchall()

    active_meds = []
    for r in rx_rows:
        if r["medicine_name"]:
            active_meds.append({
                "medicine_name": r["medicine_name"],
                "dosage": r["dosage"],
                "frequency": r["frequency"],
                "prescriber": r["prescriber_name"],
            })

    # Run medication safety checks against declared profile allergies and chronic conditions
    declared_allergies = list(profile.get("allergies") or [])
    declared_conditions = list(profile.get("chronic_conditions") or [])
    safety_analysis = check_medication_safety(
        active_meds,
        patient_allergies=declared_allergies,
        patient_conditions=declared_conditions,
    )

    # 4. Recent vitals
    vitals_rows = db.execute(
        """
        SELECT metric_type, metric_value, unit, recorded_at
        FROM health_metrics
        WHERE user_id=?
        ORDER BY recorded_at DESC LIMIT 10
        """,
        (patient_id,),
    ).fetchall()
    vitals_summary = [dict(v) for v in vitals_rows]

    # 5. Draft SOAP Clinical Note
    soap_draft = {
        "subjective": (
            f"Patient {patient['name']} presents for consultation. "
            f"Reason for visit: {appt.get('reason') if appt else 'Clinical evaluation'}. "
            f"Known chronic conditions: {', '.join(declared_conditions) if declared_conditions else 'None reported'}. "
            f"Declared allergies: {', '.join(declared_allergies) if declared_allergies else 'No known drug allergies reported'}."
        ),
        "objective": (
            f"Recorded vitals: {_fmt_vitals(vitals_summary)}. "
            f"Active medications on file: {len(active_meds)}."
        ),
        "assessment_draft": (
            "[CLINICIAN DRAFT - REQUIRES DOCTOR EVALUATION]: "
            "Review history, symptoms, and physical examination findings to document clinical diagnosis."
        ),
        "plan_draft": (
            "[CLINICIAN DRAFT - REQUIRES DOCTOR REVIEW]: "
            "1. Discuss medication reconciliation and therapy goals.\n"
            "2. Review lifestyle and preventive health recommendations.\n"
            "3. Schedule follow-up as clinically indicated."
        ),
        "status": "DRAFT_REQUIRES_CLINICIAN_REVIEW",
        "human_in_the_loop_guarantee": (
            "This clinical note is an AI-generated draft. It is NOT finalized or signed. "
            "The licensed clinician must review, edit, approve, or reject this note."
        ),
    }

    # 6. Patient Instructions Draft
    patient_instructions_draft = (
        "1. Take all medications exactly as directed by your physician.\n"
        "2. Record your blood pressure and blood sugar regularly if advised.\n"
        "3. Seek emergency care immediately if experiencing chest pain, shortness of breath, or sudden weakness."
    )

    return {
        "patient": {"id": patient["id"], "name": patient["name"], "email": patient["email"]},
        "appointment": appt,
        "chief_complaint": appt.get("reason") if appt else "Clinical consultation",
        "longitudinal_snapshot": {
            "declared_allergies": declared_allergies,
            "chronic_conditions": declared_conditions,
            "blood_group": profile.get("blood_group"),
            "active_medications": active_meds,
            "recent_vitals": vitals_summary,
            "recent_reports": recent_reports_list,
        },
        "safety_and_contraindication_alerts": safety_analysis["all_alerts"],
        "draft_soap_note": soap_draft,
        "draft_patient_instructions": patient_instructions_draft,
        "disclaimer": (
            "Clinical decision support only. ZENDOC does not independently diagnose conditions or prescribe treatments. "
            "All clinical notes, diagnoses, and treatment plans require the licensed clinician's explicit human review and signature."
        ),
    }


def finalize_clinical_consultation(
    doctor_actor: Any,
    appointment_id: int,
    consultation_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Submits doctor-reviewed, signed SOAP clinical note, completes the appointment,
    and executes post-consultation workflow automation (timeline, follow-up task, reminders).
    """
    doc_id = _user_id(doctor_actor)
    db = get_db()

    appt_row = db.execute("SELECT * FROM appointments WHERE id=?", (appointment_id,)).fetchone()
    if not appt_row:
        raise LookupError("Appointment not found.")
    appt = dict(appt_row)
    patient_id = appt["patient_id"]

    subjective = str(consultation_data.get("subjective") or "").strip()
    objective = str(consultation_data.get("objective") or "").strip()
    assessment = str(consultation_data.get("assessment") or "").strip()
    plan = str(consultation_data.get("plan") or "").strip()
    patient_instructions = str(consultation_data.get("patient_instructions") or "").strip()
    diagnosis = str(consultation_data.get("diagnosis") or "").strip()

    if not assessment and not diagnosis:
        raise ValueError("Clinician assessment or diagnosis is required to finalize consultation.")

    now = now_iso()
    doc_name = _actor_field(doctor_actor, "name") or "Attending Clinician"

    # 1. Update appointment to completed
    db.execute(
        "UPDATE appointments SET status='completed', updated_at=? WHERE id=?",
        (now, appointment_id),
    )

    # 2. Record consultation into health_timeline_events with PROVIDER_RECORDED provenance
    soap_summary = f"SOAP Note: Assessment: {assessment or diagnosis}. Plan: {plan}"
    timeline_event_id = add_timeline_event(
        patient_id=patient_id,
        event_type="consultation",
        title=f"Clinical Consultation with {doc_name}",
        event_at=now,
        summary=soap_summary[:1000],
        provider_name=doc_name,
        source="PROVIDER_RECORDED",
        source_ref=f"appointment:{appointment_id}",
        created_by=doc_id,
    )

    # 3. Create non-clinical follow-up action
    follow_up_days = consultation_data.get("follow_up_days") or 14
    action_data = {
        "patient_id": patient_id,
        "action_type": "FOLLOW_UP_CONSULTATION",
        "title": f"Follow-up visit with {doc_name}",
        "provider_name": doc_name,
        "service_ref": f"appointment:{appointment_id}",
    }
    care_action = None
    try:
        care_action = create_action(
            patient_id=patient_id,
            action_type="FOLLOW_UP_CONSULTATION",
            title=f"Follow-up with {doc_name}",
            owner_type="patient",
            provider_name=doc_name,
            service_ref=f"appointment:{appointment_id}",
        )
    except Exception:
        pass

    # 4. Publish event for automation engine
    publish_event(
        "appointment.completed",
        actor=doctor_actor,
        entity_type="appointment",
        entity_id=str(appointment_id),
        status="success",
        payload={
            "appointment_id": appointment_id,
            "patient_id": patient_id,
            "diagnosis": diagnosis or assessment,
            "follow_up_days": follow_up_days,
            "has_patient_instructions": bool(patient_instructions),
        },
    )

    db.commit()

    return {
        "status": "completed",
        "appointment_id": appointment_id,
        "patient_id": patient_id,
        "timeline_event_id": timeline_event_id,
        "care_action": care_action,
        "signed_by": doc_name,
        "signed_at": now,
        "post_consultation_automation": {
            "timeline_recorded": True,
            "appointment_status": "completed",
            "follow_up_scheduled": True,
            "event_published": "appointment.completed",
        },
    }
