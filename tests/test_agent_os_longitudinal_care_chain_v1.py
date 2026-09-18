from datetime import datetime, timedelta, timezone

from tests.test_milestone1 import make_app
from zendoc.agent_handoffs import handoff_for_intent
from zendoc.appointment_continuity import complete_follow_up, sync_provider_appointment_status
from zendoc.care_chain import build_persisted_care_chain
from zendoc.db import get_db, now_iso
from zendoc.health_memory_continuity import determine_next_safe_actions, get_health_memory_provenance_summary
from zendoc.specialist_agent_routes import _confirm_connected_booking
from zendoc.specialist_orchestrator import orchestrate_specialist
from zendoc.specialist_workflow_store import persist_specialist_result


def _seed_connected_chain(app):
    target = datetime.now(timezone.utc).date() + timedelta(days=12)
    weekday = target.weekday()
    stamp = now_iso()
    with app.app_context():
        db = get_db()
        patient_id = db.execute(
            """
            INSERT INTO users (name,email,email_normalized,password_hash,role,active,city,created_at,updated_at)
            VALUES ('Chain Patient','chain-patient@example.test','chain-patient@example.test','unused','patient',1,'Kalyani',?,?)
            """,
            (stamp, stamp),
        ).lastrowid
        provider_id = db.execute(
            """
            INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
            VALUES ('Dr Chain Sen','chain-doctor@example.test','chain-doctor@example.test','unused','doctor',1,?,?)
            """,
            (stamp, stamp),
        ).lastrowid
        profile_id = db.execute(
            """
            INSERT INTO provider_profiles
            (user_id,provider_type,specialty,organization,address,city,state,postal_code,verification_status,created_at,updated_at)
            VALUES (?,'doctor','Cardiology','Chain Heart Clinic','Station Road','Kalyani','West Bengal','741235','verified',?,?)
            """,
            (provider_id, stamp, stamp),
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
        patient = dict(db.execute("SELECT * FROM users WHERE id=?", (patient_id,)).fetchone())
        provider = dict(db.execute("SELECT * FROM users WHERE id=?", (provider_id,)).fetchone())
        return patient, provider, int(profile_id), target


def _persist(actor, command, context=None):
    context = context or {}
    result = orchestrate_specialist(actor, command, context)
    result["handoff_chain"] = handoff_for_intent(result.get("intent"))
    return persist_specialist_result(actor, result, context)


def test_one_request_one_journey_through_provider_evidence_memory_and_follow_up(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENDOC_PLACES_PROVIDER", "none")
    app = make_app(tmp_path)
    patient, provider, profile_id, target = _seed_connected_chain(app)

    with app.app_context():
        discovery = _persist(
            patient,
            "Book appointment with a cardiologist in Kalyani next week",
        )
        assert discovery["assigned_agent"] == "BookingAgent"
        assert discovery["care_journey"]["state"] == "WAITING_USER_SELECTION"
        first_task_id = discovery["workflow_task"]["id"]
        journey_id = discovery["care_journey"]["id"]

        staged = _persist(
            patient,
            "Book appointment with a cardiologist",
            {
                "provider_profile_id": profile_id,
                "date": target.isoformat(),
                "journey_id": journey_id,
                "workflow_task_id": first_task_id,
            },
        )
        assert staged["care_journey"]["id"] == journey_id
        assert staged["care_journey"]["state"] == "APPOINTMENT_STAGED"
        slot = staged["payload"]["available_slots"][0]
        second_task_id = staged["workflow_task"]["id"]

        booking = _confirm_connected_booking(
            patient,
            {
                "provider_profile_id": profile_id,
                "scheduled_for": slot,
                "reason": "Cardiology consultation",
                "journey_id": journey_id,
                "workflow_task_id": second_task_id,
                "user_confirmed": True,
            },
            require_persisted_refs=True,
        )
        appointment_id = booking["appointment_id"]
        assert booking["care_journey"]["id"] == journey_id
        assert booking["care_journey"]["state"] == "WAITING_PROVIDER"
        assert booking["careloop_action_id"]

        db = get_db()
        action = db.execute(
            "SELECT id,journey_id,status,service_ref FROM care_actions WHERE id=?",
            (booking["careloop_action_id"],),
        ).fetchone()
        assert int(action["journey_id"]) == journey_id
        assert action["status"] == "STAGED"
        assert action["service_ref"] == f"zendoc_appointment:{appointment_id}"

        db.execute(
            "UPDATE appointments SET status='confirmed',updated_at=? WHERE id=?",
            (now_iso(), appointment_id),
        )
        db.commit()
        confirmed = sync_provider_appointment_status(provider, appointment_id)
        assert confirmed["care_journey_id"] == journey_id
        assert confirmed["care_journey_state"] == "WAITING_VISIT"
        assert confirmed["next_safe_action"] == "attend_confirmed_appointment"
        assert db.execute("SELECT status FROM care_actions WHERE id=?", (action["id"],)).fetchone()["status"] == "CONFIRMED"

        db.execute(
            "UPDATE appointments SET status='completed',updated_at=? WHERE id=?",
            (now_iso(), appointment_id),
        )
        db.commit()
        completed = sync_provider_appointment_status(provider, appointment_id)
        assert completed["care_journey_id"] == journey_id
        assert completed["care_journey_state"] == "FOLLOW_UP"
        assert completed["care_outcome_id"]
        assert completed["health_memory_outcome_event_id"]
        assert completed["next_safe_action"] == "review_post_visit_follow_up"
        assert db.execute("SELECT status FROM care_actions WHERE id=?", (action["id"],)).fetchone()["status"] == "COMPLETED"

        outcome = db.execute(
            "SELECT status,source_type,source_ref,journey_id FROM care_outcomes WHERE id=?",
            (completed["care_outcome_id"],),
        ).fetchone()
        assert outcome["status"] == "VERIFIED"
        assert outcome["source_type"] == "provider_appointment_status"
        assert outcome["source_ref"] == f"appointment:{appointment_id}:completed"
        assert int(outcome["journey_id"]) == journey_id

        memory = get_health_memory_provenance_summary(patient["id"], actor=patient)
        assert any(
            event["event_type"] == "provider_outcome"
            and event["source_ref"] == f"care_outcome:{completed['care_outcome_id']}"
            for event in memory["by_provenance"]["PROVIDER_RECORDED"]
        )

        safe_actions = determine_next_safe_actions(patient["id"], actor=patient)
        follow_up = next(item for item in safe_actions if item["action_type"] == "REVIEW_POST_VISIT_FOLLOW_UP")
        assert follow_up["journey_id"] == journey_id
        assert follow_up["care_outcome_id"] == completed["care_outcome_id"]
        assert follow_up["provenance"] == "PROVIDER_RECORDED"

        final = complete_follow_up(patient, journey_id, user_confirmed=True)
        assert final["care_journey_state"] == "COMPLETED"
        assert final["follow_up_completion_state"] == "patient_reported"

        states = [
            row["state"]
            for row in db.execute(
                "SELECT state FROM care_journey_events WHERE journey_id=? ORDER BY id",
                (journey_id,),
            ).fetchall()
        ]
        assert states == [
            "CONTEXT_READY",
            "PROVIDER_SEARCH",
            "WAITING_USER_SELECTION",
            "APPOINTMENT_STAGED",
            "WAITING_PROVIDER",
            "WAITING_VISIT",
            "CONSULTATION",
            "FOLLOW_UP",
            "COMPLETED",
        ]

        final_memory = get_health_memory_provenance_summary(patient["id"], actor=patient)
        assert any(event["event_type"] == "provider_outcome" for event in final_memory["by_provenance"]["PROVIDER_RECORDED"])
        assert any(event["event_type"] == "follow_up_completed" for event in final_memory["by_provenance"]["USER_REPORTED"])

        canonical = build_persisted_care_chain(patient, journey_id)
        assert canonical["state"] == "COMPLETED"
        assert canonical["provider_confirmation"]["appointment_status"] == "completed"
        assert canonical["provider_confirmation"]["provider_confirmed"] is True
        assert canonical["outcome"]["verified"] is True
        assert canonical["outcome"]["care_outcome_id"] == completed["care_outcome_id"]
        assert canonical["longitudinal_memory"]["provider_recorded"] is True
        assert canonical["longitudinal_memory"]["provenance"] == "PROVIDER_RECORDED"
        assert canonical["truth"]["model_claim_is_provider_confirmation"] is False
        assert canonical["truth"]["patient_report_is_provider_recorded"] is False
