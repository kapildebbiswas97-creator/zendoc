import json
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_milestone1 import make_app
from zendoc.appointment_continuity import sync_provider_appointment_status
from tests.test_specialist_agent_os_v1 import _seed_booking_provider
from zendoc.agent_handoffs import handoff_for_intent
from zendoc.db import get_db, now_iso
from zendoc.provider_service import book_provider_slot
from zendoc.specialist_orchestrator import orchestrate_specialist
from zendoc.specialist_workflow_store import (
    mark_booking_requested,
    persist_specialist_result,
    validate_booking_confirmation,
)


def _attach_handoff(result):
    result["handoff_chain"] = handoff_for_intent(result["intent"])
    return result


def _seed_patient(app, email="workflow-patient@example.test"):
    with app.app_context():
        db = get_db()
        stamp = now_iso()
        patient_id = db.execute(
            """
            INSERT INTO users
            (name,email,email_normalized,password_hash,role,active,city,created_at,updated_at)
            VALUES ('Workflow Patient',?,?, 'unused','patient',1,'Kalyani',?,?)
            """,
            (email, email, stamp, stamp),
        ).lastrowid
        db.commit()
        return dict(db.execute("SELECT * FROM users WHERE id=?", (patient_id,)).fetchone())


def test_general_specialist_workflow_persists_without_raw_prompt_or_payload(tmp_path):
    app = make_app(tmp_path)
    actor = _seed_patient(app)

    with app.app_context():
        result = _attach_handoff(
            orchestrate_specialist(actor, "Find fitness equipment for home workouts")
        )
        persisted = persist_specialist_result(actor, result, {"category": "fitness"})
        task_id = persisted["workflow_task"]["id"]
        task = get_db().execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
        metadata = json.loads(task["metadata_json"])

        assert task["task_type"] == "specialist_workflow:health_commerce"
        assert task["assigned_agent"] == "CommerceAgent"
        assert task["status"] == "completed"
        assert metadata["raw_prompt_stored"] is False
        assert metadata["tool_payload_stored"] is False
        assert metadata["context_keys"] == ["category"]
        assert "Find fitness equipment" not in task["metadata_json"]
        assert "results" not in metadata
        assert persisted["truth"]["payment_executed"] is False


def test_booking_workflow_persists_and_advances_only_to_human_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENDOC_PLACES_PROVIDER", "none")
    app = make_app(tmp_path)
    actor, profile_id, target = _seed_booking_provider(app)

    with app.app_context():
        discovery = _attach_handoff(
            orchestrate_specialist(actor, "Book appointment with a cardiologist in Kalyani next week")
        )
        discovery = persist_specialist_result(actor, discovery, {})
        assert discovery["workflow_task"]["status"] == "waiting_human"
        assert discovery["care_journey"]["state"] == "WAITING_USER_SELECTION"
        first_task_id = discovery["workflow_task"]["id"]
        journey_id = discovery["care_journey"]["id"]

        slot_result = _attach_handoff(
            orchestrate_specialist(
                actor,
                "Book appointment with a cardiologist",
                {"provider_profile_id": profile_id, "date": target.isoformat()},
            )
        )
        slot_result = persist_specialist_result(
            actor,
            slot_result,
            {
                "provider_profile_id": profile_id,
                "date": target.isoformat(),
                "journey_id": journey_id,
                "workflow_task_id": first_task_id,
            },
        )

        assert slot_result["workflow_task"]["status"] == "waiting_human"
        assert slot_result["care_journey"]["state"] == "APPOINTMENT_STAGED"
        assert slot_result["care_journey"]["required_actor"] == "patient"
        assert slot_result["care_journey"]["required_consent"] == "explicit_booking_confirmation"
        assert get_db().execute(
            "SELECT status FROM agent_tasks WHERE id=?", (first_task_id,)
        ).fetchone()["status"] == "completed"

        count = get_db().execute(
            "SELECT COUNT(*) AS c FROM appointments WHERE patient_id=?", (actor["id"],)
        ).fetchone()["c"]
        assert count == 0


