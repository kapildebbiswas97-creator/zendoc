"""
Health Memory 2.0 & Longitudinal Health Intelligence Test Suite.
Verifies expanded clinical timeline, biomarker trend calculations,
unit normalization, red-flag safety, conflict detection, and longitudinal API.
"""
from io import BytesIO
import pytest
from tests.test_milestone1 import api_token, make_client
from zendoc.db import get_db
from zendoc.health_timeline import TIMELINE_TYPES, FILTER_ALIASES, list_timeline, add_timeline_event
from zendoc.report_intelligence import (
    STANDARD_BIOMARKERS,
    lookup_biomarker_definition,
    normalize_biomarker_value,
    calculate_biomarker_longitudinal_trend,
    get_report_result_trend,
)
from zendoc.health_memory_continuity import (
    detect_record_conflicts_and_duplicates,
    get_longitudinal_health_summary,
)


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_expanded_timeline_types_and_aliases():
    expected_new_types = {
        "prescription", "diagnosis", "condition", "care_plan", "symptom", "vital",
        "allergy", "clinical_note", "patient_note", "family_history", "risk_factor",
        "device_reading", "lab_result"
    }
    assert expected_new_types.issubset(TIMELINE_TYPES)

    assert FILTER_ALIASES["prescriptions"] == "prescription"
    assert FILTER_ALIASES["vitals"] == "measurement"
    assert FILTER_ALIASES["allergies"] == "allergy"
    assert FILTER_ALIASES["diagnoses"] == "diagnosis"
    assert FILTER_ALIASES["notes"] == "clinical_note"
    assert FILTER_ALIASES["devices"] == "device_reading"


def test_timeline_prescriptions_provenance_and_freshness(tmp_path):
    app, client = make_client(tmp_path)
    token = api_token(client, "patient-memory@example.com")
    with app.app_context():
        user = get_db().execute("SELECT id FROM users WHERE email='patient-memory@example.com'").fetchone()
        patient_id = user["id"]

        # Insert prescription
        get_db().execute(
            """
            INSERT INTO prescriptions (prescription_uid, patient_id, prescriber_name, issue_date, diagnosis_notes, status, data_mode, created_at, updated_at)
            VALUES ('RX-TEST-001', ?, 'Dr. Longitudinal', '2026-09-15', 'Essential hypertension management', 'active', 'LIVE', '2026-09-15T10:00:00Z', '2026-09-15T10:00:00Z')
            """,
            (patient_id,),
        )
        # Insert measurement
        get_db().execute(
            """
            INSERT INTO health_metrics (user_id, metric_type, metric_value, unit, recorded_at)
            VALUES (?, 'blood_pressure', '128/82', 'mmHg', '2026-09-20T08:00:00Z')
            """,
            (patient_id,),
        )
        get_db().commit()

        actor = {"id": patient_id, "role": "patient"}
        timeline = list_timeline(actor, patient_id=patient_id)
        assert timeline["total"] >= 2

        event_types = {e["event_type"] for e in timeline["events"]}
        assert "prescription" in event_types
        assert "measurement" in event_types

        # Verify provenance and confidence
        rx_event = next(e for e in timeline["events"] if e["event_type"] == "prescription")
        assert rx_event["provenance"] == "PROVIDER_RECORDED"
        assert rx_event["confidence"] == 1.0
        assert rx_event["data_freshness"] in {"LIVE", "RECENT", "HISTORICAL"}

        meas_event = next(e for e in timeline["events"] if e["event_type"] == "measurement")
        assert meas_event["provenance"] in {"DEVICE_RECORDED", "USER_REPORTED"}
        assert meas_event["confidence"] >= 0.7


def test_biomarker_normalization_and_ranges():
    # Test lookup
    meta = lookup_biomarker_definition("Fast Blood Sugar")
    assert meta is not None
    assert meta["canonical_name"] == "Fasting Blood Glucose"
    assert meta["standard_unit"] == "mg/dL"

    # Test conversion mmol/L -> mg/dL
    converted_val, std_unit, _ = normalize_biomarker_value("glucose", 5.5, "mmol/L")
    assert std_unit == "mg/dL"
    assert 98.0 <= converted_val <= 100.0


