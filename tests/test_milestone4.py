import json
import sqlite3
from datetime import datetime, timedelta, timezone
from io import BytesIO

from zendoc import create_app
from zendoc.db import get_db

from tests.test_milestone1 import api_token, csrf, login_web, make_client, register_web
from tests.test_milestone3 import register_api


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def user_id(app, email):
    with app.app_context():
        return get_db().execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()["id"]


def upload_report(client, token, title="CBC Report", report_type="blood_test", document_date="2026-08-20", content=b"sample report"):
    return client.post(
        "/api/v1/reports",
        data={
            "title": title,
            "category": "Medical report",
            "report_type": report_type,
            "document_date": document_date,
            "provider_name": "Example Clinician",
            "lab_name": "Example Lab",
            "description": "Patient supplied document",
            "file": (BytesIO(content), f"{title.lower().replace(' ', '-')}.txt"),
        },
        headers=headers(token),
        content_type="multipart/form-data",
    )


def verified_provider(app, client, email="provider-m4@example.com"):
    token = register_api(client, email, "doctor")
    response = client.post(
        "/api/v1/provider/profile",
        json={"specialty": "cardiology", "organization": "Consent Clinic", "city": "Kolkata"},
        headers=headers(token),
    )
    assert response.status_code == 200
    with app.app_context():
        row = get_db().execute(
            "SELECT pp.id,pp.user_id FROM provider_profiles pp JOIN users u ON u.id=pp.user_id WHERE u.email=?",
            (email,),
        ).fetchone()
        get_db().execute("UPDATE provider_profiles SET verification_status='verified' WHERE id=?", (row["id"],))
        get_db().commit()
        return token, row["id"], row["user_id"]


def test_health_profile_create_update_validation_and_cross_user_isolation(tmp_path):
    app, client = make_client(tmp_path)
    token_one = api_token(client, "profile-one@example.com")
    token_two = api_token(client, "profile-two@example.com")
    patient_one = user_id(app, "profile-one@example.com")
    response = client.put(
        "/api/v1/health-profile",
        json={
            "date_of_birth": "1998-04-12",
            "blood_group": "O+",
            "height_cm": 172,
            "baseline_weight_kg": 70,
            "allergies": ["Penicillin"],
            "current_medications": ["Medicine A"],
            "health_goals": "Improve sleep\nWalk daily",
        },
        headers=headers(token_one),
    )
    assert response.status_code == 200
    assert response.json["health_profile"]["allergies"] == ["Penicillin"]
    updated = client.put(
        "/api/v1/health-profile",
        json={"blood_group": "A+", "current_medications": ["Medicine B"]},
        headers=headers(token_one),
    )
    assert updated.json["health_profile"]["blood_group"] == "A+"
    denied = client.get(f"/api/v1/health-profile?patient_id={patient_one}", headers=headers(token_two))
    assert denied.status_code == 403
    invalid = client.put("/api/v1/health-profile", json={"height_cm": 999}, headers=headers(token_one))
    assert invalid.status_code == 400


def test_timeline_connects_appointments_reports_measurements_filter_search_and_sort(tmp_path):
    _app, client = make_client(tmp_path)
    token = api_token(client, "timeline@example.com")
    appointment = client.post(
        "/api/v1/appointments",
        json={"provider_name": "Heart Doctor", "scheduled_for": "2026-09-01T10:00:00+00:00", "reason": "Cardiology follow-up"},
        headers=headers(token),
    )
    assert appointment.status_code == 201
    measurement = client.post(
        "/api/v1/health-measurements",
        json={"metric_type": "weight", "value": 70, "unit": "kg", "recorded_at": "2026-08-25T09:00:00+00:00"},
        headers=headers(token),
    )
    assert measurement.status_code == 201
    report = upload_report(client, token)
    assert report.status_code == 201
    timeline = client.get("/api/v1/health-timeline?order=desc", headers=headers(token))
    assert timeline.status_code == 200
    assert {event["event_type"] for event in timeline.json["events"]} >= {"appointment", "measurement", "report"}
    assert timeline.json["events"][0]["event_at"] >= timeline.json["events"][-1]["event_at"]
    filtered = client.get("/api/v1/health-timeline?type=report", headers=headers(token))
    assert {event["event_type"] for event in filtered.json["events"]} == {"report"}
    searched = client.get("/api/v1/health-timeline/search?q=cardiology", headers=headers(token))
    assert searched.json["total"] == 1
    oldest = client.get("/api/v1/health-timeline?order=asc", headers=headers(token))
    assert oldest.json["events"][0]["event_at"] <= oldest.json["events"][-1]["event_at"]
    assert client.get("/api/v1/health-timeline/search", headers=headers(token)).status_code == 400


