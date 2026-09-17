from datetime import datetime, timedelta, timezone

import pytest

from tests.test_milestone1 import make_app
from zendoc.appointment_continuity import complete_follow_up, sync_provider_appointment_status
from zendoc.care_action_ledger import create_action
from zendoc.care_journey_store import advance_persisted_journey, create_persisted_journey, get_persisted_journey
from zendoc.db import get_db
from zendoc.health_memory_continuity import determine_next_safe_actions, get_health_memory_provenance_summary


def _seed_users_and_appointment(db, *, suffix="one"):
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    patient_id = db.execute(
        """
        INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
        VALUES (?,?,?,?, 'patient',1,?,?)
        """,
        (f"Patient {suffix}", f"patient-{suffix}@example.test", f"patient-{suffix}@example.test", "unused", stamp, stamp),
    ).lastrowid
    provider_id = db.execute(
        """
        INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
        VALUES (?,?,?,?, 'doctor',1,?,?)
        """,
        (f"Dr Provider {suffix}", f"doctor-{suffix}@example.test", f"doctor-{suffix}@example.test", "unused", stamp, stamp),
    ).lastrowid
    profile_id = db.execute(
        """
        INSERT INTO provider_profiles
        (user_id,provider_type,specialty,organization,address,city,state,postal_code,verification_status,created_at,updated_at)
        VALUES (?,'doctor','Cardiology',?,'Station Road','Kalyani','West Bengal','741235','verified',?,?)
        """,
        (provider_id, f"Heart Clinic {suffix}", stamp, stamp),
    ).lastrowid
    scheduled = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%dT10:00")
    appointment_id = db.execute(
        """
        INSERT INTO appointments
        (patient_id,provider_id,provider_profile_id,provider_name,specialty,scheduled_for,reason,status,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,'requested',?,?)
        """,
        (patient_id, provider_id, profile_id, f"Heart Clinic {suffix}", "Cardiology", scheduled, "Continuity test", stamp, stamp),
    ).lastrowid
    db.commit()
    patient = dict(db.execute("SELECT * FROM users WHERE id=?", (patient_id,)).fetchone())
    provider = dict(db.execute("SELECT * FROM users WHERE id=?", (provider_id,)).fetchone())
    return patient, provider, int(profile_id), int(appointment_id)


def _waiting_provider_journey(patient, appointment_id, provider_profile_id):
    journey = create_persisted_journey(
        patient,
        provenance={"source": "agent_os", "intent": "appointment_booking"},
    )
    steps = (
        ("CONTEXT_READY", "Patient context authorized.", {}),
        ("PROVIDER_SEARCH", "Provider discovery started.", {}),
        ("WAITING_USER_SELECTION", "Provider option selected.", {"required_actor": "patient"}),
        (
            "APPOINTMENT_STAGED",
            "Verified connected slot staged.",
            {"required_actor": "patient", "required_consent": "explicit_booking_confirmation"},
        ),
        (
            "WAITING_PROVIDER",
            "Patient created a real appointment request.",
            {
                "required_actor": "provider",
                "provenance": {
                    "appointment_id": appointment_id,
                    "provider_profile_id": provider_profile_id,
                    "provider_confirmation_state": "requested",
                },
            },
        ),
    )
    for state, reason, extra in steps:
        journey = advance_persisted_journey(
            patient,
            journey["id"],
            target_state=state,
            reason=reason,
            actor_type="user" if state in {"APPOINTMENT_STAGED", "WAITING_PROVIDER"} else "system",
            **extra,
        )

    action = create_action(
        patient,
        journey["id"],
        {
            "action_type": "appointment",
            "title": "Connected appointment",
            "rationale": "Continuity regression",
            "status": "STAGED",
            "human_confirmation_required": True,
            "owner_type": "patient",
            "owner_id": patient["id"],
            "service_ref": f"zendoc_appointment:{appointment_id}",
            "evidence": {"appointment_id": appointment_id},
            "provenance": {
                "source": "agent_os",
                "appointment_id": appointment_id,
                "provider_profile_id": provider_profile_id,
            },
        },
    )
    return journey, action


