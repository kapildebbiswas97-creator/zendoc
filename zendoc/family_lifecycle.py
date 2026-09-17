"""Deterministic family lifecycle and subscription-readiness helpers.

This module is intentionally non-clinical and non-transactional. It organizes
family-care journeys by explicit relationship/age context without diagnosing,
prescribing, changing permissions, or executing payments.

Pregnancy is never inferred from age, gender, relationship, or model output. A
pregnancy/postpartum journey can only be activated from an explicit user-selected
care context in a future persisted workflow.
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
        "subscription_available": False,
    },
    {
        "id": "remote_family",
        "label": "Remote Parent & Family",
        "audience": "Families living in different cities or countries",
        "summary": "Coordinate care tasks and visibility for parents or dependents without automatically granting write access to their health data.",
        "activation": "explicit_consent_required",
        "subscription_available": False,
    },
    {
        "id": "maternity_newborn",
        "label": "Pregnancy, Postpartum & Newborn",
        "audience": "People who explicitly choose a maternity/newborn care journey",
        "summary": "Organize appointments, records, care tasks and handoffs across pregnancy, postpartum and newborn care.",
        "activation": "user_selected_only",
        "subscription_available": False,
    },
    {
        "id": "child_growth",
        "label": "Child Growth & Pediatrics",
        "audience": "Children and adolescents",
        "summary": "Keep age-stage records, preventive follow-through, appointments and caregiver coordination together.",
        "activation": "age_context_only",
        "subscription_available": False,
    },
    {
        "id": "adult_continuity",
        "label": "Adult Continuity",
        "audience": "Adults managing care across providers",
        "summary": "Preserve portable longitudinal context, follow-up tasks and verified care actions through adult life stages.",
        "activation": "age_context_only",
        "subscription_available": False,
    },
    {
        "id": "older_adult_support",
        "label": "Older Adult Support",
        "audience": "Older adults and consented family caregivers",
        "summary": "Support remote coordination and care follow-through while keeping the patient in control of permissions.",
        "activation": "explicit_consent_required",
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
        "region": "Provider-dependent",
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
)


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
    """Normalize future explicit care context without inferring sensitive state."""
    value = str((member or {}).get("care_context") or "").strip().lower()
    allowed = {"pregnancy", "postpartum", "newborn"}
    return value if value in allowed else None


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
    if explicit_context in {"pregnancy", "postpartum", "newborn"}:
        programs.append("maternity_newborn")

    item["life_stage"] = stage
    item["care_program_ids"] = list(dict.fromkeys(programs))
    item["explicit_care_context"] = explicit_context
    item["pregnancy_inferred"] = False
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
        "methods": [deepcopy(method) for method in PAYMENT_METHODS],
        "truth_notice": (
            "No payment is taken from this family-care screen. A payment method becomes usable only after "
            "a real payment provider integration is configured, verified and audited. ZENDOC must never store card CVV, UPI PIN or banking passwords."
        ),
    }
