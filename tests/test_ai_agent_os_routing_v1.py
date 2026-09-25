from zendoc.intelligence import ZendocIntelligence
from zendoc.intent import IntentRouter, is_multi_step_care_goal


MULTI_STEP_GOALS = (
    "My mother has a prescription; help me organize the safest next step near her home.",
    "Find the right doctor, help me request a consultation, and show what report I should bring.",
    "Check my health records, find the relevant follow-up, and organize the next safe action.",
)


def test_multi_step_detector_routes_care_coordination_examples_to_agent_os():
    router = IntentRouter()
    for message in MULTI_STEP_GOALS:
        assert is_multi_step_care_goal(message) is True
        assert router.detect(message) == "agent_os_request"


def test_multi_step_detector_does_not_overroute_simple_questions():
    router = IntentRouter()
    assert is_multi_step_care_goal("I have a cough. What should I do?") is False
    assert router.detect("I have a cough. What should I do?") == "symptoms"
    assert is_multi_step_care_goal("Find a cardiologist near me") is False
    assert router.detect("Find a cardiologist near me") == "doctor"


def test_zendoc_ai_can_start_bounded_agent_os_workflow(monkeypatch):
    captured = {}

    def fake_run(actor, command, context):
        captured["actor"] = actor
        captured["command"] = command
        captured["context"] = context
        return {
            "intent": "appointment_booking",
            "assigned_agent": "BookingAgent",
            "execution_status": "waiting_human",
            "message": "Booking Agent prepared verified options; no appointment was created.",
            "actions": [{"type": "provider_shortlist", "label": "Review provider options"}],
            "requires_confirmation": True,
            "human_gate": "explicit_user_confirmation_before_booking",
            "decision_control": {"source": "deterministic_policy"},
            "plan": {"urgency": "routine"},
            "workflow_task": {"id": 77, "status": "waiting_human"},
            "care_journey": {"id": 88, "state": "WAITING_USER_SELECTION"},
        }

    monkeypatch.setattr("zendoc.specialist_orchestrator.run_specialist_workflow", fake_run)
    user = {"id": 7, "role": "patient", "active": 1}
    result, _latency = ZendocIntelligence().respond(
        MULTI_STEP_GOALS[1],
        user=user,
        allow_agent_os=True,
    )

    assert captured["actor"] == user
    assert captured["command"] == MULTI_STEP_GOALS[1]
    assert result.intent == "agent_os_request"
    assert result.provider == "specialist_agent_os"
    assert result.model_metadata["agent_os"]["assigned_agent"] == "BookingAgent"
    assert result.model_metadata["agent_os"]["workflow_task_id"] == 77
    assert result.model_metadata["agent_os"]["requires_confirmation"] is True
    assert "workflow #77" in result.message.lower()


def test_agent_os_execution_is_opt_in_to_zendoc_ai_mode(monkeypatch):
    def must_not_run(*_args, **_kwargs):
        raise AssertionError("Agent OS must not execute when the caller did not opt in.")

    monkeypatch.setattr("zendoc.specialist_orchestrator.run_specialist_workflow", must_not_run)
    result, _latency = ZendocIntelligence().respond(
        MULTI_STEP_GOALS[2],
        user={"id": 7, "role": "patient", "active": 1},
        allow_agent_os=False,
    )

    assert result.intent == "agent_os_request"
    assert result.provider == "agent_os_handoff"
    assert result.success is True


def test_emergency_safety_precedes_multi_step_agent_routing(monkeypatch):
    def must_not_run(*_args, **_kwargs):
        raise AssertionError("Agent OS must never run before the emergency safety path.")

    monkeypatch.setattr("zendoc.specialist_orchestrator.run_specialist_workflow", must_not_run)
    result, _latency = ZendocIntelligence().respond(
        "I have chest pain and shortness of breath; find a doctor and schedule a consultation.",
        user={"id": 7, "role": "patient", "active": 1},
        allow_agent_os=True,
    )

    assert result.emergency is True
    assert result.intent == "emergency"
    assert result.provider == "deterministic_safety"


def test_multi_step_consultation_request_uses_booking_agent():
    from zendoc.agent_planner import build_plan

    plan = build_plan(
        {"id": 7, "role": "patient", "active": 1},
        MULTI_STEP_GOALS[1],
    )
    assert plan.intent == "appointment_booking"
    assert plan.assigned_agent == "BookingAgent"
    assert plan.requires_confirmation is True
    assert plan.human_gate == "explicit_user_confirmation_before_booking"


def test_multi_step_records_goal_starts_with_authorized_health_memory_reads():
    from zendoc.agent_planner import build_plan

    plan = build_plan(
        {"id": 7, "role": "patient", "active": 1},
        MULTI_STEP_GOALS[2],
    )
    assert plan.intent == "health_records"
    assert plan.assigned_agent == "HealthMemoryAgent"
    assert [step.tool_name for step in plan.steps] == [
        "get_health_memory_context",
        "search_health_memory_evidence",
    ]
