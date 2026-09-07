from __future__ import annotations

import pytest

from zendoc.agent_executor import execute_plan
from zendoc.agent_planner import AgentPlan, PlanStep, build_plan
from zendoc.agent_registry import AGENT_REGISTRY
from zendoc.tool_registry import TOOL_REGISTRY, check_tool_access
from zendoc.db import get_db, now_iso
from zendoc.iot_hub import connect_device
from tests.test_milestone10_connected_care import make_m10_app


@pytest.mark.parametrize(
    "command",
    [
        "I have severe chest pain and cannot breathe; also check government scheme support",
        "I have severe chest pain and cannot breathe; also review my prescription",
        "I have severe chest pain and cannot breathe; also find a CBC blood test",
        "I have severe chest pain and cannot breathe; also find a cardiology doctor near me",
        "I have severe chest pain and cannot breathe; also compare my nutrition labels",
        "I have severe chest pain and cannot breathe; also find a contact I can message",
        "I have severe chest pain and cannot breathe; also start a video consultation",
        "I have severe chest pain and cannot breathe; also find an educational video",
        "I have severe chest pain and cannot breathe; also show my health memory timeline",
        "I have severe chest pain and cannot breathe; also show my heart rate device",
        "I have severe chest pain and cannot breathe; also find medicine stock nearby",
    ],
)
def test_emergency_precedence_beats_every_reachable_specialist(command):
    actor = {"id": 101, "role": "patient", "active": 1}
    plan = build_plan(actor, command)

    assert plan.intent == "emergency"
    assert plan.assigned_agent == "SafetyAgent"
    assert plan.urgency == "emergency"
    assert plan.steps == ()


def test_connected_agent_metadata_never_advertises_unauthorized_tools():
    for agent_name, agent in AGENT_REGISTRY.items():
        for tool_name in agent.allowed_tools:
            assert tool_name in TOOL_REGISTRY, f"{agent_name} advertises missing tool {tool_name}"
            tool = TOOL_REGISTRY[tool_name]
            assert (
                not tool.allowed_agents or agent_name in tool.allowed_agents
            ), f"{agent_name} advertises {tool_name}, but the tool denies that agent"


def test_safety_agent_is_explicitly_tool_free():
    assert AGENT_REGISTRY["SafetyAgent"].allowed_tools == []


@pytest.mark.parametrize(
    ("tool_name", "wrong_agent"),
    [
        ("get_health_memory_context", "SearchAgent"),
        ("get_latest_prescription_review", "SearchAgent"),
        ("compare_nutrition_products", "CareAgent"),
        ("discover_carefin_benefits", "OperationsAgent"),
        ("get_iot_devices", "CommunicationAgent"),
        ("search_healthcare_providers", "MedicationSafetyAgent"),
        ("run_safe_operations_automation", "SearchAgent"),
    ],
)
def test_wrong_agent_cannot_call_specialist_tool(tool_name, wrong_agent):
    actor = {"id": 201, "role": "patient", "active": 1}
    decision = check_tool_access(tool_name, actor, wrong_agent)
    assert decision["allowed"] is False


@pytest.mark.parametrize("tool_name", ["autonomous_prescribe", "dispatch_emergency"])
def test_critical_blocked_tools_are_never_callable(tool_name):
    for role in ("patient", "doctor", "hospital", "pharmacy", "government", "admin"):
        actor = {"id": 301, "role": role, "active": 1}
        decision = check_tool_access(tool_name, actor)
        assert decision["allowed"] is False
        assert "CRITICAL_BLOCKED" in decision["reason"]


