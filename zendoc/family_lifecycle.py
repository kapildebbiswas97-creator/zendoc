"""Deterministic family lifecycle and subscription-readiness helpers.

This module is intentionally non-clinical and non-transactional. It organizes
family-care journeys by explicit relationship/age context without diagnosing,
prescribing, changing permissions, or executing payments.

Pregnancy, fertility/family-building, postpartum, newborn and menopause/midlife
journeys are never inferred from age, gender, relationship, model output or
medical records. Sensitive care contexts can only be activated by an explicit
user selection in a future persisted workflow.
"""
from __future__ import annotations

from copy import deepcopy


AGE_BANDS = (
    {"id": "early_childhood", "min_age": 0, "max_age": 2, "label": "Early childhood (0–2)", "focus": "Newborn, infant and toddler continuity; exact milestone timing requires date of birth."},
    {"id": "preschool", "min_age": 3, "max_age": 5, "label": "Preschool (3–5)", "focus": "Growth, development, vaccination records and everyday care coordination."},
    {"id": "child", "min_age": 6, "max_age": 11, "label": "Child (6–11)", "focus": "School-age preventive care, records, appointments and family coordination."},
    {"id": "adolescent", "min_age": 12, "max_age": 17, "label": "Adolescent (12–17)", "focus": "Age-appropriate preventive care with privacy and guardian boundaries."},
    {"id": "young_adult", "min_age": 18, "max_age": 39, "label": "Young adult (18–39)", "focus": "Portable records, preventive care, appointments and continuity across providers."},
    {"id": "midlife", "min_age": 40, "max_age": 64, "label": "Midlife (40–64)", "focus": "Preventive follow-through, chronic-care coordination and longitudinal records."},
    {"id": "older_adult", "min_age": 65, "max_age": 150, "label": "Older adult (65+)", "focus": "Remote-family coordination, appointments, care tasks and consent-scoped visibility."},
)


FAMILY_PROGRAMS = (
    {
        "id": "family_essentials",
        "label": "Family Essentials",
        "audience": "Households coordinating everyday healthcare",
        "summary": "One family care network for appointments, records, reminders and consent-scoped coordination.",
        "activation": "available_as_care_category",
        "clinical_scope": "care_navigation_only",
        "subscription_available": False,
    },
    {
        "id": "remote_family",
        "label": "Remote Parent & Family",
        "audience": "Families living in different cities or countries",
        "summary": "Coordinate care tasks and visibility for parents or dependents without automatically granting write access to their health data.",
        "activation": "explicit_consent_required",
        "clinical_scope": "care_navigation_only",
        "subscription_available": False,
    },
    {
        "id": "family_building",
        "label": "Fertility & Family Building",
        "audience": "People who explicitly choose a family-building journey",
        "summary": "Organize records, appointments, verified-provider discovery and follow-through for family-building care without inferring fertility status or treatment needs.",
        "activation": "user_selected_only",
        "clinical_scope": "care_navigation_only",
        "subscription_available": False,
    },
    {
        "id": "maternity_newborn",
        "label": "Pregnancy, Postpartum & Newborn",
        "audience": "People who explicitly choose a maternity/newborn care journey",
        "summary": "Organize appointments, records, care tasks and handoffs across pregnancy, postpartum and newborn care.",
        "activation": "user_selected_only",
        "clinical_scope": "care_navigation_only",
        "subscription_available": False,
    },
    {
        "id": "child_growth",
        "label": "Child Growth & Pediatrics",
        "audience": "Children and adolescents",
        "summary": "Keep age-stage records, preventive follow-through, appointments and caregiver coordination together.",
        "activation": "age_context_only",
        "clinical_scope": "care_navigation_only",
        "subscription_available": False,
    },
    {
        "id": "adult_continuity",
        "label": "Adult Continuity",
        "audience": "Adults managing care across providers",
        "summary": "Preserve portable longitudinal context, follow-up tasks and verified care actions through adult life stages.",
        "activation": "age_context_only",
        "clinical_scope": "care_navigation_only",
        "subscription_available": False,
    },
    {
        "id": "menopause_midlife",
        "label": "Menopause & Midlife",
        "audience": "People who explicitly choose a menopause or midlife-health journey",
        "summary": "Organize records, appointments, questions and follow-up across midlife care without inferring menopause status or recommending hormone treatment.",
        "activation": "user_selected_only",
        "clinical_scope": "care_navigation_only",
        "subscription_available": False,
    },
    {
        "id": "older_adult_support",
        "label": "Older Adult Support",
        "audience": "Older adults and consented family caregivers",
        "summary": "Support remote coordination and care follow-through while keeping the patient in control of permissions.",
        "activation": "explicit_consent_required",
        "clinical_scope": "care_navigation_only",
        "subscription_available": False,
    },
)


