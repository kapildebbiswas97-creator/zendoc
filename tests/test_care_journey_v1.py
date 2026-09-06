import pytest

from zendoc.care_journey import (
    APPOINTMENT_STAGED,
    BLOCKED,
    COMPLETED,
    CONTEXT_READY,
    FOLLOW_UP,
    NEW,
    PROVIDER_SEARCH,
    WAITING_HUMAN,
    WAITING_USER_SELECTION,
    start_journey,
    transition_journey,
)


def test_care_journey_tracks_history_and_next_safe_action():
    journey = start_journey(patient_id=12, journey_id="journey-1", provenance={"source": "user_request"})
    assert journey.state == NEW

    journey = transition_journey(
        journey,
        target_state=CONTEXT_READY,
        reason="Minimum necessary context authorized.",
        provenance={"consent": "self"},
    )
    journey = transition_journey(
        journey,
        target_state=PROVIDER_SEARCH,
        reason="Care goal requires provider discovery.",
    )
    journey = transition_journey(
        journey,
        target_state=WAITING_USER_SELECTION,
        reason="Provider options found.",
    )

    data = journey.to_dict()
    assert data["state"] == WAITING_USER_SELECTION
    assert len(data["history"]) == 3
    assert data["next_safe_action"] == "ask_user_to_select_provider"
    assert data["provenance"]["consent"] == "self"


def test_waiting_human_requires_named_actor():
    journey = start_journey(patient_id=1, journey_id="journey-human")
    journey = transition_journey(journey, target_state=CONTEXT_READY, reason="Context ready")
    with pytest.raises(ValueError):
        transition_journey(
            journey,
            target_state=WAITING_HUMAN,
            reason="Need approval",
        )


def test_ai_staged_appointment_keeps_patient_gate_explicit():
    journey = start_journey(patient_id=1, journey_id="journey-appt")
    journey = transition_journey(journey, target_state=CONTEXT_READY, reason="Context ready")
    journey = transition_journey(journey, target_state=PROVIDER_SEARCH, reason="Searching")
    journey = transition_journey(journey, target_state=WAITING_USER_SELECTION, reason="Options ready")
    journey = transition_journey(
        journey,
        target_state=APPOINTMENT_STAGED,
        reason="AI prepared a reversible appointment preview",
        actor_type="ai",
    )
    assert journey.required_actor == "patient"
    assert journey.next_safe_action == "ask_user_to_confirm_appointment"


def test_invalid_care_journey_transition_is_blocked():
    journey = start_journey(patient_id=1, journey_id="journey-invalid")
    with pytest.raises(ValueError):
        transition_journey(
            journey,
            target_state=COMPLETED,
            reason="Cannot skip workflow",
        )


def test_blocked_journey_requires_reason_and_is_terminal():
    journey = start_journey(patient_id=1, journey_id="journey-blocked")
    with pytest.raises(ValueError):
        transition_journey(journey, target_state=BLOCKED, reason="Cannot continue")

    blocked = transition_journey(
        journey,
        target_state=BLOCKED,
        reason="Authorization failed",
        blocked_reason="No valid consent for another adult patient",
    )
    assert blocked.to_dict()["terminal"] is True
    with pytest.raises(ValueError):
        transition_journey(blocked, target_state=CONTEXT_READY, reason="Retry")


def test_completed_journey_is_terminal():
    journey = start_journey(patient_id=1, journey_id="journey-complete")
    journey = transition_journey(journey, target_state=CONTEXT_READY, reason="Context ready")
    journey = transition_journey(journey, target_state=PROVIDER_SEARCH, reason="Search")
    journey = transition_journey(journey, target_state=WAITING_USER_SELECTION, reason="Select")
    journey = transition_journey(journey, target_state=APPOINTMENT_STAGED, reason="Staged", required_actor="patient")
    journey = transition_journey(journey, target_state="WAITING_PROVIDER", reason="Patient confirmed; waiting provider")
    journey = transition_journey(journey, target_state="CONSULTATION", reason="Provider accepted")
    journey = transition_journey(journey, target_state=FOLLOW_UP, reason="No prescription or diagnostics required")
    journey = transition_journey(journey, target_state=COMPLETED, reason="Follow-up complete")
    assert journey.state == COMPLETED
    assert journey.to_dict()["terminal"] is True