def test_report_metadata_truthful_extraction_secure_download_and_bad_signature(tmp_path):
    _app, client = make_client(tmp_path)
    owner_token = api_token(client, "report-owner@example.com")
    other_token = api_token(client, "report-other@example.com")
    created = upload_report(client, owner_token)
    assert created.status_code == 201
    record_id = created.json["record_id"]
    assert created.json["report"]["report_id"].startswith("ZR-")
    assert created.json["report"]["extraction_status"] == "unavailable"
    assert "stored_filename" not in created.json["report"]
    explanation = client.get(f"/api/v1/reports/{record_id}/explanation", headers=headers(owner_token))
    assert explanation.json["status"] == "unavailable"
    assert explanation.json["results"] == []
    assert "Automatic extraction unavailable" in explanation.json["message"]
    assert client.get(f"/api/v1/reports/{record_id}/download", headers=headers(owner_token)).status_code == 200
    assert client.get(f"/api/v1/reports/{record_id}/download", headers=headers(other_token)).status_code == 403
    bad_upload = client.post(
        "/api/v1/reports",
        data={"title": "Fake PDF", "category": "Report", "report_type": "other", "file": (BytesIO(b"not a pdf"), "fake.pdf")},
        headers=headers(owner_token),
        content_type="multipart/form-data",
    )
    assert bad_upload.status_code == 400


def test_structured_report_results_explanation_and_unit_safe_lab_trends(tmp_path):
    _app, client = make_client(tmp_path)
    token = api_token(client, "structured@example.com")
    first = upload_report(client, token, title="CBC One", document_date="2026-07-10")
    second = upload_report(client, token, title="CBC Two", document_date="2026-08-10")
    for response, value, unit, flag in ((first, "13.1", "g/dL", "normal"), (second, "11.4", "g/dL", "low")):
        saved = client.post(
            f"/api/v1/reports/{response.json['record_id']}/results",
            json={"test_name": "Hemoglobin", "value": value, "unit": unit, "reference_range": "12.0-16.0", "abnormal_flag": flag},
            headers=headers(token),
        )
        assert saved.status_code == 201
    third = client.post(
        f"/api/v1/reports/{second.json['record_id']}/results",
        json={"test_name": "Hemoglobin", "value": "120", "unit": "g/L", "reference_range": "120-160", "abnormal_flag": "normal"},
        headers=headers(token),
    )
    assert third.status_code == 201
    explanation = client.get(f"/api/v1/reports/{second.json['record_id']}/explanation", headers=headers(token))
    assert explanation.json["status"] == "structured_results_available"
    assert "not a diagnosis" in explanation.json["disclaimer"]
    trend = client.get("/api/v1/report-trends?test_name=Hemoglobin", headers=headers(token))
    assert trend.status_code == 200
    assert trend.json["unit_mismatch"] is True
    assert {series["unit"] for series in trend.json["series"]} == {"g/dL", "g/L"}


def test_measurement_source_validation_blood_pressure_and_trends(tmp_path):
    _app, client = make_client(tmp_path)
    token = api_token(client, "measurements@example.com")
    for day, value in ((20, 72), (26, 70)):
        response = client.post(
            "/api/v1/health-measurements",
            json={"metric_type": "weight", "value": value, "unit": "kg", "source": "manual", "recorded_at": f"2026-08-{day}T08:00:00+00:00"},
            headers=headers(token),
        )
        assert response.status_code == 201
    mislabeled = client.post(
        "/api/v1/health-measurements",
        json={"metric_type": "steps", "value": 5000, "source": "wearable"},
        headers=headers(token),
    )
    assert mislabeled.status_code == 400
    missing_diastolic = client.post(
        "/api/v1/health-measurements",
        json={"metric_type": "blood_pressure", "value": 120},
        headers=headers(token),
    )
    assert missing_diastolic.status_code == 400
    blood_pressure = client.post(
        "/api/v1/health-measurements",
        json={"metric_type": "blood_pressure", "value": 120, "secondary_value": 80, "unit": "mmHg"},
        headers=headers(token),
    )
    assert blood_pressure.status_code == 201
    trend = client.get("/api/v1/health-trends?metric_type=weight&period=30d", headers=headers(token))
    assert trend.status_code == 200
    assert trend.json["series"][0]["direction"] == "down"
    measurements = client.get("/api/v1/health-measurements", headers=headers(token))
    assert all(item["source"] == "manual" for item in measurements.json["measurements"])


