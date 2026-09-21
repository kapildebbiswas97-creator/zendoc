"""Truthful health-commerce discovery helpers.

This module intentionally provides *external search handoffs*, not ecommerce,
affiliate revenue, inventory, pricing, prescription, ordering, or payment.

Health-data and clinical recommendations must never be biased by commercial
relationships. A future affiliate/merchant integration requires a real program
agreement, disclosure, deterministic attribution, consent/privacy review and
integration-specific tests before ZENDOC may claim referral revenue.
"""
from __future__ import annotations

from copy import deepcopy
import re
from urllib.parse import quote_plus, urlparse


COMMERCE_CATEGORIES = (
    {
        "id": "food_fresh",
        "label": "Fresh food & healthy groceries",
        "safety_note": (
            "Food discovery is general wellness support, not medical nutrition therapy. Allergies, kidney disease, "
            "diabetes, pregnancy and other clinical dietary needs may require qualified professional guidance."
        ),
    },
    {
        "id": "eyewear",
        "label": "Eyewear & vision accessories",
        "safety_note": (
            "Prescription power must come from a licensed eye-care professional or a verified prescription. "
            "ZENDOC AI does not infer or change lens power."
        ),
    },
    {
        "id": "fitness",
        "label": "Fitness & recovery equipment",
        "safety_note": "Product discovery is not a medical recommendation. Follow clinician restrictions when applicable.",
    },
    {
        "id": "nutrition",
        "label": "Food & nutrition products",
        "safety_note": (
            "ZENDOC does not infer that a supplement is medically necessary. Medication interactions, pregnancy, "
            "chronic disease and deficiencies require appropriate professional review."
        ),
    },
    {
        "id": "home_health",
        "label": "Home-health & wellness devices",
        "safety_note": (
            "Consumer device listings are not treated as validated medical-device measurements unless the exact device, "
            "intended use and integration have been verified."
        ),
    },
    {
        "id": "baby_child",
        "label": "Baby & child wellness products",
        "safety_note": "Age suitability and safety must be checked with the product manufacturer and appropriate clinician when needed.",
    },
    {
        "id": "general_wellness",
        "label": "General wellness",
        "safety_note": "Commercial discovery remains separate from clinical advice and care prioritization.",
    },
)


MERCHANTS = (
    {
        "id": "blinkit",
        "label": "Blinkit",
        "categories": {"food_fresh", "nutrition", "general_wellness"},
        "search_template": "https://blinkit.com/s/?q={query}",
        "relationship_status": "external_search_only",
    },
    {
        "id": "bigbasket",
        "label": "BigBasket",
        "categories": {"food_fresh", "nutrition", "general_wellness"},
        "search_template": "https://www.bigbasket.com/ps/?q={query}",
        "relationship_status": "external_search_only",
    },
    {
        "id": "zepto",
        "label": "Zepto",
        "categories": {"food_fresh", "nutrition", "general_wellness"},
        "search_template": "https://www.zeptonow.com/search?query={query}",
        "relationship_status": "external_search_only",
    },
    {
        "id": "swiggy_instamart",
        "label": "Swiggy Instamart",
        "categories": {"food_fresh", "nutrition", "general_wellness"},
        "search_template": "https://www.swiggy.com/instamart/search?custom_back=true&query={query}",
        "relationship_status": "external_search_only",
    },
    {
        "id": "zomato",
        "label": "Zomato",
        "categories": {"food_fresh", "nutrition", "general_wellness"},
        "search_template": "https://www.zomato.com/search?q={query}",
        "relationship_status": "external_search_only",
    },
    {
        "id": "amazon_india",
        "label": "Amazon India",
        "categories": {"food_fresh", "eyewear", "fitness", "nutrition", "home_health", "baby_child", "general_wellness"},
        "search_template": "https://www.amazon.in/s?k={query}",
        "relationship_status": "external_search_only",
    },
    {
        "id": "flipkart",
        "label": "Flipkart",
        "categories": {"eyewear", "fitness", "nutrition", "home_health", "baby_child", "general_wellness"},
        "search_template": "https://www.flipkart.com/search?q={query}",
        "relationship_status": "external_search_only",
    },
    {
        "id": "meesho",
        "label": "Meesho",
        "categories": {"fitness", "home_health", "baby_child", "general_wellness"},
        "search_template": "https://www.meesho.com/search?q={query}",
        "relationship_status": "external_search_only",
    },
    {
        "id": "lenskart",
        "label": "Lenskart",
        "categories": {"eyewear"},
        "search_template": "https://www.lenskart.com/eyeglasses.html",
        "relationship_status": "external_catalog_handoff",
    },
    {
        "id": "healthkart",
        "label": "HealthKart",
        "categories": {"fitness", "nutrition", "general_wellness"},
        "search_template": "https://www.healthkart.com/",
        "relationship_status": "external_catalog_handoff",
    },
)


