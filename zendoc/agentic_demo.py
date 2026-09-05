"""Synthetic Agentic Care demo scenario for ZENDOC.

This module creates a clearly labelled, deterministic demonstration path for
hackathon/submission videos. It does not contact real doctors, pharmacies,
labs, payment systems, or emergency services.
"""
from __future__ import annotations

from .agent_task_engine import create_agent_task, set_task_waiting

DEMO_GOAL = (
    "My mother has prescribed medicines. Help me organize the safest next step "
    "near her home and show where human confirmation is needed."
)


def run_synthetic_agentic_demo(actor) -> dict:
    """Return a reliable synthetic Agentic Care trace for the final demo."""
    if actor is None:
        raise PermissionError("A signed-in user is required for the Agentic Care demo.")

    task = create_agent_task(
        task_type="synthetic_agentic_care_demo",
        requested_by=int(actor["id"]),
        assigned_agent="CareAgent",
        priority="normal",
        risk_level="consent_required",
        metadata={
            "synthetic_demo": True,
            "goal": DEMO_GOAL,
            "external_services_called": False,
        },
        actor=actor,
    )
    task = set_task_waiting(
        task["id"],
        "waiting_human",
        "Synthetic demo stopped at the human confirmation boundary.",
    )

    lifecycle = [
        {
            "stage": "OBSERVE",
            "status": "completed",
            "summary": "Synthetic demo goal received from the signed-in patient account.",
        },
        {
            "stage": "UNDERSTAND",
            "status": "completed",
            "summary": "ZENDOC identifies a family-prescription coordination goal and selects the Care Agent.",
        },
        {
            "stage": "PLAN",
            "status": "completed",
            "summary": "Plan prepared with safety, consent, Health Memory, pharmacy, consultation and confirmation boundaries.",
        },
        {
            "stage": "ACT",
            "status": "waiting_confirmation",
            "summary": "Demo executes no real-world consequential action and stops before any order, booking, or record sharing.",
        },
        {
            "stage": "VERIFY",
            "status": "completed",
            "summary": "Verified task state is WAITING_HUMAN; no provider acceptance, delivery, dispatch, payment, or booking is claimed.",
        },
        {
            "stage": "REMEMBER",
            "status": "completed",
            "summary": f"Recorded synthetic demo task #{task['id']} for audit-safe review.",
        },
    ]

    plan = {
        "plan_id": f"demo-agentic-care-{task['id']}",
        "intent": "synthetic_agentic_care_demo",
        "urgency": "routine",
        "assigned_agent": "CareAgent",
        "risk_level": "consent_required",
        "requires_confirmation": True,
        "steps": [
            {
                "sequence": 1,
                "tool_name": "deterministic_safety_scan",
                "purpose": "Screen for emergency red flags before any agentic planning.",
                "status": "completed",
            },
            {
                "sequence": 2,
                "tool_name": "family_consent_boundary",
                "purpose": "Check that family/member context requires valid access and consent before private data use.",
                "status": "completed",
            },
            {
                "sequence": 3,
                "tool_name": "get_unified_healthcare_inbox",
                "purpose": "Show how ZENDOC can read patient-scoped care context when authorized.",
                "status": "planned_read_only",
            },
            {
                "sequence": 4,
                "tool_name": "search_nearby_pharmacy_inventory",
                "purpose": "Search participating pharmacy records without claiming unavailable stock.",
                "status": "planned_read_only",
            },
            {
                "sequence": 5,
                "tool_name": "get_diagnostic_options",
                "purpose": "Show diagnostic option lookup only when verified catalog/lab data exists.",
                "status": "planned_read_only",
            },
            {
                "sequence": 6,
                "tool_name": "human_confirmation_gate",
                "purpose": "Stop before consultation requests, record sharing, order submission, payment, dispatch, or provider claims.",
                "status": "waiting_human",
            },
        ],
    }

    return {
        "intent": "synthetic_agentic_care_demo",
        "urgency": "routine",
        "message": (
            "Synthetic Agentic Care demo: ZENDOC observed the family-prescription goal, selected the Care Agent, "
            "prepared a bounded plan, verified the stored task state as WAITING_HUMAN, and stopped before any "
            "real-world order, booking, payment, dispatch, or provider acceptance. This demonstrates the startup vision "
            "without fabricating integrations."
        ),
        "actions": [
            {"type": "confirm_boundary", "label": "Review Confirmation Boundary"},
            {"type": "health_memory", "label": "Open Health Memory"},
        ],
        "requires_confirmation": True,
        "task_id": task["id"],
        "run_id": None,
        "plan": plan,
        "orchestration_plan": None,
        "agentic_lifecycle": lifecycle,
        "autonomy_level": "L4_CONFIRM_AND_ACT",
        "execution_truth": "waiting_human_confirmation",
        "verification": {
            "status": "waiting_confirmation",
            "truth_state": "WAITING_HUMAN",
            "task_status": task["status"],
            "task_id": task["id"],
            "synthetic_demo": True,
        },
        "planning_assistance": {
            "accepted": False,
            "reason": "synthetic_demo_uses_deterministic_script",
            "steps": [],
        },
        "synthetic_demo": True,
    }
