import pytest

from zendoc.agent_planner import AgentPlan, PlanStep
from zendoc.agent_fleet import list_fleet_agents
from zendoc.agent_registry import list_agents
from zendoc.agent_executor import TOOL_HANDLERS, execute_plan
from zendoc.agentic_integration_mesh import INTEGRATION_POLICIES
from zendoc.agentic_decision_layer import (
    ASK_HUMAN,
    HUMAN_GATE,
    PROCEED,
    decision_layer_manifest,
    evaluate_agent_control,
)
from zendoc.jev_system_one import JevProtocolError, system_one


def _plan(*, agent="ProviderDiscoveryAgent", privacy="INTERNAL", requires_confirmation=False, human_gate=None):
    return AgentPlan(
        plan_id="jev-test",
        command="find hospitals",
        intent="provider_discovery",
        urgency="routine",
        assigned_agent=agent,
        risk_level="read_only",
        steps=(PlanStep(1, "search_healthcare_providers", {}, "search"),),
        requires_confirmation=requires_confirmation,
        privacy_class=privacy,
        human_gate=human_gate,
    )


def _jev_response(choice="proceed", confidence=0.95, needs_human=0.05):
    return {
        "model": "jev-1.13.0",
        "answers": {
            "control_action": {
                "type": "choice",
                "choice": choice,
                "confidence": confidence,
                "probabilities": {
                    "proceed": 0.95 if choice == "proceed" else 0.01,
                    "ask_human": 0.95 if choice == "ask_human" else 0.01,
                    "escalate": 0.95 if choice == "escalate" else 0.01,
                    "stop": 0.95 if choice == "stop" else 0.01,
                },
            },
            "needs_human": {"type": "noul", "noul": needs_human},
        },
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }


def test_decision_layer_defaults_to_deterministic_policy(monkeypatch):
    monkeypatch.delenv("ZENDOC_JEV_ENABLED", raising=False)
    result = evaluate_agent_control(_plan(), "find hospitals", {})
    assert result["action"] == PROCEED
    assert result["allow_reversible_execution"] is True
    assert result["source"] == "deterministic_policy"
    assert result["raw_text_sent"] is False


def test_jev_can_approve_only_already_bounded_reversible_work(monkeypatch):
    monkeypatch.setenv("ZENDOC_JEV_ENABLED", "true")
    monkeypatch.setenv("ZENDOC_JEV_API_KEY", "test-key")
    monkeypatch.setenv("ZENDOC_JEV_CONTEXT_MODE", "metadata_only")

    captured = {}

    def transport(endpoint, payload, headers, timeout):
        captured["endpoint"] = endpoint
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _jev_response()

    result = evaluate_agent_control(_plan(), "private symptom text must not leave", {}, transport=transport)
    assert result["action"] == PROCEED
    assert result["source"] == "jev_system_one"
    assert result["allow_reversible_execution"] is True
    assert result["raw_text_sent"] is False
    assert "minimum_user_text" not in captured["payload"]["state"]
    assert captured["endpoint"].endswith("/v1/systemone")
    assert captured["headers"]["Authorization"] == "Bearer test-key"


def test_low_confidence_jev_narrows_automation(monkeypatch):
    monkeypatch.setenv("ZENDOC_JEV_ENABLED", "true")
    monkeypatch.setenv("ZENDOC_JEV_API_KEY", "test-key")
    monkeypatch.setenv("ZENDOC_JEV_CONFIDENCE_THRESHOLD", "0.85")

    result = evaluate_agent_control(
        _plan(),
        "find hospitals",
        {},
        transport=lambda *_args: _jev_response(confidence=0.60),
    )
    assert result["action"] == ASK_HUMAN
    assert result["allow_reversible_execution"] is False


def test_jev_cannot_waive_deterministic_human_gate(monkeypatch):
    monkeypatch.setenv("ZENDOC_JEV_ENABLED", "true")
    monkeypatch.setenv("ZENDOC_JEV_API_KEY", "test-key")

    result = evaluate_agent_control(
        _plan(
            agent="BookingAgent",
            requires_confirmation=True,
            human_gate="explicit_user_confirmation_before_booking",
        ),
        "book this now",
        {},
        transport=lambda *_args: _jev_response(choice="proceed", confidence=1.0, needs_human=0.0),
    )
    assert result["action"] == HUMAN_GATE
    assert result["allow_reversible_execution"] is True
    assert "cannot waive" in result["reason"].lower()


