"""ZENDOC Health Hub: safe daily-health engagement and discovery metadata.

This module is intentionally deterministic. It does not diagnose, prescribe,
change medicines, infer genetic conditions, manipulate children, execute
payments, publish social posts, or claim third-party integrations.

The goal is useful repeat care habits, not compulsive screen time.
"""
from __future__ import annotations

from copy import deepcopy

from .family_lifecycle import age_band


CONTENT_LANES = (
    {
        "id": "healthy_cooking",
        "label": "Healthy cooking & nutrition",
        "summary": "Healthy recipes, food skills and nutrition education with evidence and source labels.",
        "clinical_boundary": "Educational only; medical nutrition therapy requires an appropriate professional.",
    },
    {
        "id": "fitness_mobility",
        "label": "Fitness, mobility & recovery",
        "summary": "Exercise education, mobility, recovery and safe habit-building.",
        "clinical_boundary": "Not a diagnosis or rehabilitation prescription; respect clinician restrictions.",
    },
    {
        "id": "mental_wellbeing",
        "label": "Mental wellbeing",
        "summary": "Stress, sleep, emotional skills, healthy routines and routes to qualified mental-health care.",
        "clinical_boundary": "No autonomous diagnosis, crisis intervention or medication advice.",
    },
    {
        "id": "child_family",
        "label": "Child & family development",
        "summary": "Age-aware parenting education, play, routines, communication, physical wellbeing and caregiver coordination.",
        "clinical_boundary": "No personality engineering, developmental diagnosis or pressure-based optimization.",
    },
    {
        "id": "women_family_health",
        "label": "Family building, pregnancy & midlife",
        "summary": "User-selected education and navigation for family building, pregnancy/postpartum and midlife journeys.",
        "clinical_boundary": "Sensitive states are never inferred; clinical decisions remain with qualified professionals.",
    },
    {
        "id": "clinician_education",
        "label": "Doctor & clinician education",
        "summary": "Provider-reviewed explainers, appointment preparation and trustworthy health education.",
        "clinical_boundary": "Content does not replace an individual clinical assessment.",
    },
    {
        "id": "elder_remote_care",
        "label": "Older adult & remote family care",
        "summary": "Caregiver education, safe-home planning and consent-scoped coordination across distance.",
        "clinical_boundary": "Relationship alone never grants health-data permission or payment authority.",
    },
    {
        "id": "devices_iot",
        "label": "Health devices & IoT",
        "summary": "Device education, measurement provenance and future verified integrations.",
        "clinical_boundary": "Consumer-device claims are not treated as validated medical-device evidence without verification.",
    },
)

CHILD_DEVELOPMENT_DOMAINS = (
    {
        "id": "physical_wellbeing",
        "label": "Physical wellbeing",
        "summary": "Age-appropriate movement, sleep, routine, nutrition and preventive-care follow-through.",
    },
    {
        "id": "learning_play",
        "label": "Learning & play",
        "summary": "Curiosity, play, reading and age-appropriate learning without performance pressure.",
    },
    {
        "id": "communication",
        "label": "Communication",
        "summary": "Supportive language, listening and caregiver-child communication habits.",
    },
    {
        "id": "social_emotional",
        "label": "Social & emotional skills",
        "summary": "Emotional vocabulary, relationships, empathy and help-seeking skills without personality scoring.",
    },
    {
        "id": "healthy_habits",
        "label": "Healthy habits",
        "summary": "Small repeatable routines for food, movement, hygiene, sleep and everyday safety.",
    },
    {
        "id": "digital_wellbeing",
        "label": "Digital wellbeing",
        "summary": "Balanced screen use, privacy awareness and age-appropriate digital habits.",
    },
    {
        "id": "care_continuity",
        "label": "Care continuity",
        "summary": "Keep verified records, appointments, caregiver tasks and follow-up visible across age stages.",
    },
    {
        "id": "safety_support",
        "label": "Safety & support",
        "summary": "Escalate concerns to caregivers and qualified professionals instead of letting AI make high-risk decisions.",
    },
)

GENOMICS_BOUNDARY = {
    "status": "integration_required",
    "lab_partner_configured": False,
    "genetic_test_ordering_enabled": False,
    "ai_genetic_inference_enabled": False,
    "ai_can_diagnose_genetic_condition": False,
    "ai_can_select_or_change_treatment": False,
    "verified_lab_result_required": True,
    "qualified_interpretation_required": True,
    "summary": (
        "ZENDOC may later organize verified newborn/child genetic-test results from an authorized laboratory, "
        "plus counseling and follow-up. It must never infer DNA findings from chat, symptoms, images, videos, "
        "wearables or ordinary app activity."
    ),
}

CREATOR_PLATFORM_READINESS = {
    "public_creator_uploads_enabled": False,
    "cross_posting_enabled": False,
    "creator_payouts_enabled": False,
    "health_claim_moderation_enabled": False,
    "official_social_oauth_configured": False,
    "status": "readiness_only",
    "required_before_launch": [
        "identity and age controls",
        "copyright and consent workflow",
        "medical-claim moderation and escalation",
        "misinformation and harmful-content reporting",
        "minor-safety controls",
        "creator disclosure and sponsorship labels",
        "official OAuth/API integrations for each destination platform",
        "appeals, audit logs and repeat-offender handling",
    ],
    "truth_notice": (
        "ZENDOC does not currently publish creator videos or cross-post to external social networks. "
        "A one-click cross-post feature requires each platform's official authorization/API and user OAuth."
    ),
}

ENGAGEMENT_POLICY = {
    "optimize_for_compulsive_screen_time": False,
    "dark_patterns_allowed": False,
    "infinite_autoplay_for_minors_default": False,
    "health_anxiety_targeting_allowed": False,
    "illness_based_ad_targeting_allowed": False,
    "child_personality_manipulation_allowed": False,
    "social_score_for_children_allowed": False,
    "daily_goal": "useful_health_action_or_learning",
    "success_metric": "care_follow_through_and_wellbeing_not_minutes_spent",
    "summary": (
        "ZENDOC should become a trusted daily habit by helping users complete useful health actions, learn, "
        "and coordinate care—not by making people psychologically dependent on the app."
    ),
}


def health_content_catalog():
    return [deepcopy(item) for item in CONTENT_LANES]


def child_development_plan(age=None):
    stage = age_band(age)
    return {
        "life_stage": stage,
        "domains": [deepcopy(item) for item in CHILD_DEVELOPMENT_DOMAINS],
        "diagnosis_enabled": False,
        "personality_scoring_enabled": False,
        "pressure_optimization_enabled": False,
        "caregiver_review_required_for_minor_actions": True,
        "summary": (
            "Support healthy development with age-aware education, routines, records and caregiver tasks. "
            "AI does not decide what personality a child should have or diagnose developmental conditions."
        ),
    }


def genomics_readiness():
    return deepcopy(GENOMICS_BOUNDARY)


def creator_platform_readiness():
    return deepcopy(CREATOR_PLATFORM_READINESS)


def engagement_policy():
    return deepcopy(ENGAGEMENT_POLICY)