def test_biomarker_longitudinal_trend_calculation():
    meta = lookup_biomarker_definition("glucose")
    series = [
        {"numeric_value": 90.0, "unit": "mg/dL", "measurement_date": "2026-01-10", "id": 1},
        {"numeric_value": 115.0, "unit": "mg/dL", "measurement_date": "2026-04-10", "id": 2},
        {"numeric_value": 130.0, "unit": "mg/dL", "measurement_date": "2026-08-10", "id": 3},
    ]

    trend = calculate_biomarker_longitudinal_trend(series, meta)
    assert trend["status"] == "ANALYZED"
    assert trend["trend_direction"] == "RISING"
    assert trend["delta"] == 15.0  # 130 - 115
    assert trend["percent_change"] > 0
    assert "clinician_questions" in trend
    assert len(trend["clinician_questions"]) > 0
    assert "non_diagnostic_guarantee" in trend
    assert "does not independently diagnose" in trend["non_diagnostic_guarantee"]


def test_red_flag_alerting_without_autonomous_diagnosis():
    meta = lookup_biomarker_definition("glucose")
    critical_series = [
        {"numeric_value": 350.0, "unit": "mg/dL", "measurement_date": "2026-09-01", "id": 1}
    ]

    trend = calculate_biomarker_longitudinal_trend(critical_series, meta)
    assert trend["red_flag"] is True
    assert "Urgent medical consultation" in trend["red_flag_reason"]
    # Guarantees no autonomous diagnosis
    assert "ZENDOC does not independently diagnose" in trend["non_diagnostic_guarantee"]


def test_record_integrity_conflicts_and_duplicates(tmp_path):
    app, client = make_client(tmp_path)
    token = api_token(client, "conflict-patient@example.com")
    with app.app_context():
        user = get_db().execute("SELECT id FROM users WHERE email='conflict-patient@example.com'").fetchone()
        patient_id = user["id"]

        # Duplicate metrics on same timestamp
        get_db().execute(
            """
            INSERT INTO health_metrics (user_id, metric_type, metric_value, unit, recorded_at)
            VALUES (?, 'weight', '72', 'kg', '2026-09-01T08:00:00Z'),
                   (?, 'weight', '72', 'kg', '2026-09-01T08:00:00Z')
            """,
            (patient_id, patient_id),
        )

        # Conflicting blood group: Profile says A+, Record result says B+
        get_db().execute(
            """
            INSERT INTO patient_health_profiles (patient_id, blood_group, created_at, updated_at)
            VALUES (?, 'A+', '2026-09-01T00:00:00Z', '2026-09-01T00:00:00Z')
            """,
            (patient_id,),
        )
        rec_id = get_db().execute(
            """
            INSERT INTO medical_records (owner_id, uploaded_by, title, category, original_filename, stored_filename, mime_type, file_size, created_at)
            VALUES (?, ?, 'Lab Blood Test', 'Report', 'blood.txt', 'key1', 'text/plain', 128, '2026-09-01T00:00:00Z')
            """,
            (patient_id, patient_id),
        ).lastrowid
        get_db().execute(
            """
            INSERT INTO report_results (record_id, test_name, value_text, measurement_date, source, created_by, created_at)
            VALUES (?, 'Blood Group', 'B+', '2026-09-01', 'clinical', ?, '2026-09-01T00:00:00Z')
            """,
            (rec_id, patient_id),
        )
        get_db().commit()

        actor = {"id": patient_id, "role": "patient"}
        integrity = detect_record_conflicts_and_duplicates(patient_id, actor)
        assert integrity["duplicates_count"] >= 1
        assert integrity["conflicts_count"] >= 1
        assert integrity["integrity_score"] < 1.0


def test_longitudinal_health_summary_api(tmp_path):
    app, client = make_client(tmp_path)
    token = api_token(client, "longitudinal-api@example.com")
    resp = client.get("/api/v1/health-memory/longitudinal", headers=headers(token))
    assert resp.status_code == 200
    data = resp.json["longitudinal_health_memory"]
    assert "timeline_overview" in data
    assert "provenance_summary" in data
    assert "next_safe_actions" in data
    assert "record_integrity" in data
    assert "disclaimer" in data
    assert "ZENDOC does not independently diagnose" in data["disclaimer"]