def test_health_sensitive_text_stays_outside_external_jev_by_default(monkeypatch):
    monkeypatch.setenv("ZENDOC_JEV_ENABLED", "true")
    monkeypatch.setenv("ZENDOC_JEV_API_KEY", "test-key")
    monkeypatch.setenv("ZENDOC_JEV_CONTEXT_MODE", "minimum_text")
    monkeypatch.setenv("ZENDOC_JEV_TRUST_MODE", "external_unverified")

    captured = {}

    def transport(_endpoint, payload, _headers, _timeout):
        captured["state"] = payload["state"]
        return _jev_response()

    result = evaluate_agent_control(
        _plan(privacy="HEALTH_SENSITIVE"),
        "sensitive medical details",
        {},
        transport=transport,
    )
    assert result["raw_text_sent"] is False
    assert "minimum_user_text" not in captured["state"]


def test_private_verified_endpoint_can_receive_minimum_text_when_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("ZENDOC_JEV_ENABLED", "true")
    monkeypatch.setenv("ZENDOC_JEV_BASE_URL", "http://127.0.0.1:8765")
    monkeypatch.delenv("ZENDOC_JEV_API_KEY", raising=False)
    monkeypatch.setenv("ZENDOC_JEV_CONTEXT_MODE", "minimum_text")
    monkeypatch.setenv("ZENDOC_JEV_TRUST_MODE", "private_verified")
    monkeypatch.setenv("ZENDOC_JEV_ALLOW_HEALTH_TEXT", "true")

    captured = {}

    def transport(_endpoint, payload, _headers, _timeout):
        captured["state"] = payload["state"]
        return _jev_response()

    result = evaluate_agent_control(
        _plan(privacy="HEALTH_SENSITIVE"),
        "minimum necessary medical context",
        {},
        transport=transport,
    )
    assert result["raw_text_sent"] is True
    assert captured["state"]["minimum_user_text"] == "minimum necessary medical context"


def test_system_one_rejects_answer_outside_declared_choice(monkeypatch):
    monkeypatch.setenv("ZENDOC_JEV_ENABLED", "true")
    monkeypatch.setenv("ZENDOC_JEV_API_KEY", "test-key")

    questions = {
        "route": {
            "type": "choice",
            "instructions": "Choose route",
            "criteria": {"a": "A", "b": "B"},
        }
    }

    def bad_transport(_endpoint, _payload, _headers, _timeout):
        return {
            "model": "jev-1.13.0",
            "answers": {
                "route": {
                    "type": "choice",
                    "choice": "c",
                    "probabilities": {"c": 1.0},
                    "confidence": 1.0,
                }
            },
        }

    try:
        system_one("state", questions, transport=bad_transport)
    except JevProtocolError:
        pass
    else:
        raise AssertionError("Invalid Jev choice must fail closed.")


def test_decision_manifest_covers_every_registered_agent(monkeypatch):
    monkeypatch.delenv("ZENDOC_JEV_ENABLED", raising=False)
    registered = {agent["identifier"] for agent in list_agents()}
    fleet = {agent["agent_id"] for agent in list_fleet_agents()}
    assert registered == fleet

    manifest = decision_layer_manifest()
    profiled = {agent["agent_id"] for agent in manifest["agents"]}
    assert profiled == registered
    assert all(agent["decision_engine"] == "jev_system_one_optional" for agent in manifest["agents"])
    assert all(agent["mission"] for agent in manifest["agents"])


def test_every_assigned_agent_tool_has_bounded_executor_handler():
    assigned = {
        tool
        for agent in list_agents()
        for tool in agent["allowed_tools"]
    }
    assert assigned
    assert assigned <= set(TOOL_HANDLERS)


