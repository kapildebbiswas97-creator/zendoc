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
            "INSERT INTO users (name,email,password_hash,role,active,created_at) VALUES (?,?,?,?,?,?)",
            ("Bounded", "bounded@example.com", "x", "patient", 1, now),
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
