from .db import get_db
from .health_access import authorize_patient, has_active_grant
from .health_analytics import calculate_bmi, list_measurements
from .health_profile import get_health_profile
from .report_intelligence import list_reports


def _value(actor, key):
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    return actor.get(key) if isinstance(actor, dict) else None


def _can(actor, patient_id, scope):
    role = _value(actor, "role")
    if role == "admin" or (role == "patient" and int(_value(actor, "id")) == int(patient_id)):
        return True
    return role in {"doctor", "hospital"} and has_active_grant(patient_id, _value(actor, "id"), scope)


def build_health_summary(actor, patient_id=None):
    target_id = int(patient_id or _value(actor, "id"))
    patient = get_db().execute("SELECT id,name FROM users WHERE id=? AND role='patient' AND active=1", (target_id,)).fetchone()
    if not patient:
        raise LookupError("Patient not found.")
    if _value(actor, "role") == "patient" and int(_value(actor, "id")) != target_id:
        raise PermissionError("You cannot access another patient's health summary.")
    if _value(actor, "role") not in {"patient", "admin", "doctor", "hospital"}:
        raise PermissionError("Health summary access is not permitted.")
    summary = {"patient": {"id": patient["id"], "name": patient["name"]}, "access_scopes": []}
    if _can(actor, target_id, "profile"):
        summary["profile"] = get_health_profile(actor, target_id)
        summary["access_scopes"].append("profile")
    if _can(actor, target_id, "appointments"):
        authorize_patient(actor, target_id, "appointments")
        rows = get_db().execute(
            "SELECT id,provider_name,specialty,scheduled_for,reason,status FROM appointments WHERE patient_id=? ORDER BY scheduled_for DESC LIMIT 5",
            (target_id,),
        ).fetchall()
        summary["recent_appointments"] = [dict(row) for row in rows]
        summary["access_scopes"].append("appointments")
    if _can(actor, target_id, "reports"):
        summary["recent_reports"] = list_reports(actor, target_id, page=1, per_page=5)["reports"]
        summary["access_scopes"].append("reports")
    if _can(actor, target_id, "measurements"):
        measurements = list_measurements(actor, target_id, limit=10)
        summary["recent_measurements"] = measurements
        summary["access_scopes"].append("measurements")
        profile = summary.get("profile", {})
        latest_weight = next((item["numeric_value"] for item in measurements if item["metric_type"] == "weight" and item["numeric_value"] is not None), profile.get("baseline_weight_kg"))
        summary["current_bmi"] = calculate_bmi(profile.get("height_cm"), latest_weight)
    if _value(actor, "role") in {"doctor", "hospital"} and not summary["access_scopes"]:
        raise PermissionError("Patient consent is required to view this health summary.")
    summary["privacy"] = "Private health summary. Access is limited to the patient and explicitly authorized roles/scopes."
    return summary


def export_health_data(actor):
    if _value(actor, "role") != "patient":
        raise PermissionError("Only patients can export their complete health data.")
    patient_id = int(_value(actor, "id"))
    summary = build_health_summary(actor, patient_id)
    appointments = get_db().execute("SELECT * FROM appointments WHERE patient_id=? ORDER BY scheduled_for", (patient_id,)).fetchall()
    records = list_reports(actor, patient_id, page=1, per_page=100)
    measurements = list_measurements(actor, patient_id, limit=500)
    summary.update(
        {
            "appointments": [dict(row) for row in appointments],
            "reports": records["reports"],
            "measurements": measurements,
            "export_note": "This structured export contains ZENDOC-stored data and does not certify clinical completeness.",
        }
    )
    return summary
