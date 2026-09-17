from urllib.parse import parse_qs, urlparse

from tests.test_milestone1 import login_web, make_client, register_web
from zendoc.health_commerce import search_health_products
from zendoc.health_hub import (
    child_development_plan,
    creator_platform_readiness,
    engagement_policy,
    genomics_readiness,
)


def test_health_hub_engagement_rejects_addictive_dark_patterns():
    policy = engagement_policy()
    assert policy["optimize_for_compulsive_screen_time"] is False
    assert policy["dark_patterns_allowed"] is False
    assert policy["infinite_autoplay_for_minors_default"] is False
    assert policy["health_anxiety_targeting_allowed"] is False
    assert policy["illness_based_ad_targeting_allowed"] is False
    assert policy["child_personality_manipulation_allowed"] is False
    assert policy["success_metric"] == "care_follow_through_and_wellbeing_not_minutes_spent"


def test_child_development_is_supportive_not_diagnostic_or_personality_scoring():
    plan = child_development_plan(6)
    assert plan["life_stage"]["id"] == "child"
    assert plan["diagnosis_enabled"] is False
    assert plan["personality_scoring_enabled"] is False
    assert plan["pressure_optimization_enabled"] is False
    assert plan["caregiver_review_required_for_minor_actions"] is True
    assert {item["id"] for item in plan["domains"]} >= {
        "physical_wellbeing",
        "learning_play",
        "social_emotional",
        "digital_wellbeing",
        "care_continuity",
    }


def test_genomics_requires_verified_evidence_and_never_ai_dna_inference():
    status = genomics_readiness()
    assert status["status"] == "integration_required"
    assert status["lab_partner_configured"] is False
    assert status["genetic_test_ordering_enabled"] is False
    assert status["ai_genetic_inference_enabled"] is False
    assert status["ai_can_diagnose_genetic_condition"] is False
    assert status["verified_lab_result_required"] is True
    assert status["qualified_interpretation_required"] is True


def test_creator_cross_posting_is_not_faked_before_oauth_and_moderation():
    creator = creator_platform_readiness()
    assert creator["public_creator_uploads_enabled"] is False
    assert creator["cross_posting_enabled"] is False
    assert creator["creator_payouts_enabled"] is False
    assert creator["health_claim_moderation_enabled"] is False
    assert creator["official_social_oauth_configured"] is False


def test_health_commerce_external_links_never_claim_stock_price_or_affiliate():
    result = search_health_products("blue light glasses", "eyewear")
    assert result["external_only"] is True
    assert result["availability_verified"] is False
    assert result["price_verified"] is False
    assert result["affiliate_attribution_enabled"] is False
    assert result["affiliate_relationship_configured"] is False
    assert result["payment_execution_enabled"] is False
    assert result["results"]
    assert any(item["id"] == "amazon_india" for item in result["results"])
    assert any(item["id"] == "lenskart" for item in result["results"])
    assert all(item["affiliate_link"] is False for item in result["results"])


def test_medicine_query_stays_out_of_general_ecommerce():
    result = search_health_products("prescription medicine insulin", "general_wellness")
    assert result["medicine_query"] is True
    assert result["results"] == []
    assert result["pharmacy_handoff"].startswith("/pharmacy?q=")
    query = parse_qs(urlparse(result["pharmacy_handoff"]).query)["q"][0]
    assert "insulin" in query


def test_health_hub_page_renders_truthful_video_and_commerce_fallbacks(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "hub@example.com", "Health Hub")
    login_web(client, "patient", "hub@example.com")

    response = client.get(
        "/health-hub?topic=healthy+child+lunch+ideas&product_q=blue+light+glasses&product_category=eyewear&child_age=6"
    )
    assert response.status_code == 200
    assert b"ZENDOC Health Hub" in response.data
    assert b"Healthy engagement, not addiction." in response.data
    assert b"No fabricated video cards." in response.data
    assert b"Open exact YouTube search" in response.data
    assert b"External discovery only" in response.data
    assert b"Stock not verified" in response.data
    assert b"Price not verified" in response.data
    assert b"ZENDOC does not infer DNA." in response.data
    assert b"Health creator" in response.data
    assert b"Readiness only" in response.data
