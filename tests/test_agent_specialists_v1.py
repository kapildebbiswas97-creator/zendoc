from datetime import datetime, timedelta, timezone

import pytest

from tests.test_milestone1 import make_app
from zendoc.agent_executor import execute_plan
from zendoc.agent_planner import AgentPlan, PlanStep, build_plan
from zendoc.agent_registry import get_agent
from zendoc.db import get_db
from zendoc.tool_registry import check_tool_access


def _plan(agent, tool, arguments=None, requires_confirmation=False):
    return AgentPlan(
        plan_id="specialist-test",
        command="test",
        intent="test",
        urgency="routine",
        assigned_agent=agent,
        risk_level="read_only",
        steps=(PlanStep(1, tool, arguments or {}, "test"),),
        requires_confirmation=requires_confirmation,
    )


def test_dedicated_domain_agents_are_registered():
    for agent_id in (
        "BookingAgent",
        "CommerceAgent",
        "FitnessAgent",
        "PreventionAgent",
        "LifecycleAgent",
        "LearningAgent",
        "ModelImprovementAgent",
    ):
        assert get_agent(agent_id) is not None

    assert "confirm_provider_booking" in get_agent("BookingAgent").allowed_tools
    assert "search_health_products" in get_agent("CommerceAgent").allowed_tools
    assert get_agent("ModelImprovementAgent").allowed_tools == []


def test_planner_routes_booking_commerce_fitness_and_learning(tmp_path):
    app = make_app(tmp_path)
    actor = {"id": 501, "role": "patient", "active": 1}
    with app.app_context():
        booking = build_plan(actor, "Book appointment with a cardiologist in Kalyani tomorrow")
        assert booking.assigned_agent == "BookingAgent"
        assert booking.requires_confirmation is True
        assert booking.steps[0].tool_name == "search_healthcare_providers"

        commerce = build_plan(actor, "Find fitness equipment for home workouts")
        assert commerce.assigned_agent == "CommerceAgent"
        assert commerce.steps[0].tool_name == "search_health_products"

        fitness = build_plan(actor, "Create a fitness workout plan")
        assert fitness.assigned_agent == "FitnessAgent"

        learning = build_plan(actor, "Teach me about blood pressure as health education")
        assert learning.assigned_agent == "LearningAgent"
        assert learning.steps[0].tool_name == "search_educational_video"


def test_commerce_agent_returns_truthful_external_handoffs_without_payment():
    actor = {"id": 1, "role": "patient", "active": 1}
    result = execute_plan(
        _plan("CommerceAgent", "search_health_products", {"query": "home exercise mat", "category": "fitness"}),
        actor,
    )
    output = result["tool_results"][0]["output"]
    assert output["external_only"] is True
    assert output["price_verified"] is False
    assert output["availability_verified"] is False
    assert output["payment_execution_enabled"] is False
    assert output["affiliate_relationship_configured"] is False

    payment = check_tool_access("execute_payment", actor, "CommerceAgent")
    assert payment["allowed"] is False
    assert "CRITICAL_BLOCKED" in payment["reason"]


def test_booking_agent_reads_real_verified_slots_but_autonomous_confirmation_is_blocked(tmp_path):
    app = make_app(tmp_path)
    target = datetime.now(timezone.utc).date() + timedelta(days=10)
    weekday = target.weekday()
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with app.app_context():
        db = get_db()
        patient_id = db.execute(
            """
            INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
            VALUES ('Booking Patient','booking-agent-patient@example.test','booking-agent-patient@example.test','unused','patient',1,?,?)
            """,
            (stamp, stamp),
        ).lastrowid
        doctor_id = db.execute(
            """
            INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
            VALUES ('Dr Booking Sen','booking-agent-doctor@example.test','booking-agent-doctor@example.test','unused','doctor',1,?,?)
            """,
            (stamp, stamp),
        ).lastrowid
        profile_id = db.execute(
            """
            INSERT INTO provider_profiles
            (user_id,provider_type,specialty,organization,address,city,state,postal_code,verification_status,created_at,updated_at)
            VALUES (?,'doctor','Cardiology','Booking Heart Clinic','Station Road','Kalyani','West Bengal','741235','verified',?,?)
            """,
            (doctor_id, stamp, stamp),
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

        actor = dict(db.execute("SELECT * FROM users WHERE id=?", (patient_id,)).fetchone())
        options = execute_plan(
            _plan(
                "BookingAgent",
                "get_provider_booking_options",
                {"provider_profile_id": profile_id, "date": target.isoformat()},
            ),
            actor,
        )
        output = options["tool_results"][0]["output"]
        assert output["bookable_in_zendoc"] is True
        assert output["confirmation_required"] is True
        assert output["available_slots"]
        assert output["available_slots"][0].startswith(target.isoformat())

        confirm_plan = _plan(
            "BookingAgent",
            "confirm_provider_booking",
            {
                "provider_profile_id": profile_id,
                "scheduled_for": output["available_slots"][0],
                "reason": "Cardiology consultation",
                "user_confirmed": True,
            },
            requires_confirmation=True,
        )
        with pytest.raises(PermissionError, match="explicit human authorization workflow"):
            execute_plan(confirm_plan, actor)

        count = db.execute("SELECT COUNT(*) AS c FROM appointments WHERE patient_id=?", (patient_id,)).fetchone()["c"]
        assert count == 0


def test_model_improvement_requests_are_owner_only_and_have_no_execution_tools(tmp_path):
    app = make_app(tmp_path)
    patient = {"id": 41, "role": "patient", "active": 1}
    with app.app_context():
        denied = build_plan(patient, "Improve model and run offline eval")
        assert denied.authorization_error
        assert denied.steps == ()

    model_agent = get_agent("ModelImprovementAgent")
    assert model_agent.allowed_tools == []
    assert "configured_owner_review_before_any_production_promotion" in model_agent.approval_requirements
