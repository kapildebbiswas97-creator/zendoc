"""Milestone 12 AI hardening regression tests.

These tests protect deterministic emergency handling and conflict-aware intent
routing.  They deliberately test product routing semantics, not medical
diagnosis or clinical validation.
"""

import pytest

from zendoc.intent import IntentRouter
from zendoc.safety import SafetyEngine


@pytest.mark.parametrize(
    ("message", "category"),
    [
        ("I have crushing chest pain", "cardiac"),
        ("I cannot breathe properly", "breathing"),
        ("The bleeding won't stop", "bleeding"),
        ("My face is drooping and speech is slurred", "stroke"),
        ("They are unresponsive and not waking up", "consciousness"),
        ("He is having a seizure", "seizure"),
        ("My tongue is swelling after an allergic reaction", "allergic_reaction"),
        ("I think this may be an overdose", "poisoning"),
        ("I want to kill myself", "self_harm"),
    ],
)
def test_m12_emergency_categories_are_detected_deterministically(message, category):
    result = SafetyEngine().assess(message)
    assert result["emergency"] is True
    assert result["urgency"] == "emergency"
    assert result["category"] == category
    assert result["guidance"]


@pytest.mark.parametrize(
    "message",
    [
        "I do not have chest pain.",
        "I have no shortness of breath.",
        "I deny severe bleeding.",
        "I am not suicidal.",
        "I have never had a seizure.",
    ],
)
def test_m12_simple_negated_red_flags_do_not_trigger_by_themselves(message):
    result = SafetyEngine().assess(message)
    assert result["emergency"] is False


def test_m12_negated_first_clause_does_not_hide_real_second_red_flag():
    result = SafetyEngine().assess(
        "I do not have chest pain, but I cannot breathe properly."
    )
    assert result["emergency"] is True
    assert result["category"] == "breathing"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("book a doctor appointment", "appointment"),
        ("find a cardiologist", "doctor"),
        ("medicine delivery", "pharmacy"),
        ("my mother needs medicines", "family_care"),
        ("find a workout video", "fitness_video_search"),
        ("show my report", "report_history"),
        ("explain my report", "report_intelligence"),
        ("ambulance for a scheduled hospital transfer", "ambulance"),
        ("connect my BP monitor", "iot_hub"),
        ("doctor video consultation", "telehealth"),
        ("I need a nurse at home", "home_health"),
    ],
)
def test_m12_specific_intents_win_over_generic_keyword_collisions(message, expected):
    assert IntentRouter().detect(message) == expected


def test_m12_plain_chest_pain_keyword_does_not_need_intent_router_for_safety():
    safety = SafetyEngine().assess("I have chest pain")
    assert safety["emergency"] is True
    # The application safety gate runs first; the router is not the authority
    # that decides whether symptom text represents an emergency.
    assert IntentRouter().detect("I have chest pain") in {"symptoms", "general_assistant"}


from zendoc.assistant_modes import (
    doctor_ai_response,
    general_assistant_response,
    mental_wellness_ai_response,
    normalize_ai_mode,
)
from tests.test_milestone1 import csrf, login_web, make_client, register_web


def test_m12_ai_mode_normalization_is_fail_closed():
    assert normalize_ai_mode("doctor") == "doctor"
    assert normalize_ai_mode("MENTAL") == "mental"
    assert normalize_ai_mode("unknown-mode") == "zendoc"


def test_m12_doctor_ai_is_specialized_but_not_presented_as_a_real_doctor():
    result = doctor_ai_response(
        "I have fever and headache. Can you tell me a medicine name?"
    )
    assert result.intent == "doctor_ai"
    assert result.emergency is False
    assert "paracetamol" in result.message.lower() or "acetaminophen" in result.message.lower()
    assert "not a licensed doctor" in result.safety_notice.lower()
    assert any(action["type"] == "telehealth" for action in result.possible_actions)


