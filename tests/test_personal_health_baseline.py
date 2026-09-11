from datetime import datetime, timedelta, timezone

from zendoc.db import get_db
from tests.test_milestone1 import login_web, make_client, register_web


def _patient_id(app, email):
    with app.app_context():
        return int(get_db().execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()["id"])


def _insert_metric(app, patient_id, *, value, days_ago, unit="kg", secondary=None, source="manual"):
    recorded_at = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(timespec="seconds")
    display = f"{value}/{secondary}" if secondary is not None else str(value)
    with app.app_context():
        get_db().execute(
            """
            INSERT INTO health_metrics
            (user_id,metric_type,metric_value,unit,recorded_at,numeric_value,secondary_value,source,notes)
            VALUES (?,?,?,?,?,?,?,?,NULL)
            """,
            (patient_id, "weight", display, unit, recorded_at, float(value), secondary, source),
        )
        get_db().commit()


def test_personal_baseline_compares_recent_values_to_prior_same_unit_history(tmp_path):
    app, client = make_client(tmp_path)
    email = "baseline-owner@example.com"
    register_web(client, "patient", email)
    patient_id = _patient_id(app, email)

    _insert_metric(app, patient_id, value=70, days_ago=30)
    _insert_metric(app, patient_id, value=71, days_ago=25)
    _insert_metric(app, patient_id, value=69, days_ago=20)
    _insert_metric(app, patient_id, value=200, days_ago=4, unit="lb")
    _insert_metric(app, patient_id, value=73, days_ago=3)
    _insert_metric(app, patient_id, value=74, days_ago=1)

    login_web(client, "patient", email)
    response = client.get("/api/v1/health-baseline?metric_type=weight&baseline_days=60&recent_days=7")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["patient_id"] == patient_id
    assert payload["status"] == "ABOVE_PERSONAL_BASELINE"
    assert payload["unit"] == "kg"
    assert payload["baseline_window"]["point_count"] == 3
    assert payload["recent_window"]["point_count"] == 2
    assert payload["provenance"]["excluded_other_unit_points"] == 1
    assert payload["primary"]["baseline_mean"] == 70.0
    assert payload["primary"]["recent_mean"] == 73.5
    assert payload["medical_interpretation"] is False
    assert payload["emergency_detector"] is False


def test_personal_baseline_fails_closed_when_prior_history_is_insufficient(tmp_path):
    app, client = make_client(tmp_path)
    email = "baseline-small@example.com"
    register_web(client, "patient", email)
    patient_id = _patient_id(app, email)

    _insert_metric(app, patient_id, value=60, days_ago=20)
    _insert_metric(app, patient_id, value=61, days_ago=15)
    _insert_metric(app, patient_id, value=62, days_ago=1)

    login_web(client, "patient", email)
    response = client.get("/api/v1/health-baseline?metric_type=weight&baseline_days=30&recent_days=7")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "INSUFFICIENT_BASELINE"
    assert payload["primary"]["baseline_mean"] is None
    assert payload["primary"]["recent_mean"] == 62.0


def test_personal_baseline_blocks_cross_patient_idor(tmp_path):
    app, client = make_client(tmp_path)
    first_email = "baseline-first@example.com"
    second_email = "baseline-second@example.com"
    register_web(client, "patient", first_email)
    client.get("/logout")
    register_web(client, "patient", second_email)
    second_id = _patient_id(app, second_email)

    client.get("/logout")
    login_web(client, "patient", first_email)
    response = client.get(f"/api/v1/health-baseline?metric_type=weight&patient_id={second_id}")

    assert response.status_code == 403
    assert "cannot access another patient" in response.get_json()["error"]["message"].lower()


def test_personal_baseline_validates_windows_and_authentication(tmp_path):
    _app, client = make_client(tmp_path)

    unauthenticated = client.get("/api/v1/health-baseline?metric_type=weight")
    assert unauthenticated.status_code in {401, 403}

    register_web(client, "patient", "baseline-window@example.com")
    login_web(client, "patient", "baseline-window@example.com")
    invalid = client.get("/api/v1/health-baseline?metric_type=weight&baseline_days=30&recent_days=30")
    assert invalid.status_code == 400
    assert "smaller" in invalid.get_json()["error"]["message"].lower()
