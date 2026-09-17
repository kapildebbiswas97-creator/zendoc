from datetime import datetime, timedelta, timezone

from tests.test_milestone1 import make_app
from zendoc.db import get_db
from zendoc.specialist_orchestrator import orchestrate_specialist


def _future_weekday(days_ahead=11):
    target = datetime.now(timezone.utc).date() + timedelta(days=days_ahead)
    return target, target.weekday()


def _seed_booking_provider(app):
    target, weekday = _future_weekday()
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with app.app_context():
        db = get_db()
        patient_id = db.execute(
            """
            INSERT INTO users (name,email,email_normalized,password_hash,role,active,city,created_at,updated_at)
            VALUES ('Agent OS Patient','agent-os-patient@example.test','agent-os-patient@example.test','unused','patient',1,'Kalyani',?,?)
            """,
            (stamp, stamp),
        ).lastrowid
        doctor_id = db.execute(
            """
            INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
            VALUES ('Dr Agent Sen','agent-os-doctor@example.test','agent-os-doctor@example.test','unused','doctor',1,?,?)
            """,
            (stamp, stamp),
        ).lastrowid
        profile_id = db.execute(
            """
            INSERT INTO provider_profiles
            (user_id,provider_type,specialty,organization,address,city,state,postal_code,verification_status,created_at,updated_at)
            VALUES (?,'doctor','Cardiology','Agent Heart Clinic','Station Road','Kalyani','West Bengal','741235','verified',?,?)
            """,
            (doctor_id, stamp, stamp),
        ).lastrowid
        db.execute(
            """
            INSERT INTO provider_schedules
            (provider_profile_id,weekday,start_time,end_time,slot_minutes,active,
             organization_id,organization_location_id,created_at,updated_at)
            VALUES (?,?,?,?,30,1,NULL,NULL,?,?)
            """,
            (profile_id, weekday, "09:00", "10:00", stamp, stamp),
        )
        db.commit()
        actor = dict(db.execute("SELECT * FROM users WHERE id=?", (patient_id,)).fetchone())
    return actor, profile_id, target


def test_agent_os_route_is_registered(tmp_path):
    app = make_app(tmp_path)
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/agent-os" in rules
    assert "/api/v1/agent/orchestrate" in rules
    assert "/api/v1/agent/autonomy" in rules


def test_booking_agent_runs_discovery_before_confirmation(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENDOC_PLACES_PROVIDER", "none")
    app = make_app(tmp_path)
    actor, profile_id, target = _seed_booking_provider(app)

    with app.app_context():
        result = orchestrate_specialist(actor, "Book appointment with a cardiologist in Kalyani next week")
        assert result["assigned_agent"] == "BookingAgent"
        assert result["intent"] == "appointment_booking"
        assert result["requires_confirmation"] is True
        assert result["execution_status"] == "waiting_human"
        assert result["payload"] is not None
        ids = {int(item["id"]) for item in result["payload"].get("registered_providers", [])}
        assert int(profile_id) in ids

        count = db_count = get_db().execute(
            "SELECT COUNT(*) AS c FROM appointments WHERE patient_id=?", (actor["id"],)
        ).fetchone()["c"]
        assert count == 0
        assert db_count == 0


def test_booking_agent_changes_date_and_reads_real_slots_without_booking(tmp_path):
    app = make_app(tmp_path)
    actor, profile_id, target = _seed_booking_provider(app)

    with app.app_context():
        result = orchestrate_specialist(
            actor,
            "Book appointment with a cardiologist",
            {"provider_profile_id": profile_id, "date": target.isoformat()},
        )
        assert result["assigned_agent"] == "BookingAgent"
        assert result["execution_status"] == "waiting_human"
        payload = result["payload"]
        assert payload["bookable_in_zendoc"] is True
        assert payload["confirmation_required"] is True
        assert payload["available_slots"]
        assert payload["available_slots"][0].startswith(target.isoformat())
        assert "No appointment has been created" in payload["truth_notice"]

        count = get_db().execute(
            "SELECT COUNT(*) AS c FROM appointments WHERE patient_id=?", (actor["id"],)
        ).fetchone()["c"]
        assert count == 0


def test_commerce_agent_keeps_external_handoffs_truthful(tmp_path):
    app = make_app(tmp_path)
    actor = {"id": 101, "role": "patient", "active": 1, "city": "Kalyani"}
    with app.app_context():
        result = orchestrate_specialist(actor, "Find fitness equipment for home workouts")
    assert result["assigned_agent"] == "CommerceAgent"
    payload = result["payload"]
    assert payload["external_only"] is True
    assert payload["price_verified"] is False
    assert payload["availability_verified"] is False
    assert payload["affiliate_relationship_configured"] is False
    assert payload["payment_execution_enabled"] is False
    assert result["truth"]["payment_executed"] is False


def test_fitness_and_model_improvement_do_not_fall_back_to_generic_agent(tmp_path):
    app = make_app(tmp_path)
    patient = {"id": 201, "role": "patient", "active": 1}
    with app.app_context():
        fitness = orchestrate_specialist(patient, "Create a fitness workout plan")
        assert fitness["assigned_agent"] == "FitnessAgent"
        assert fitness["intent"] == "fitness"
        assert "Fitness Agent" in fitness["message"]

        denied = False
        try:
            orchestrate_specialist(patient, "Improve model and run offline eval")
        except PermissionError:
            denied = True
        assert denied is True
