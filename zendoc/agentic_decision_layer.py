"""System One control layer for the ZENDOC specialist-agent fleet.

Deterministic policy remains authoritative. Jev may make fast typed judgments
about whether already-authorized reversible work should proceed, pause for a
human, escalate, or stop. It can never turn a forbidden or confirmation-gated
action into an autonomous action.
"""
from __future__ import annotations

import os

from .agent_fleet import get_fleet_agent, list_fleet_agents
from .jev_system_one import JevError, jev_runtime_status, system_one


PROCEED = "PROCEED"
HUMAN_GATE = "HUMAN_GATE"
ASK_HUMAN = "ASK_HUMAN"
ESCALATE = "ESCALATE"
STOP = "STOP"


def _privacy_allows_text(privacy_class: str) -> bool:
    mode = str(os.environ.get("ZENDOC_JEV_CONTEXT_MODE") or "metadata_only").strip().lower()
    trust = str(os.environ.get("ZENDOC_JEV_TRUST_MODE") or "external_unverified").strip().lower()
    privacy = str(privacy_class or "").upper()
    if mode != "minimum_text":
        return False
    if trust == "private_verified":
        if privacy in {"HEALTH_SENSITIVE", "HIGH_RISK"}:
            return str(os.environ.get("ZENDOC_JEV_ALLOW_HEALTH_TEXT") or "").strip().lower() in {
                "1", "true", "yes", "on"
            }
        return True
    return privacy in {"PUBLIC", "INTERNAL"}


def _decision_state(plan, command_text: str, context: dict | None) -> tuple[dict, bool]:
    agent = get_fleet_agent(plan.assigned_agent) or {}
    state = {
        "agent_id": plan.assigned_agent,
        "mission": agent.get("mission", ""),
        "automation_level": agent.get("automation_level", ""),
        "intent": plan.intent,
        "urgency": plan.urgency,
        "risk_level": plan.risk_level,
        "privacy_class": plan.privacy_class,
        "requires_confirmation": bool(plan.requires_confirmation),
        "human_gate": plan.human_gate,
        "planned_tools": [step.tool_name for step in plan.steps],
        "human_gates": agent.get("human_gates", []),
        "forbidden_actions": agent.get("forbidden", []),
        "context_keys": sorted(str(key) for key in (context or {}).keys()),
    }
    raw_text_sent = False
    if _privacy_allows_text(plan.privacy_class):
        state["minimum_user_text"] = str(command_text or "")[:1200]
        raw_text_sent = True
    return state, raw_text_sent


def _questions_for(plan) -> dict:
    agent = get_fleet_agent(plan.assigned_agent) or {}
    mission = str(agent.get("mission") or plan.assigned_agent)
    gates = ", ".join(agent.get("human_gates") or []) or "none"
    forbidden = ", ".join(agent.get("forbidden") or []) or "none"
    return {
        "control_action": {
            "type": "choice",
            "instructions": (
                f"For the {plan.assigned_agent}, whose mission is: {mission}. "
                "Choose the safest control action for the already policy-bounded reversible work. "
                f"Known human gates: {gates}. Forbidden actions: {forbidden}. "
                "Never choose proceed to bypass a stated gate or forbidden action."
            ),
            "criteria": {
                "proceed": "Run only the already-authorized reversible/read-only/staging steps.",
                "ask_human": "Pause because the state is ambiguous or needs fresh user input.",
                "escalate": "Escalate to a qualified human, owner, or clinician because routine automation is insufficient.",
                "stop": "Stop because the workflow appears unsafe, contradictory, or outside this agent mission.",
            },
        },
        "needs_human": {
            "type": "noul",
            "instructions": (
                "Does this workflow need a human before any additional reversible agent step can safely run? "
                "Answer yes for ambiguity, authorization uncertainty, clinical or financial consequence, or policy conflict."
            ),
            "criteria": {
                "true": "A person should review before more agent work runs.",
                "false": "Already-authorized reversible work can continue automatically.",
            },
        },
    }