def test_planner_routes_remaining_domain_agents_to_real_tools():
    actor = {"id": 501, "role": "patient", "active": 1}

    fitness = __import__("zendoc.agent_planner", fromlist=["build_plan"]).build_plan(
        actor, "show my fitness progress"
    )
    assert fitness.assigned_agent == "FitnessAgent"
    assert [step.tool_name for step in fitness.steps] == ["get_fitness_snapshot"]

    fitness_generate = __import__("zendoc.agent_planner", fromlist=["build_plan"]).build_plan(
        actor, "create workout plan"
    )
    assert fitness_generate.assigned_agent == "FitnessAgent"
    assert [step.tool_name for step in fitness_generate.steps] == [
        "get_fitness_snapshot",
        "generate_fitness_plan",
    ]

    family = __import__("zendoc.agent_planner", fromlist=["build_plan"]).build_plan(
        actor, "show my family care tasks"
    )
    assert family.assigned_agent == "FamilyCareAgent"
    assert family.steps[0].tool_name == "get_family_care_snapshot"

    home = __import__("zendoc.agent_planner", fromlist=["build_plan"]).build_plan(
        actor, "show home health nurse options"
    )
    assert home.assigned_agent == "HomeHealthAgent"
    assert home.steps[0].tool_name == "get_home_health_options"

    transport = __import__("zendoc.agent_planner", fromlist=["build_plan"]).build_plan(
        actor, "show medical transport options"
    )
    assert transport.assigned_agent == "TransportAgent"
    assert transport.steps[0].tool_name == "get_transport_options"


@pytest.mark.parametrize(
    ("agent_id", "tool_name"),
    [
        ("HomeHealthAgent", "confirm_home_health_request"),
        ("TransportAgent", "confirm_transport_request"),
    ],
)
def test_consequential_service_intake_cannot_run_inside_autonomous_plan(agent_id, tool_name):
    plan = AgentPlan(
        plan_id="human-gate-test",
        command="confirm request",
        intent="service_request",
        urgency="routine",
        assigned_agent=agent_id,
        risk_level="consent_required",
        steps=(PlanStep(1, tool_name, {"user_confirmed": True}, "must stay human gated"),),
        requires_confirmation=True,
        privacy_class="HEALTH_SENSITIVE",
        human_gate="explicit_user_confirmation",
    )
    actor = {"id": 501, "role": "patient", "active": 1}
    with pytest.raises(PermissionError, match="explicit human authorization workflow"):
        execute_plan(plan, actor)


def test_external_integration_mesh_has_registered_agent_owners():
    registered = {agent["identifier"] for agent in list_agents()}
    expected = {
        "jev_decisions",
        "payments",
        "external_ekyc",
        "carefin_partner",
        "durable_media",
        "webrtc",
        "affiliate",
        "maps",
        "video_search",
        "external_notifications",
        "database",
    }
    assert set(INTEGRATION_POLICIES) == expected
    for policy in INTEGRATION_POLICIES.values():
        assert policy["owner_agents"]
        assert set(policy["owner_agents"]) <= registered
        assert policy["autonomous_scope"]
        assert policy["fallback_mode"]
        assert policy["human_gate"]


def test_private_verified_still_withholds_health_text_without_second_opt_in(monkeypatch):
    monkeypatch.setenv("ZENDOC_JEV_ENABLED", "true")
    monkeypatch.setenv("ZENDOC_JEV_BASE_URL", "http://127.0.0.1:8765")
    monkeypatch.setenv("ZENDOC_JEV_CONTEXT_MODE", "minimum_text")
    monkeypatch.setenv("ZENDOC_JEV_TRUST_MODE", "private_verified")
    monkeypatch.delenv("ZENDOC_JEV_ALLOW_HEALTH_TEXT", raising=False)

    captured = {}

    def transport(_endpoint, payload, _headers, _timeout):
        captured["state"] = payload["state"]
        return _jev_response()

    result = evaluate_agent_control(
        _plan(privacy="HEALTH_SENSITIVE"),
        "sensitive minimum context",
        {},
        transport=transport,
    )
    assert result["raw_text_sent"] is False
    assert "minimum_user_text" not in captured["state"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda response: response["answers"]["control_action"].update({"confidence": 1.5}),
        lambda response: response["answers"]["control_action"]["probabilities"].update({"proceed": -0.1}),
        lambda response: response["answers"]["control_action"]["probabilities"].pop("stop"),
    ],
)
def test_system_one_rejects_invalid_choice_probability_data(monkeypatch, mutate):
    monkeypatch.setenv("ZENDOC_JEV_ENABLED", "true")
    monkeypatch.setenv("ZENDOC_JEV_API_KEY", "test-key")

    questions = {
        "control_action": {
            "type": "choice",
            "instructions": "Choose bounded control action",
            "criteria": {
                "proceed": "Proceed",
                "ask_human": "Ask a human",
                "escalate": "Escalate",
                "stop": "Stop",
            },
        },
        "needs_human": {
            "type": "noul",
            "instructions": "Does this need a human?",
        },
    }

    response = _jev_response()
    mutate(response)
    with pytest.raises(JevProtocolError):
        system_one("state", questions, transport=lambda *_args: response)