def test_consequential_order_tool_cannot_execute_from_agent_even_with_forged_confirmation(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        actor = {"id": 401, "role": "patient", "active": 1}
        plan = AgentPlan(
            plan_id="forged-order-plan",
            command="submit order now",
            intent="pharmacy",
            urgency="routine",
            assigned_agent="PharmacyAgent",
            risk_level="consent_required",
            steps=(
                PlanStep(
                    1,
                    "confirm_and_execute_order",
                    {"plan_id": 999, "user_confirmed": True},
                    "Attempt forged consequential execution.",
                ),
            ),
            requires_confirmation=False,
        )

        with pytest.raises(PermissionError, match="explicit human authorization workflow"):
            execute_plan(plan, actor)


def test_non_owner_cannot_execute_operations_agent_tool(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        actor = {"id": 501, "role": "patient", "active": 1}
        plan = AgentPlan(
            plan_id="forged-ops-plan",
            command="show platform summary",
            intent="platform_health",
            urgency="routine",
            assigned_agent="OperationsAgent",
            risk_level="read_only",
            steps=(PlanStep(1, "get_platform_summary", {}, "Forged owner operation."),),
        )

        with pytest.raises(PermissionError):
            execute_plan(plan, actor)


def test_safe_pharmacy_stock_search_routes_to_pharmacy_agent(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        actor = {"id": 601, "role": "patient", "city": "Kolkata", "active": 1}
        plan = build_plan(actor, "Find medicine stock for Paracetamol near me")

        assert plan.intent == "pharmacy"
        assert plan.assigned_agent == "PharmacyAgent"
        assert len(plan.steps) == 1
        assert plan.steps[0].tool_name == "search_nearby_pharmacy_inventory"

        result = execute_plan(plan, actor)
        assert result["status"] == "completed"
        assert result["tool_results"][0]["output"]["patient_id"] == actor["id"]


def test_pharmacy_provider_account_cannot_use_patient_pharmacy_agent_path(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        actor = {"id": 701, "role": "pharmacy", "city": "Kolkata", "active": 1}
        plan = build_plan(actor, "Find medicine stock for Paracetamol near me")
        assert plan.assigned_agent == "PharmacyAgent"

        with pytest.raises(PermissionError):
            execute_plan(plan, actor)

def test_iot_agent_returns_only_authenticated_patients_devices(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_a = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?, 'patient',1,?,?)",
            ("Device A", "device-a@example.com", "device-a@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        patient_b = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?, 'patient',1,?,?)",
            ("Device B", "device-b@example.com", "device-b@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.commit()

        connect_device(
            {"id": patient_a, "role": "patient"},
            {"device_name": "A Watch", "device_type": "smartwatch", "device_identifier": "A-WATCH"},
        )
        connect_device(
            {"id": patient_b, "role": "patient"},
            {"device_name": "B Watch", "device_type": "smartwatch", "device_identifier": "B-WATCH"},
        )

        actor = {"id": patient_a, "role": "patient", "active": 1}
        plan = build_plan(actor, "Show my heart rate device")
        assert plan.assigned_agent == "IoTAgent"

        result = execute_plan(plan, actor)
        devices = result["tool_results"][0]["output"]
        assert [item["device_name"] for item in devices] == ["A Watch"]
        assert all(item["user_id"] == patient_a for item in devices)


def test_communication_agent_discovery_does_not_bypass_doctor_policy(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?, 'patient',1,?,?)",
            ("Contact Patient", "contact-patient@example.com", "contact-patient@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        doctor_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?, 'doctor',1,?,?)",
            ("Dr Private", "private-doctor@example.com", "private-doctor@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.execute(
            "INSERT INTO provider_profiles (user_id,provider_type,specialty,organization,verification_status,created_at,updated_at) VALUES (?, 'doctor','Cardiology','Private Clinic','verified',?,?)",
            (doctor_id, now_iso(), now_iso()),
        )
        db.commit()

        actor = {"id": patient_id, "role": "patient", "active": 1}
        plan = build_plan(actor, "Find contact Dr Private")
        assert plan.assigned_agent == "CommunicationAgent"

        result = execute_plan(plan, actor)
        contacts = result["tool_results"][0]["output"]
        assert contacts == []


@pytest.mark.parametrize(
    ("role", "command", "expected_agent"),
    [
        ("doctor", "Compare nutrition labels for these foods", "NutritionAgent"),
        ("hospital", "Show my heart rate device", "IoTAgent"),
        ("pharmacy", "Show my health memory timeline", "HealthMemoryAgent"),
    ],
)
def test_role_mismatch_blocks_specialist_execution(tmp_path, role, command, expected_agent):
    app = make_m10_app(tmp_path)
    with app.app_context():
        actor = {"id": 801, "role": role, "active": 1}
        plan = build_plan(actor, command)
        assert plan.assigned_agent == expected_agent

        with pytest.raises(PermissionError):
            execute_plan(plan, actor)