def test_patient_consent_provider_scopes_and_revocation(tmp_path):
    app, client = make_client(tmp_path)
    provider_token, provider_profile_id, _provider_id = verified_provider(app, client)
    patient_token = api_token(client, "consent-patient@example.com")
    patient_id = user_id(app, "consent-patient@example.com")
    client.put("/api/v1/health-profile", json={"allergies": ["Latex"]}, headers=headers(patient_token))
    denied = client.get(f"/api/v1/health-summary?patient_id={patient_id}", headers=headers(provider_token))
    assert denied.status_code == 403
    grant = client.post(
        "/api/v1/health-access",
        json={"provider_profile_id": provider_profile_id, "scopes": ["profile", "timeline"]},
        headers=headers(patient_token),
    )
    assert grant.status_code == 201
    profile = client.get(f"/api/v1/health-profile?patient_id={patient_id}", headers=headers(provider_token))
    assert profile.status_code == 200
    assert profile.json["health_profile"]["allergies"] == ["Latex"]
    assert client.get(f"/api/v1/health-timeline?patient_id={patient_id}", headers=headers(provider_token)).status_code == 200
    assert client.get(f"/api/v1/reports?patient_id={patient_id}", headers=headers(provider_token)).status_code == 403
    summary = client.get(f"/api/v1/health-summary?patient_id={patient_id}", headers=headers(provider_token))
    assert summary.status_code == 200
    assert summary.json["health_summary"]["access_scopes"] == ["profile"]
    revoked = client.delete(f"/api/v1/health-access/{grant.json['grant_id']}", headers=headers(patient_token))
    assert revoked.status_code == 200
    assert client.get(f"/api/v1/health-profile?patient_id={patient_id}", headers=headers(provider_token)).status_code == 403


