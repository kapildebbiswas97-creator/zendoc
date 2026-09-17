from datetime import datetime, timedelta, timezone

import pytest

from tests.test_milestone1 import make_app
from zendoc.agent_handoffs import handoff_for_intent
from zendoc.appointment_continuity import complete_follow_up, sync_provider_appointment_status
from zendoc.care_continuity import CANONICAL_CHAIN, get_care_continuity_snapshot
from zendoc.db import get_db, now_iso
from zendoc.specialist_agent_routes import _confirm_connected_booking
from zendoc.specialist_orchestrator import orchestrate_specialist
from zendoc.specialist_workflow_store import persist_specialist_result


def _seed(app):
    target = datetime.now(timezone.utc).date() + timedelta(days=15)
    stamp = now_iso()
    with app.app_context():
        db = get_db()
        patient_id = db.execute(
            """
            INSERT INTO users (name,email,email_normalized,password_hash,role,active,city,created_at,updated_at)
            VALUES ('Continuity Patient','continuity-patient@example.test','continuity-patient@example.test','unused','patient',1,'Kalyani',?,?)
            """,
            (stamp, stamp),
        ).lastrowid
        other_patient_id = db.execute(
            """
            INSERT INTO users (name,email,email_normalized,password_hash,role,active,city,created_at,updated_at)
            VALUES ('Other Patient','other-continuity@example.test','other-continuity@example.test','unused','patient',1,'Kalyani',?,?)
            """,
            (stamp, stamp),
        ).lastrowid
        provider_id = db.execute(
            """
            INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
            VALUES ('Dr Continuity','continuity-doctor@example.test','continuity-doctor@example.test','unused','doctor',1,?,?)
            """,
            (stamp, stamp),
        ).lastrowid
        profile_id = db.execute(
            """
            INSERT INTO provider_profiles
            (user_id,provider_type,specialty,organization,address,city,state,postal_code,verification_status,created_at,updated_at)
            VALUES (?,'doctor','Cardiology','Continuity Heart Clinic','Station Road','Kalyani','West Bengal','741235','verified',?,?)
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
            (profile_id, target.weekday(), '09:00', '10:00', stamp, stamp),
        )
        db.commit()
        patient = dict(db.execute("SELECT * FROM users WHERE id=?", (patient_id,)).fetchone())
        other_patient = dict(db.execute("SELECT * FROM users WHERE id=?", (other_patient_id,)).fetchone())
        provider = dict(db.execute("SELECT * FROM users WHERE id=?", (provider_id,)).fetchone())
    return patient, other_patient, provider, int(profile_id), target


def _persist(actor, command, context=None):
    context = context or {}
    result = orchestrate_specialist(actor, command, context)
    result["handoff_chain"] = handoff_for_intent(result.get("intent"))
    return persist_specialist_result(actor, result, context)


def _book_to_waiting_provider(patient, profile_id, target):
    discovery = _persist(patient, "Book appointment with a cardiologist in Kalyani next week")
    journey_id = discovery["care_journey"]["id"]
    staged = _persist(
        patient,
        "Book appointment with a cardiologist",
        {
            "provider_profile_id": profile_id,
            "date": target.isoformat(),
            "journey_id": journey_id,
            "workflow_task_id": discovery["workflow_task"]["id"],
        },
    )
    booking = _confirm_connected_booking(
        patient,
        {
            "provider_profile_id": profile_id,
            "scheduled_for": staged["payload"]["available_slots"][0],
            "reason": "Cardiology consultation",
            "journey_id": journey_id,
            "workflow_task_id": staged["workflow_task"]["id"],
            "user_confirmed": True,
        },
        require_persisted_refs=True,
    )
    return journey_id, booking["appointment_id"]


def test_snapshot_never_invents_provider_evidence_before_provider_action(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENDOC_PLACES_PROVIDER", "none")
    app = make_app(tmp_path)
    patient, _other, _provider, profile_id, target = _seed(app)

    with app.app_context():
        journey_id, appointment_id = _book_to_waiting_provider(patient, profile_id, target)
        snapshot = get_care_continuity_snapshot(patient, journey_id)

        assert snapshot["canonical_chain"] == CANONICAL_CHAIN
        assert snapshot["state"] == "WAITING_PROVIDER"
        assert snapshot["appointment"]["id"] == appointment_id
        assert snapshot["appointment"]["status"] == "requested"
        assert snapshot["careloop"]["status"] == "STAGED"
        assert snapshot["evidence"]["provider_confirmed"] is False
        assert snapshot["evidence"]["verified_outcome_present"] is False
        assert snapshot["evidence"]["provider_recorded_health_memory"] is False
        assert snapshot["available_next_safe_actions"] == []
        assert snapshot["truth"]["missing_evidence_becomes_verified"] is False
        assert snapshot["truth"]["clinical_findings_inferred_from_completion"] is False


def test_snapshot_tracks_provider_evidence_memory_next_action_and_completion(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENDOC_PLACES_PROVIDER", "none")
    app = make_app(tmp_path)
    patient, _other, provider, profile_id, target = _seed(app)

    with app.app_context():
        journey_id, appointment_id = _book_to_waiting_provider(patient, profile_id, target)
        db = get_db()

        db.execute("UPDATE appointments SET status='confirmed',updated_at=? WHERE id=?", (now_iso(), appointment_id))
        db.commit()
        sync_provider_appointment_status(provider, appointment_id)
        confirmed = get_care_continuity_snapshot(patient, journey_id)
        assert confirmed["state"] == "WAITING_VISIT"
        assert confirmed["appointment"]["status"] == "confirmed"
        assert confirmed["careloop"]["status"] == "CONFIRMED"
        assert confirmed["evidence"]["provider_confirmed"] is True
        assert confirmed["evidence"]["verified_outcome_present"] is False

        db.execute("UPDATE appointments SET status='completed',updated_at=? WHERE id=?", (now_iso(), appointment_id))
        db.commit()
        sync_provider_appointment_status(provider, appointment_id)
        follow_up = get_care_continuity_snapshot(patient, journey_id)
        assert follow_up["state"] == "FOLLOW_UP"
        assert follow_up["appointment"]["status"] == "completed"
        assert follow_up["careloop"]["status"] == "COMPLETED"
        assert follow_up["evidence"]["visit_completed_by_provider_state"] is True
        assert follow_up["evidence"]["verified_outcome_present"] is True
        assert follow_up["evidence"]["provider_recorded_health_memory"] is True
        assert follow_up["evidence"]["health_memory_provenance"] == "PROVIDER_RECORDED"
        assert any(
            action["action_type"] == "REVIEW_POST_VISIT_FOLLOW_UP"
            for action in follow_up["available_next_safe_actions"]
        )

        complete_follow_up(patient, journey_id, user_confirmed=True)
        completed = get_care_continuity_snapshot(patient, journey_id)
        assert completed["state"] == "COMPLETED"
        assert completed["terminal"] is True
        assert completed["next_safe_action"] == "none"
        assert completed["available_next_safe_actions"] == []
        assert completed["evidence"]["provider_recorded_health_memory"] is True


def test_snapshot_rejects_cross_patient_access_before_linked_records_are_read(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENDOC_PLACES_PROVIDER", "none")
    app = make_app(tmp_path)
    patient, other_patient, _provider, profile_id, target = _seed(app)

    with app.app_context():
        journey_id, _appointment_id = _book_to_waiting_provider(patient, profile_id, target)
        with pytest.raises(PermissionError):
            get_care_continuity_snapshot(other_patient, journey_id)