def test_m12_doctor_ai_refuses_autonomous_antibiotic_or_dose_selection():
    result = doctor_ai_response("Which antibiotic should I take and can you change my dose?")
    assert "cannot select an antibiotic" in result.message.lower()
    assert "change a dose" in result.message.lower()


def test_m12_mental_wellness_ai_has_separate_support_boundary():
    result = mental_wellness_ai_response("I feel overwhelmed before exams and cannot sleep")
    assert result.intent == "mental_wellness"
    assert "not a therapist" in result.message.lower()
    assert result.model_metadata["assistant_mode"] == "mental"


def test_m12_specialized_ai_pages_render_and_keep_histories_separate(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "m12-ai@example.com", "M12 AI")
    login_web(client, "patient", "m12-ai@example.com")

    doctor_page = client.get("/ai?mode=doctor")
    assert doctor_page.status_code == 200
    assert b"Doctor AI" in doctor_page.data
    assert b"Request a real doctor" in doctor_page.data

    token = csrf(doctor_page.data.decode())
    doctor_response = client.post(
        "/ai",
        data={
            "csrf_token": token,
            "ai_mode": "doctor",
            "message": "I have fever and cough for two days.",
        },
        follow_redirects=True,
    )
    assert doctor_response.status_code == 200
    assert b"Doctor AI" in doctor_response.data
    assert b"fever and cough" in doctor_response.data

    assistant_page = client.get("/ai?mode=assistant")
    assert assistant_page.status_code == 200
    assert b"General Assistant" in assistant_page.data
    # Doctor-mode interaction must not be rendered in the separate assistant history.
    assert b"fever and cough" not in assistant_page.data