def test_expired_consent_fails_securely(tmp_path):
    app, client = make_client(tmp_path)
    provider_token, provider_profile_id, provider_id = verified_provider(app, client, "expired-provider@example.com")
    patient_token = api_token(client, "expired-patient@example.com")
    patient_id = user_id(app, "expired-patient@example.com")
    grant = client.post(
        "/api/v1/health-access",
        json={"provider_profile_id": provider_profile_id, "scopes": ["profile"]},
        headers=headers(patient_token),
    )
    assert grant.status_code == 201
    with app.app_context():
        get_db().execute("UPDATE health_access_grants SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (grant.json["grant_id"],))
        get_db().commit()
    response = client.get(f"/api/v1/health-profile?patient_id={patient_id}", headers=headers(provider_token))
    assert response.status_code == 403
    with app.app_context():
        row = get_db().execute("SELECT provider_id FROM health_access_grants WHERE id=?", (grant.json["grant_id"],)).fetchone()
        assert row["provider_id"] == provider_id


def test_ai_routes_timeline_report_trend_medications_and_preserves_emergency_priority(tmp_path):
    _app, client = make_client(tmp_path)
    token = api_token(client, "ai-memory@example.com")
    client.put("/api/v1/health-profile", json={"current_medications": ["Medicine A"]}, headers=headers(token))
    client.post("/api/v1/health-measurements", json={"metric_type": "weight", "value": 70}, headers=headers(token))
    upload_report(client, token)
    cases = {
        "show my health history": "health_timeline",
        "show my latest report": "report_history",
        "explain my blood test": "report_intelligence",
        "show my weight trend": "health_analytics",
        "what medicines am I taking?": "health_profile",
    }
    for message, expected_intent in cases.items():
        response = client.post("/api/v1/ai/message", json={"message": message}, headers=headers(token))
        assert response.status_code == 200
        assert response.json["intent"] == expected_intent
        assert response.json["provider"] == "authorized_health_services"
    emergency = client.post("/api/v1/ai/message", json={"message": "show my report, I have chest pain"}, headers=headers(token))
    assert emergency.json["intent"] == "emergency"
    assert emergency.json["emergency"] is True


def test_health_summary_and_export_do_not_expose_storage_paths(tmp_path):
    _app, client = make_client(tmp_path)
    token = api_token(client, "export@example.com")
    client.put(
        "/api/v1/health-profile",
        json={"height_cm": 170, "baseline_weight_kg": 68, "chronic_conditions": ["Condition supplied by patient"]},
        headers=headers(token),
    )
    upload_report(client, token)
    summary = client.get("/api/v1/health-summary", headers=headers(token))
    assert summary.status_code == 200
    assert summary.json["health_summary"]["profile"]["chronic_conditions"] == ["Condition supplied by patient"]
    exported = client.get("/api/v1/health-export", headers=headers(token))
    assert exported.status_code == 200
    serialized = json.dumps(exported.json)
    assert "stored_filename" not in serialized
    assert str(tmp_path) not in serialized
    assert "attachment" in exported.headers["Content-Disposition"]


def test_web_health_profile_timeline_report_and_legacy_monitor_render(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "web-health@example.com", "Web Patient")
    login_web(client, "patient", "web-health@example.com")
    profile_page = client.get("/health-profile")
    token = csrf(profile_page.data.decode())
    saved = client.post(
        "/health-profile",
        data={"csrf_token": token, "blood_group": "B+", "allergies": "Pollen"},
        follow_redirects=True,
    )
    assert b"Health profile updated" in saved.data
    health_page = client.get("/health")
    token = csrf(health_page.data.decode())
    metric = client.post(
        "/health",
        data={"csrf_token": token, "metric_type": "weight", "metric_value": "69", "unit": "kg"},
        follow_redirects=True,
    )
    assert b"Health metric saved" in metric.data
    records_page = client.get("/records")
    token = csrf(records_page.data.decode())
    report = client.post(
        "/records",
        data={"csrf_token": token, "title": "Legacy Text Report", "category": "Lab", "record_file": (BytesIO(b"legacy report"), "legacy.txt")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Record uploaded" in report.data
    assert b"Legacy Text Report" in client.get("/timeline").data
    assert client.get("/reports/1").status_code == 200


def test_additive_migration_preserves_legacy_health_metric(tmp_path):
    database = tmp_path / "legacy.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE health_metrics (id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,metric_type TEXT NOT NULL,metric_value TEXT NOT NULL,unit TEXT,recorded_at TEXT NOT NULL)"
    )
    connection.execute("INSERT INTO health_metrics (user_id,metric_type,metric_value,unit,recorded_at) VALUES (999,'bmi','24.2','kg/m2','2026-01-01')")
    connection.commit()
    connection.close()
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(database),
            "UPLOAD_FOLDER": str(tmp_path / "legacy-uploads"),
            "SECRET_KEY": "test-secret",
            "ADMIN_EMAIL": "admin@example.com",
            "ADMIN_PASSWORD": "AdminStrong123",
        }
    )
    with app.app_context():
        row = get_db().execute("SELECT metric_value,source FROM health_metrics WHERE id=1").fetchone()
        assert row["metric_value"] == "24.2"
        assert row["source"] == "legacy_manual"
        tables = {row["name"] for row in get_db().execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"patient_health_profiles", "report_metadata", "report_results", "health_timeline_events", "health_access_grants"} <= tables


def test_admin_health_access_is_controlled_and_audited(tmp_path):
    app, client = make_client(tmp_path)
    patient_token = api_token(client, "admin-audit-patient@example.com")
    patient_id = user_id(app, "admin-audit-patient@example.com")
    client.put("/api/v1/health-profile", json={"blood_group": "AB+"}, headers=headers(patient_token))
    admin_login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminStrong123", "role": "admin"},
    )
    assert admin_login.status_code == 200
    response = client.get(
        f"/api/v1/health-profile?patient_id={patient_id}",
        headers=headers(admin_login.json["token"]),
    )
    assert response.status_code == 200
    with app.app_context():
        row = get_db().execute(
            "SELECT action,entity_id,actor_id FROM audit_logs WHERE entity_type='patient_health_profile' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        admin_id = get_db().execute("SELECT id FROM users WHERE role='admin'").fetchone()["id"]
        assert row["action"] == "view"
        assert row["entity_id"] == str(patient_id)
        assert row["actor_id"] == admin_id