def deterministic_agent_profile(agent_id: str) -> dict:
    agent = get_fleet_agent(agent_id)
    if not agent:
        return {}
    return {
        "agent_id": agent["agent_id"],
        "mission": agent["mission"],
        "automation_level": agent["automation_level"],
        "preferred_model_tasks": agent["preferred_model_tasks"],
        "deterministic_first": agent["deterministic_first"],
        "human_gates": agent["human_gates"],
        "forbidden": agent["forbidden"],
        "decision_engine": "jev_system_one_optional",
    }


def decision_layer_manifest() -> dict:
    status = jev_runtime_status()
    return {
        "jev": status,
        "agents": [deterministic_agent_profile(item["agent_id"]) for item in list_fleet_agents()],
        "principle": (
            "Jev selects among bounded control outcomes; deterministic ZENDOC policy and tool permissions remain authoritative."
        ),
        "allowed_control_actions": [PROCEED, ASK_HUMAN, ESCALATE, STOP],
        "hard_gate_action": HUMAN_GATE,
    }


def evaluate_agent_control(plan, command_text: str, context=None, *, transport=None) -> dict:
    """Return a control decision that can only preserve or reduce autonomy."""
    state, raw_text_sent = _decision_state(plan, command_text, context)
    hard_gate = bool(plan.requires_confirmation or plan.human_gate)
    status = jev_runtime_status()

    if not status["configured"]:
        return {
            "action": HUMAN_GATE if hard_gate else PROCEED,
            "allow_reversible_execution": True,
            "source": "deterministic_policy",
            "jev_status": status["status"],
            "confidence": 1.0,
            "raw_text_sent": False,
            "reason": (
                "Deterministic human gate preserved."
                if hard_gate
                else "Jev is not configured; existing deterministic bounded policy remains in control."
            ),
        }

    try:
        response = system_one(state, _questions_for(plan), transport=transport)
    except JevError as exc:
        return {
            "action": HUMAN_GATE if hard_gate else PROCEED,
            "allow_reversible_execution": True,
            "source": "deterministic_fallback",
            "jev_status": "unavailable",
            "confidence": 1.0,
            "raw_text_sent": raw_text_sent,
            "reason": str(exc),
        }

    answers = response["answers"]
    choice = answers["control_action"]
    selected = str(choice.get("choice") or "").strip().lower()
    confidence = float(choice.get("confidence") or 0.0)
    threshold = float(status["confidence_threshold"])
    needs_human_probability = float(answers["needs_human"].get("noul") or 0.0)

    if hard_gate:
        action = HUMAN_GATE
        reason = "Deterministic plan requires human confirmation or review; Jev cannot waive it."
        allow = True
    elif confidence < threshold:
        action = ASK_HUMAN
        reason = "Jev control confidence is below the configured automation threshold."
        allow = False
    elif needs_human_probability >= threshold:
        action = ASK_HUMAN
        reason = "Jev indicates human review is likely required before further automated work."
        allow = False
    elif selected == "proceed":
        action = PROCEED
        reason = "Jev selected bounded reversible execution above the configured confidence threshold."
        allow = True
    elif selected == "escalate":
        action = ESCALATE
        reason = "Jev selected escalation within the bounded control options."
        allow = False
    elif selected == "stop":
        action = STOP
        reason = "Jev selected stop within the bounded control options."
        allow = False
    else:
        action = ASK_HUMAN
        reason = "Jev selected human review or returned an unrecognized bounded choice."
        allow = False

    return {
        "action": action,
        "allow_reversible_execution": allow,
        "source": "jev_system_one",
        "jev_status": "connected_for_decision",
        "model": response.get("model"),
        "confidence": confidence,
        "needs_human_probability": needs_human_probability,
        "threshold": threshold,
        "raw_text_sent": raw_text_sent,
        "usage": response.get("usage") or {},
        "reason": reason,
    }
