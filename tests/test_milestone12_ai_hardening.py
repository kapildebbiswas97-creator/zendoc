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
