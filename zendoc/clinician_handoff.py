"""Patient-controlled clinician handoff packet builder.

The packet summarizes ZENDOC-stored facts for a human clinician. It does not
diagnose, prescribe, infer new conditions, or automatically transmit patient
data to any external party.
"""
from __future__ import annotations

from .care_action_ledger import ensure_care_action_ledger_schema
from .db import get_db, now_iso
from .health_summary import build_health_summary
from .health_timeline import list_timeline

PACKET_VERSION = "zendoc-clinician-handoff-v1"


def _value(actor, key, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    if isinstance(actor, dict):
        return actor.get(key, default)
    return default


def _clean_text(value, limit):
    return " ".join(str(value or "").strip().split())[:limit]


def _questions(value):
    if isinstance(value, (list, tuple)):
        candidates = value
    else:
        candidates = str(value or "").replace(";", "\n").splitlines()
    result = []
    for item in candidates:
        text = _clean_text(item, 300)
        if text and text not in result:
            result.append(text)
        if len(result) >= 8:
            break
    return result


def _open_actions(patient_id):
    ensure_care_action_ledger_schema()
    rows = get_db().execute(
        """SELECT id,action_uid,action_type,title,status,owner_type,provider_name,
                  estimated_cost,currency,due_at,service_ref,updated_at
           FROM care_actions
           WHERE patient_id=? AND status NOT IN ('COMPLETED','BLOCKED','CANCELLED')
           ORDER BY updated_at DESC,id DESC LIMIT 10""",
        (int(patient_id),),
    ).fetchall()
    return [dict(row) for row in rows]


def build_clinician_handoff_packet(actor, *, reason_for_visit=None, questions=None):
    if str(_value(actor, "role", "")) != "patient":
        raise PermissionError("Only the patient can prepare a clinician handoff packet from this page.")
    patient_id = int(_value(actor, "id", 0) or 0)
    if not patient_id:
        raise PermissionError("Authentication is required.")
    summary = build_health_summary(actor, patient_id)
    timeline = list_timeline(actor, patient_id=patient_id, order="desc", page=1, per_page=12)
    profile = dict(summary.get("profile") or {})
    important = {
        "allergies": list(profile.get("allergies") or []),
        "current_medications": list(profile.get("current_medications") or []),
        "chronic_conditions": list(profile.get("chronic_conditions") or []),
        "previous_conditions": list(profile.get("previous_conditions") or []),
        "surgeries": list(profile.get("surgeries") or []),
        "vaccinations": list(profile.get("vaccinations") or []),
        "blood_group": profile.get("blood_group"),
        "sex_at_birth": profile.get("sex_at_birth"),
        "date_of_birth": profile.get("date_of_birth"),
    }
    missing = []
    if not important["allergies"]:
        missing.append("allergies not recorded")
    if not important["current_medications"]:
        missing.append("current medications not recorded")
    if not important["chronic_conditions"]:
        missing.append("chronic conditions not recorded")
    if not summary.get("recent_reports"):
        missing.append("no recent reports in ZENDOC")
    if not summary.get("recent_measurements"):
        missing.append("no recent measurements in ZENDOC")
    return {
        "packet_version": PACKET_VERSION,
        "generated_at": now_iso(),
        "patient": dict(summary["patient"]),
        "reason_for_visit": _clean_text(reason_for_visit, 1000),
        "questions_for_clinician": _questions(questions),
        "important_health_information": important,
        "recent_appointments": list(summary.get("recent_appointments") or []),
        "recent_reports": list(summary.get("recent_reports") or []),
        "recent_measurements": list(summary.get("recent_measurements") or []),
        "recent_timeline": list(timeline.get("events") or []),
        "open_care_actions": _open_actions(patient_id),
        "completeness_notes": missing,
        "clinical_interpretation": None,
        "sharing": {
            "automatic_external_sharing": False,
            "patient_controlled": True,
            "notice": (
                "This packet is prepared for the patient to review and share. "
                "ZENDOC does not automatically send it to a clinician or external service."
            ),
        },
        "provenance": {
            "profile": "ZENDOC patient Health Memory",
            "appointments": "ZENDOC appointment records",
            "reports": "ZENDOC medical-record/report metadata",
            "measurements": "ZENDOC health measurements",
            "timeline": "ZENDOC Health Timeline",
            "care_actions": "ZENDOC Care Action Ledger",
            "patient_entered_context": (
                "Reason for visit and clinician questions are entered by the patient for this packet."
            ),
        },
        "safety_notice": (
            "Human handoff summary only. ZENDOC does not diagnose, prescribe, "
            "or certify that this packet is clinically complete."
        ),
    }