def test_provider_confirm_complete_memory_next_action_and_follow_up_completion(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient, provider, profile_id, appointment_id = _seed_users_and_appointment(db, suffix="confirm")
        journey, action = _waiting_provider_journey(patient, appointment_id, profile_id)
        assert journey["state"] == "WAITING_PROVIDER"
        assert action["journey_id"] == journey["id"]

        db.execute("UPDATE appointments SET status='confirmed',updated_at=? WHERE id=?", (datetime.now(timezone.utc).isoformat(timespec="seconds"), appointment_id))
        db.commit()
        confirmed = sync_provider_appointment_status(provider, appointment_id)
        assert confirmed["provider_authoritative"] is True
        assert confirmed["provenance_class"] == "PROVIDER_RECORDED"
        assert confirmed["care_journey_state"] == "WAITING_VISIT"
        assert confirmed["next_safe_action"] == "attend_confirmed_appointment"

        memory = get_health_memory_provenance_summary(patient["id"], actor=patient)
        provider_events = memory["by_provenance"]["PROVIDER_RECORDED"]
        assert any(
            event["event_type"] == "appointment_confirmed"
            and event["source_ref"] == f"appointment:{appointment_id}:confirmed"
            for event in provider_events
        )

        # Idempotent reconciliation must not duplicate provider-recorded status events.
        again = sync_provider_appointment_status(provider, appointment_id)
        assert again["care_journey_state"] == "WAITING_VISIT"
        count = db.execute(
            """
            SELECT COUNT(*) c FROM health_timeline_events
            WHERE patient_id=? AND source='PROVIDER_RECORDED'
              AND source_ref=?
            """,
            (patient["id"], f"appointment:{appointment_id}:confirmed"),
        ).fetchone()["c"]
        assert count == 1

        db.execute("UPDATE appointments SET status='completed',updated_at=? WHERE id=?", (datetime.now(timezone.utc).isoformat(timespec="seconds"), appointment_id))
        db.commit()
        completed = sync_provider_appointment_status(provider, appointment_id)
        assert completed["care_journey_state"] == "FOLLOW_UP"
        assert completed["follow_up_ready"] is True
        assert completed["care_outcome_id"]
        assert completed["health_memory_outcome_event_id"]
        assert completed["next_safe_action"] == "review_post_visit_follow_up"

        outcome = db.execute("SELECT * FROM care_outcomes WHERE id=?", (completed["care_outcome_id"],)).fetchone()
        assert outcome["status"] == "VERIFIED"
        assert outcome["outcome_type"] == "appointment_completion"
        assert outcome["source_type"] == "provider_appointment_status"
        assert "No diagnosis" in outcome["summary"]

        refreshed = get_persisted_journey(journey["id"], patient)
        assert refreshed["state"] == "FOLLOW_UP"
        assert refreshed["next_safe_action"] == "review_post_visit_follow_up"
        assert refreshed["provenance"]["provider_confirmation_state"] == "completed_by_provider"
        assert refreshed["provenance"]["care_outcome_id"] == completed["care_outcome_id"]

        memory = get_health_memory_provenance_summary(patient["id"], actor=patient)
        provider_memory = memory["by_provenance"]["PROVIDER_RECORDED"]
        assert any(
            event["event_type"] == "appointment_completed"
            and event["source_ref"] == f"appointment:{appointment_id}:completed"
            for event in provider_memory
        )
        assert any(
            event["event_type"] == "provider_outcome"
            and event["source_ref"] == f"care_outcome:{completed['care_outcome_id']}"
            for event in provider_memory
        )

        next_actions = determine_next_safe_actions(patient["id"], actor=patient)
        follow_up_action = next(item for item in next_actions if item["action_type"] == "REVIEW_POST_VISIT_FOLLOW_UP")
        assert follow_up_action["journey_id"] == journey["id"]
        assert follow_up_action["care_outcome_id"] == completed["care_outcome_id"]
        assert follow_up_action["clinical_directive"] is False

        follow_up = complete_follow_up(patient, journey["id"], user_confirmed=True)
        assert follow_up["care_journey_state"] == "COMPLETED"
        assert follow_up["follow_up_completion_state"] == "patient_reported"
        assert follow_up["care_outcome_id"] == completed["care_outcome_id"]

        final_journey = get_persisted_journey(journey["id"], patient)
        assert final_journey["state"] == "COMPLETED"
        assert final_journey["status"] == "completed"
        assert final_journey["terminal"] is True
        assert final_journey["provenance"]["provider_recorded_outcome_preserved"] is True

        final_memory = get_health_memory_provenance_summary(patient["id"], actor=patient)
        assert any(
            event["event_type"] == "provider_outcome"
            for event in final_memory["by_provenance"]["PROVIDER_RECORDED"]
        )
        assert any(
            event["event_type"] == "follow_up_completed"
            for event in final_memory["by_provenance"]["USER_REPORTED"]
        )

        # Retry is idempotent and does not duplicate the patient completion event.
        repeat = complete_follow_up(patient, journey["id"], user_confirmed=True)
        assert repeat["idempotent"] is True
        follow_count = db.execute(
            "SELECT COUNT(*) c FROM health_timeline_events WHERE patient_id=? AND event_type='follow_up_completed'",
            (patient["id"],),
        ).fetchone()["c"]
        assert follow_count == 1


def test_provider_cancellation_returns_journey_to_provider_search(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient, provider, profile_id, appointment_id = _seed_users_and_appointment(db, suffix="cancel")
        journey, _action = _waiting_provider_journey(patient, appointment_id, profile_id)

        db.execute("UPDATE appointments SET status='cancelled' WHERE id=?", (appointment_id,))
        db.commit()
        result = sync_provider_appointment_status(provider, appointment_id)
        assert result["care_journey_state"] == "PROVIDER_SEARCH"

        refreshed = get_persisted_journey(journey["id"], patient)
        assert refreshed["state"] == "PROVIDER_SEARCH"
        assert refreshed["terminal"] is False
        assert refreshed["next_safe_action"] == "search_verified_and_external_providers"
        assert refreshed["provenance"]["provider_confirmation_state"] == "cancelled_by_provider"


def test_patient_cannot_forge_provider_authoritative_outcome(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient, provider, profile_id, appointment_id = _seed_users_and_appointment(db, suffix="forgery")
        _waiting_provider_journey(patient, appointment_id, profile_id)
        db.execute("UPDATE appointments SET status='confirmed' WHERE id=?", (appointment_id,))
        db.commit()

        with pytest.raises(PermissionError, match="assigned provider or ZENDOC owner"):
            sync_provider_appointment_status(patient, appointment_id)

        count = db.execute(
            "SELECT COUNT(*) c FROM health_timeline_events WHERE patient_id=? AND event_type='appointment_confirmed'",
            (patient["id"],),
        ).fetchone()["c"]
        assert count == 0


def test_follow_up_cannot_complete_without_verified_provider_outcome(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient, _provider, profile_id, appointment_id = _seed_users_and_appointment(db, suffix="no-evidence")
        journey, _action = _waiting_provider_journey(patient, appointment_id, profile_id)
        # Deliberately advance to a user-waiting state but never create provider completion evidence.
        journey = advance_persisted_journey(
            patient,
            journey["id"],
            target_state="WAITING_HUMAN",
            reason="Test-only non-provider waiting state.",
            actor_type="system",
            required_actor="patient",
        )
        assert journey["state"] == "WAITING_HUMAN"
        with pytest.raises(ValueError, match="not waiting for post-visit follow-up"):
            complete_follow_up(patient, journey["id"], user_confirmed=True)