def test_confirmed_booking_waits_for_provider_then_closes_from_provider_truth(tmp_path):
    app = make_app(tmp_path)
    actor, profile_id, target = _seed_booking_provider(app)

    with app.app_context():
        discovery = _attach_handoff(
            orchestrate_specialist(actor, "Book appointment with a cardiologist in Kalyani")
        )
        discovery = persist_specialist_result(actor, discovery, {})
        journey_id = discovery["care_journey"]["id"]

        slot_result = _attach_handoff(
            orchestrate_specialist(
                actor,
                "Book appointment with a cardiologist",
                {"provider_profile_id": profile_id, "date": target.isoformat()},
            )
        )
        slot_result = persist_specialist_result(
            actor,
            slot_result,
            {
                "provider_profile_id": profile_id,
                "date": target.isoformat(),
                "journey_id": journey_id,
                "workflow_task_id": discovery["workflow_task"]["id"],
            },
        )
        task_id = slot_result["workflow_task"]["id"]
        slot = slot_result["payload"]["available_slots"][0]

        refs = validate_booking_confirmation(
            actor,
            journey_id=journey_id,
            workflow_task_id=task_id,
        )
        assert refs["journey"]["state"] == "APPOINTMENT_STAGED"
        assert refs["task"]["status"] == "waiting_human"

        appointment_id = book_provider_slot(
            actor,
            profile_id,
            slot,
            "Cardiology consultation",
        )
        persisted = mark_booking_requested(
            actor,
            appointment_id=appointment_id,
            provider_profile_id=profile_id,
            journey_id=journey_id,
            workflow_task_id=task_id,
        )

        assert persisted["workflow_task"]["status"] == "waiting_provider"
        assert persisted["care_journey"]["state"] == "WAITING_PROVIDER"
        assert persisted["care_journey"]["required_actor"] == "provider"
        appointment = get_db().execute(
            "SELECT status FROM appointments WHERE id=?", (appointment_id,)
        ).fetchone()
        assert appointment["status"] == "requested"

        provider = get_db().execute(
            """
            SELECT u.* FROM users u
            JOIN provider_profiles p ON p.user_id=u.id
            WHERE p.id=?
            """,
            (profile_id,),
        ).fetchone()
        get_db().execute(
            "UPDATE appointments SET status='confirmed',updated_at=? WHERE id=?",
            (now_iso(), appointment_id),
        )
        get_db().commit()
        synced = sync_provider_appointment_status(dict(provider), appointment_id)
        assert synced["workflow_task_id"] == task_id
        assert synced["workflow_task_status"] == "completed"
        assert get_db().execute(
            "SELECT status FROM agent_tasks WHERE id=?", (task_id,)
        ).fetchone()["status"] == "completed"


def test_cross_patient_cannot_reuse_booking_journey_or_task(tmp_path):
    app = make_app(tmp_path)
    actor, profile_id, target = _seed_booking_provider(app)
    other = _seed_patient(app, "workflow-other@example.test")

    with app.app_context():
        result = _attach_handoff(
            orchestrate_specialist(
                actor,
                "Book appointment with a cardiologist",
                {"provider_profile_id": profile_id, "date": target.isoformat()},
            )
        )
        result = persist_specialist_result(
            actor,
            result,
            {"provider_profile_id": profile_id, "date": target.isoformat()},
        )

        with pytest.raises(PermissionError):
            validate_booking_confirmation(
                other,
                journey_id=result["care_journey"]["id"],
                workflow_task_id=result["workflow_task"]["id"],
            )


def test_empty_connected_slot_result_does_not_stage_booking(tmp_path):
    app = make_app(tmp_path)
    actor, profile_id, _target = _seed_booking_provider(app)
    seeded_weekday = (datetime.now(timezone.utc).date() + timedelta(days=11)).weekday()
    no_schedule_date = datetime.now(timezone.utc).date() + timedelta(days=9)
    while no_schedule_date.weekday() == seeded_weekday:
        no_schedule_date += timedelta(days=1)

    with app.app_context():
        result = _attach_handoff(
            orchestrate_specialist(
                actor,
                "Book appointment with a cardiologist",
                {"provider_profile_id": profile_id, "date": no_schedule_date.isoformat()},
            )
        )
        assert result["payload"]["available_slots"] == []
        result = persist_specialist_result(
            actor,
            result,
            {"provider_profile_id": profile_id, "date": no_schedule_date.isoformat()},
        )
        assert result["care_journey"]["state"] == "WAITING_INFORMATION"
        assert result["care_journey"]["state"] != "APPOINTMENT_STAGED"