MEDICINE_TERMS = {
    "medicine", "medicines", "drug", "drugs", "tablet", "tablets", "capsule", "capsules",
    "antibiotic", "antibiotics", "injection", "insulin", "prescription medicine",
    "paracetamol", "acetaminophen", "ibuprofen", "aspirin", "cetirizine", "azithromycin",
    "amoxicillin", "metformin", "atorvastatin", "omeprazole", "pantoprazole",
}


COMMERCE_DISCOVERY_PRESETS = {
    "food_fresh": ("fresh fruit", "vegetables", "oats", "nuts", "healthy snacks"),
    "eyewear": ("eyeglass case", "sunglasses", "lens cleaning kit", "reading light"),
    "fitness": ("yoga mat", "resistance bands", "foam roller", "protein shaker", "exercise mat"),
    "nutrition": ("oats", "nuts and seeds", "protein shaker", "lunch box", "whole grain snacks"),
    "home_health": ("digital thermometer", "blood pressure monitor", "pulse oximeter", "weighing scale"),
    "baby_child": ("baby thermometer", "feeding bottle", "baby hygiene kit", "child water bottle"),
    "general_wellness": ("water bottle", "sleep mask", "first aid organizer", "fitness tracker"),
}


def commerce_discovery_presets(category="general_wellness"):
    selected = _category(category)
    return list(COMMERCE_DISCOVERY_PRESETS.get(selected, COMMERCE_DISCOVERY_PRESETS["general_wellness"]))


def commerce_category_catalog():
    return [deepcopy(item) for item in COMMERCE_CATEGORIES]


def _clean_query(value):
    return " ".join(str(value or "").strip().split())[:160]


def _category(value):
    requested = str(value or "general_wellness").strip().lower()
    allowed = {item["id"] for item in COMMERCE_CATEGORIES}
    return requested if requested in allowed else "general_wellness"


def _looks_like_medicine_query(query):
    lowered = query.lower()
    if any(term in lowered for term in MEDICINE_TERMS):
        return True
    # Dosage-like queries are routed into the pharmacy safety flow instead of
    # being treated as ordinary marketplace shopping intent.
    return bool(re.search(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|microgram|milligram)\b", lowered))


def search_health_products(query, category="general_wellness"):
    """Return deterministic merchant handoffs without claiming commerce state.

    No merchant is called from this function. URLs are external search/catalog
    handoffs only. Stock, price, suitability and referral attribution are never
    inferred from the presence of a link.
    """
    cleaned = _clean_query(query)
    selected = _category(category)
    category_meta = next(item for item in COMMERCE_CATEGORIES if item["id"] == selected)

    result = {
        "query": cleaned,
        "category": selected,
        "category_label": category_meta["label"],
        "safety_note": category_meta["safety_note"],
        "results": [],
        "external_only": True,
        "price_verified": False,
        "availability_verified": False,
        "clinical_recommendation": False,
        "affiliate_attribution_enabled": False,
        "affiliate_relationship_configured": False,
        "payment_execution_enabled": False,
        "medicine_query": False,
        "pharmacy_handoff": None,
        "presets": commerce_discovery_presets(selected),
        "merchant_count": 0,
        "truth_notice": (
            "These links open external merchant searches/catalogs. ZENDOC has not verified current stock, price, seller, "
            "medical suitability or delivery, and no affiliate/referral relationship is configured by this feature. "
            "Clinical need and product ranking must remain independent of commercial revenue."
        ),
    }

    if not cleaned:
        return result

    if _looks_like_medicine_query(cleaned):
        result["medicine_query"] = True
        result["pharmacy_handoff"] = f"/pharmacy?q={quote_plus(cleaned)}"
        result["truth_notice"] = (
            "Medicine searches stay inside ZENDOC's pharmacy safety flow. This commerce finder does not send prescription "
            "medicine queries to general marketplaces and does not diagnose, prescribe, substitute or change medicines."
        )
        return result

    encoded = quote_plus(cleaned)
    for merchant in MERCHANTS:
        if selected not in merchant["categories"]:
            continue
        item = deepcopy(merchant)
        item["url"] = merchant["search_template"].format(query=encoded)
        parsed = urlparse(item["url"])
        item["domain"] = parsed.netloc.replace("www.", "")
        item["affiliate_link"] = False
        item["stock_verified"] = False
        item["price_verified"] = False
        item.pop("search_template", None)
        item["categories"] = sorted(item["categories"])
        result["results"].append(item)
    result["merchant_count"] = len(result["results"])
    return result


def commerce_ethics_policy():
    """Machine-readable commercial guardrails for UI/tests/future integrations."""
    return {
        "medical_ranking_independent_of_commission": True,
        "affiliate_disclosure_required": True,
        "health_data_for_ad_targeting": False,
        "sell_clinical_records": False,
        "dark_patterns_allowed": False,
        "addictive_engagement_target": False,
        "minor_autoplay_infinite_scroll_default": False,
        "model_can_purchase": False,
        "model_can_change_prescription": False,
        "model_can_confirm_payment": False,
        "goal": "useful_repeat_care_habits_not_compulsive_screen_time",
    }