def test_m12_legacy_doctor_form_still_routes_to_doctor_mode(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "m12-legacy@example.com", "Legacy AI")
    login_web(client, "patient", "m12-legacy@example.com")
    page = client.get("/ai")
    token = csrf(page.data.decode())
    response = client.post(
        "/ai",
        data={"csrf_token": token, "feature": "doctor", "symptoms": "chest pain"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Emergency guidance" in response.data
    assert b"Seek urgent care now" in response.data


from zendoc.intelligence import ZendocIntelligence
from zendoc.db import get_db, now_iso


def test_m12_zendoc_ai_uses_only_same_conversation_context(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "patient", "context@example.com", "Context User")
    login_web(client, "patient", "context@example.com")

    with app.app_context():
        user = get_db().execute("SELECT * FROM users WHERE email=?", ("context@example.com",)).fetchone()
        db = get_db()
        now = now_iso()
        conv_a = db.execute(
            "INSERT INTO ai_conversations (user_id,title,last_intent,created_at,updated_at) VALUES (?,?,?,?,?)",
            (user["id"], "A", "symptoms", now, now),
        ).lastrowid
        conv_b = db.execute(
            "INSERT INTO ai_conversations (user_id,title,last_intent,created_at,updated_at) VALUES (?,?,?,?,?)",
            (user["id"], "B", "symptoms", now, now),
        ).lastrowid
        db.execute(
            """
            INSERT INTO ai_interactions
            (user_id,conversation_id,feature,intent,input_text,output_text,risk_level,model_version,provider,emergency,success,latency_ms,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (user["id"], conv_a, "zendoc_ai", "symptoms", "I have fever", "ok", "routine", "test", "test", 0, 1, 1, now),
        )
        db.execute(
            """
            INSERT INTO ai_interactions
            (user_id,conversation_id,feature,intent,input_text,output_text,risk_level,model_version,provider,emergency,success,latency_ms,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (user["id"], conv_b, "zendoc_ai", "symptoms", "I have a rash", "ok", "routine", "test", "test", 0, 1, 1, now),
        )
        db.commit()

        conversation = db.execute(
            "SELECT * FROM ai_conversations WHERE id=? AND user_id=?",
            (conv_a, user["id"]),
        ).fetchone()
        result, _latency = ZendocIntelligence().respond(
            "for three days",
            user=user,
            conversation=conversation,
        )
        assert result.intent == "symptoms"
        assert result.model_metadata["conversation_context_used"] is True
        assert result.model_metadata["context_messages_used"] == 1
        # The other conversation must not contaminate this response.
        assert "rash" not in result.message.lower()


def test_m12_zendoc_ai_context_is_bounded_to_recent_messages(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        db = get_db()
        now = now_iso()
        user_id = db.execute(
            "INSERT INTO users (name,email,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
            ("Bounded", "bounded@example.com", "x", "patient", 1, now, now),
        ).lastrowid
        conv_id = db.execute(
            "INSERT INTO ai_conversations (user_id,title,last_intent,created_at,updated_at) VALUES (?,?,?,?,?)",
            (user_id, "Bounded", "symptoms", now, now),
        ).lastrowid
        for idx in range(10):
            db.execute(
                """
                INSERT INTO ai_interactions
                (user_id,conversation_id,feature,intent,input_text,output_text,risk_level,model_version,provider,emergency,success,latency_ms,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (user_id, conv_id, "zendoc_ai", "symptoms", f"message {idx}", "ok", "routine", "test", "test", 0, 1, 1, now),
            )
        db.commit()
        user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        conversation = db.execute("SELECT * FROM ai_conversations WHERE id=?", (conv_id,)).fetchone()
        context = ZendocIntelligence()._context(user, conversation, "symptoms")
        assert len(context["recent_user_messages"]) == 4
        assert context["recent_user_messages"][0] == "message 6"
        assert context["recent_user_messages"][-1] == "message 9"


def test_m12_specialized_ai_context_does_not_retrigger_old_emergency_phrase():
    # Previous conversational context may inform guidance, but the deterministic
    # emergency gate evaluates the current turn so stale emergency wording does
    # not trap the user in an emergency state forever.
    result = doctor_ai_response(
        "I am feeling better now.",
        recent_user_messages=["Yesterday I had chest pain."],
    )
    assert result.emergency is False


def test_m12_general_assistant_preserves_bounded_context_metadata():
    result = general_assistant_response(
        "continue that explanation",
        recent_user_messages=[
            "Explain Python dictionaries simply.",
            "Show me one short example.",
        ],
    )
    assert result.model_metadata["conversation_context_used"] is True
    assert result.model_metadata["context_messages_used"] == 2


def test_m12_general_assistant_is_local_model_eligible():
    from zendoc.model_router import SAFE_LOCAL_TASKS
    assert "general_assistant" in SAFE_LOCAL_TASKS


def test_m125_agentic_intent_routes_explicit_workflow_language():
    from zendoc.intent import IntentRouter
    assert IntentRouter().detect("use agentic care to handle this workflow") == "core_agent"


def test_m125_agentic_care_lifecycle_is_observable_and_bounded(tmp_path):
    from zendoc.agentic_care import run_agentic_care

    app, client = make_client(tmp_path)
    register_web(client, "patient", "agentic@example.com", "Agentic User")
    login_web(client, "patient", "agentic@example.com")

    with app.app_context():
        user = get_db().execute(
            "SELECT * FROM users WHERE email=?", ("agentic@example.com",)
        ).fetchone()
        result = run_agentic_care(user, "check my unread messages")
        stages = [item["stage"] for item in result["agentic_lifecycle"]]
        assert stages == ["OBSERVE", "UNDERSTAND", "PLAN", "ACT", "VERIFY", "REMEMBER"]
        assert result["autonomy_level"] in {"L3_SAFE_AUTONOMY", "L2_PLAN_OR_GUIDE"}
        assert result["execution_truth"] == "bounded_permissioned_execution"
        assert result["run_id"]
        assert result["task_id"]


def test_m125_agentic_care_does_not_bypass_confirmation(tmp_path):
    from zendoc.agentic_care import run_agentic_care

    app, client = make_client(tmp_path)
    register_web(client, "patient", "agentic-confirm@example.com", "Agentic Confirm")
    login_web(client, "patient", "agentic-confirm@example.com")

    with app.app_context():
        user = get_db().execute(
            "SELECT * FROM users WHERE email=?", ("agentic-confirm@example.com",)
        ).fetchone()
        result = run_agentic_care(user, "share my medical record")
        assert result["requires_confirmation"] is True
        assert result["autonomy_level"] == "L4_CONFIRM_AND_ACT"
        assert result["execution_truth"] == "waiting_human_confirmation"
        act = next(item for item in result["agentic_lifecycle"] if item["stage"] == "ACT")
        assert act["status"] == "waiting_confirmation"


def test_m125_explicit_agentic_invocation_wins_over_nested_workflow_keyword():
    from zendoc.intent import IntentRouter
    assert IntentRouter().detect("Use agentic care to check my unread messages") == "core_agent"


def test_m125_zendoc_ai_renders_agent_activity_trace(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "patient", "agent-ui@example.com", "Agent UI")
    login_web(client, "patient", "agent-ui@example.com")

    page = client.get("/ai?mode=zendoc")
    token = csrf(page.data.decode())
    response = client.post(
        "/ai",
        data={
            "csrf_token": token,
            "ai_mode": "zendoc",
            "message": "Use agentic care to check my unread messages",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Agent Activity" in response.data
    assert b"OBSERVE" in response.data
    assert b"UNDERSTAND" in response.data
    assert b"PLAN" in response.data
    assert b"ACT" in response.data
    assert b"VERIFY" in response.data
    assert b"REMEMBER" in response.data
    assert b"Permissioned tool plan" in response.data
    assert b"get unread summary" in response.data
    assert b"not hidden model reasoning" in response.data


def test_m125_natural_multistep_family_goal_uses_agentic_orchestration(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "patient", "natural-agentic@example.com", "Natural Agentic")
    login_web(client, "patient", "natural-agentic@example.com")

    with app.app_context():
        user = get_db().execute(
            "SELECT * FROM users WHERE email=?", ("natural-agentic@example.com",)
        ).fetchone()
        result, _ = ZendocIntelligence().respond(
            "My mother has prescribed medicines. Help me organize the safest next step near her home.",
            user=user,
            conversation=None,
        )
        # Preserve the M11 public provider contract while proving that the
        # request is executed through the new Agentic Care runtime.
        assert result.provider == "healthcare_orchestrator"
        assert result.model_metadata["agentic_care"] is True
        assert result.model_metadata["agentic_runtime"] == "zendoc_agentic_care_os"
        assert result.model_metadata["lifecycle"]
        assert result.model_metadata["verification"]["truth_state"] in {
            "WAITING_HUMAN", "BLOCKED_DATA", "BLOCKED_PERMISSION", "BOUNDED_EXECUTION_VERIFIED"
        }


def test_m125_simple_symptom_question_does_not_overroute_to_agentic_care(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "patient", "simple-health@example.com", "Simple Health")
    login_web(client, "patient", "simple-health@example.com")

    with app.app_context():
        user = get_db().execute(
            "SELECT * FROM users WHERE email=?", ("simple-health@example.com",)
        ).fetchone()
        result, _ = ZendocIntelligence().respond(
            "I have a mild headache since this morning.",
            user=user,
            conversation=None,
        )
        assert result.intent == "symptoms"
        assert result.provider != "zendoc_agentic_care_os"
        assert result.model_metadata.get("agentic_care") is not True


def test_m125_waiting_provider_requires_authoritative_provider_transition(tmp_path):
    from zendoc.agent_task_engine import create_agent_task, resume_waiting_task, set_task_waiting

    app, client = make_client(tmp_path)
    register_web(client, "patient", "provider-wait@example.com", "Provider Wait")
    login_web(client, "patient", "provider-wait@example.com")

    with app.app_context():
        user = get_db().execute(
            "SELECT * FROM users WHERE email=?", ("provider-wait@example.com",)
        ).fetchone()
        task = create_agent_task(
            task_type="provider_wait_test",
            requested_by=user["id"],
            assigned_agent="CareAgent",
            risk_level="low_risk",
            actor=user,
        )
        task = set_task_waiting(task["id"], "waiting_provider", "Waiting for provider acknowledgement.")
        assert task["status"] == "waiting_provider"

        with pytest.raises(PermissionError):
            resume_waiting_task(
                task["id"],
                user,
                authoritative_state="human_confirmed",
            )

        resumed = resume_waiting_task(
            task["id"],
            user,
            authoritative_state="provider_acknowledged",
            summary="Provider acknowledgement recorded.",
        )
        assert resumed["status"] == "queued"


def test_m125_verifier_never_overclaims_waiting_provider(tmp_path):
    from zendoc.agentic_care import verify_agentic_result
    from zendoc.agent_task_engine import create_agent_task, set_task_waiting

    app, client = make_client(tmp_path)
    register_web(client, "patient", "verify-provider@example.com", "Verify Provider")
    login_web(client, "patient", "verify-provider@example.com")

    with app.app_context():
        user = get_db().execute(
            "SELECT * FROM users WHERE email=?", ("verify-provider@example.com",)
        ).fetchone()
        task = create_agent_task(
            task_type="provider_verify_test",
            requested_by=user["id"],
            assigned_agent="CareAgent",
            risk_level="low_risk",
            actor=user,
        )
        set_task_waiting(task["id"], "waiting_provider", "Awaiting authoritative provider response.")
        verification = verify_agentic_result(user, {"task_id": task["id"]})
        assert verification["truth_state"] == "WAITING_PROVIDER"
        assert "waiting for an authoritative provider response" in verification["summary"].lower()


def test_m125_model_candidate_plan_rejects_unknown_tool(tmp_path):
    from zendoc.agent_candidate_planner import validate_candidate_plan

    app, client = make_client(tmp_path)
    register_web(client, "patient", "candidate-unknown@example.com", "Candidate Unknown")
    login_web(client, "patient", "candidate-unknown@example.com")

    with app.app_context():
        user = get_db().execute(
            "SELECT * FROM users WHERE email=?", ("candidate-unknown@example.com",)
        ).fetchone()
        result = validate_candidate_plan(
            {
                "steps": [
                    {
                        "tool_name": "execute_shell",
                        "inputs": {},
                        "purpose": "Try an unsafe tool",
                    }
                ]
            },
            user,
            "SearchAgent",
        )
        assert result.accepted is False
        assert result.reason.startswith("tool_not_model_plannable")


def test_m125_model_candidate_plan_enforces_max_step_limit(tmp_path):
    from zendoc.agent_candidate_planner import MODEL_PLAN_MAX_STEPS, validate_candidate_plan

    app, client = make_client(tmp_path)
    register_web(client, "patient", "candidate-limit@example.com", "Candidate Limit")
    login_web(client, "patient", "candidate-limit@example.com")

    with app.app_context():
        user = get_db().execute(
            "SELECT * FROM users WHERE email=?", ("candidate-limit@example.com",)
        ).fetchone()
        candidate = {
            "steps": [
                {
                    "tool_name": "find_contact",
                    "inputs": {"query": "doctor"},
                    "purpose": "Find permitted contacts",
                }
                for _ in range(MODEL_PLAN_MAX_STEPS + 1)
            ]
        }
        result = validate_candidate_plan(candidate, user, "SearchAgent")
        assert result.accepted is False
        assert result.reason == "step_limit_exceeded"


def test_m125_model_candidate_plan_rejects_unapproved_arguments(tmp_path):
    from zendoc.agent_candidate_planner import validate_candidate_plan

    app, client = make_client(tmp_path)
    register_web(client, "patient", "candidate-args@example.com", "Candidate Args")
    login_web(client, "patient", "candidate-args@example.com")

    with app.app_context():
        user = get_db().execute(
            "SELECT * FROM users WHERE email=?", ("candidate-args@example.com",)
        ).fetchone()
        result = validate_candidate_plan(
            {
                "steps": [
                    {
                        "tool_name": "find_contact",
                        "inputs": {"query": "doctor", "sql": "DROP TABLE users"},
                        "purpose": "Unsafe extra argument",
                    }
                ]
            },
            user,
            "SearchAgent",
        )
        assert result.accepted is False
        assert result.reason == "argument_not_allowed:find_contact"


def test_m125_voice_access_can_submit_low_risk_agentic_goal_but_keeps_consequential_confirmation():
    app_js = open("static/app.js", encoding="utf-8").read()
    assert 'text.startsWith("ask zendoc ")' in app_js
    assert "submitAIRequest" in app_js
    assert "Any consequential healthcare action will still require explicit confirmation." in app_js
    assert 'pendingAction = { kind: "login_submit"' in app_js
    assert 'pendingAction = { kind: "send_ai"' in app_js
    assert 'if (["confirm", "yes confirm", "proceed", "continue"].includes(text))' in app_js


def test_m125_voice_access_reads_visible_agent_activity_without_hidden_reasoning():
    app_js = open("static/app.js", encoding="utf-8").read()
    template = open("templates/ai.html", encoding="utf-8").read()
    assert 'readAgentActivity' in app_js
    assert 'read agent activity' in app_js
    assert 'data-agentic-result="true"' in template
    assert "not hidden model reasoning" in template


def test_m125_agentic_care_exposes_planning_assistance_metadata(tmp_path):
    from zendoc.agentic_care import run_agentic_care

    app, client = make_client(tmp_path)
    register_web(client, "patient", "planning-meta@example.com", "Planning Meta")
    login_web(client, "patient", "planning-meta@example.com")

    with app.app_context():
        user = get_db().execute(
            "SELECT * FROM users WHERE email=?", ("planning-meta@example.com",)
        ).fetchone()
        result = run_agentic_care(user, "check my unread messages")
        assert "planning_assistance" in result
        assert result["planning_assistance"]["accepted"] is False
        assert result["planning_assistance"]["reason"] == "not_needed"


def test_m125_synthetic_demo_routes_explicitly():
    assert IntentRouter().detect("Run ZENDOC synthetic agentic demo") == "synthetic_agentic_demo"


def test_m125_synthetic_demo_is_labelled_bounded_and_waiting_human(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "patient", "demo-agentic@example.com", "Demo Agentic")
    login_web(client, "patient", "demo-agentic@example.com")

    with app.app_context():
        user = get_db().execute(
            "SELECT * FROM users WHERE email=?", ("demo-agentic@example.com",)
        ).fetchone()
        result, _ = ZendocIntelligence().respond(
            "Run ZENDOC synthetic agentic demo",
            user=user,
            conversation=None,
        )
        assert result.intent == "synthetic_agentic_demo"
        assert result.model_metadata["synthetic_demo"] is True
        assert result.model_metadata["agentic_care"] is True
        assert result.model_metadata["verification"]["truth_state"] == "WAITING_HUMAN"
        assert result.model_metadata["verification"]["synthetic_demo"] is True
        assert "Synthetic Agentic Care demo" in result.message
        assert "no real-world order" in result.message
        assert result.model_metadata["plan"]["requires_confirmation"] is True


def test_m125_synthetic_demo_renders_agent_activity(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "patient", "demo-ui@example.com", "Demo UI")
    login_web(client, "patient", "demo-ui@example.com")
    page = client.get("/ai?mode=zendoc")
    token = csrf(page.data.decode())
    response = client.post(
        "/ai",
        data={
            "csrf_token": token,
            "ai_mode": "zendoc",
            "message": "Run ZENDOC synthetic agentic demo",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Synthetic Agentic Care demo" in response.data
    assert b"Agent Activity" in response.data
    assert b"WAITING HUMAN" in response.data or b"waiting human" in response.data.lower()