PAYMENT_METHODS = (
    {
        "id": "upi",
        "label": "UPI",
        "region": "India",
        "integration_status": "provider_required",
        "collect_in_zendoc": False,
    },
    {
        "id": "card",
        "label": "Credit / debit card",
        "region": "Domestic or international only if a future gateway supports it",
        "integration_status": "provider_required",
        "collect_in_zendoc": False,
    },
    {
        "id": "netbanking",
        "label": "Net banking",
        "region": "India",
        "integration_status": "provider_required",
        "collect_in_zendoc": False,
    },
    {
        "id": "wallet",
        "label": "Supported wallet",
        "region": "Provider-dependent",
        "integration_status": "provider_required",
        "collect_in_zendoc": False,
    },
    {
        "id": "employer_or_insurer",
        "label": "Employer / insurer benefit",
        "region": "Coverage-dependent",
        "integration_status": "authoritative_coverage_confirmation_required",
        "collect_in_zendoc": False,
    },
    {
        "id": "provider_direct",
        "label": "Pay provider directly",
        "region": "Provider-dependent",
        "integration_status": "external_provider_handoff_only",
        "collect_in_zendoc": False,
    },
)


EXPLICIT_CARE_CONTEXTS = {
    "family_building": "family_building",
    "pregnancy": "maternity_newborn",
    "postpartum": "maternity_newborn",
    "newborn": "maternity_newborn",
    "menopause": "menopause_midlife",
    "midlife_health": "menopause_midlife",
}


def age_band(age):
    """Return a product lifecycle band from an integer age, or unknown.

    This is categorization only. It is not a medical assessment and it does not
    generate screening, diagnosis or treatment decisions.
    """
    if age in (None, ""):
        return {"id": "unknown", "label": "Age stage not set", "focus": "Add age context only if appropriate and consented."}
    try:
        value = int(age)
    except (TypeError, ValueError):
        return {"id": "unknown", "label": "Age stage not set", "focus": "Age value is unavailable or invalid."}
    if value < 0 or value > 150:
        return {"id": "unknown", "label": "Age stage not set", "focus": "Age value is outside the supported range."}
    for band in AGE_BANDS:
        if band["min_age"] <= value <= band["max_age"]:
            return deepcopy(band)
    return {"id": "unknown", "label": "Age stage not set", "focus": "Age context is unavailable."}


def _explicit_care_context(member):
    """Normalize explicit care context without inferring sensitive state."""
    value = str((member or {}).get("care_context") or "").strip().lower()
    return value if value in EXPLICIT_CARE_CONTEXTS else None


def member_lifecycle(member):
    """Enrich a family-member mapping with deterministic lifecycle metadata."""
    item = dict(member or {})
    stage = age_band(item.get("age"))
    relationship = str(item.get("relationship") or "other").strip().lower()
    explicit_context = _explicit_care_context(item)

    programs = ["family_essentials"]
    if relationship in {"father", "mother", "grandfather", "grandmother", "guardian"} or bool(item.get("is_remote_parent")):
        programs.append("remote_family")
    if stage["id"] in {"early_childhood", "preschool", "child", "adolescent"}:
        programs.append("child_growth")
    elif stage["id"] in {"young_adult", "midlife"}:
        programs.append("adult_continuity")
    elif stage["id"] == "older_adult":
        programs.append("older_adult_support")
    if explicit_context:
        programs.append(EXPLICIT_CARE_CONTEXTS[explicit_context])

    item["life_stage"] = stage
    item["care_program_ids"] = list(dict.fromkeys(programs))
    item["explicit_care_context"] = explicit_context
    item["pregnancy_inferred"] = False
    item["sensitive_context_inferred"] = False
    return item


def enrich_family_members(members):
    return [member_lifecycle(member) for member in (members or [])]


def family_program_catalog():
    return [deepcopy(program) for program in FAMILY_PROGRAMS]


def payment_readiness():
    """Describe supported payment shapes without pretending billing is live."""
    return {
        "payment_execution_enabled": False,
        "billing_provider": None,
        "status": "not_configured",
        "remote_family_sponsor_payment_enabled": False,
        "cross_border_settlement_enabled": False,
        "stored_sensitive_payment_credentials": False,
        "methods": [deepcopy(method) for method in PAYMENT_METHODS],
        "truth_notice": (
            "No payment is taken from this family-care screen. A payment method becomes usable only after "
            "a real payment provider integration is configured, verified and audited. Cross-border family payment "
            "requires gateway-supported currency, compliance and payer authorization. ZENDOC must never store card CVV, "
            "UPI PIN or banking passwords, and model output must never execute or confirm a payment."
        ),
    }
