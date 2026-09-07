"""ZENDOC data-gap and survey registry.

This module separates information that can be obtained from official/public
sources from operational facts that require direct provider surveys,
patient-consented research, or funded/authorized integrations.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class DataGap:
    gap_id: str
    category: str
    field_name: str
    public_availability: str
    preferred_collection: str
    sensitivity: str
    update_frequency: str
    notes: str

    def to_dict(self) -> dict:
        return asdict(self)


DATA_GAPS = {
    "doctor_live_slots": DataGap(
        "doctor_live_slots", "provider_operations", "doctor_live_appointment_slots",
        "GENERALLY_NOT_PUBLIC", "PROVIDER_INTEGRATION_OR_PROVIDER_SURVEY",
        "LOW", "REAL_TIME_OR_DAILY",
        "Directory data can identify a doctor or clinic, but live slots must come from the provider or booking system."
    ),
    "provider_wait_time": DataGap(
        "provider_wait_time", "provider_operations", "current_wait_time",
        "NOT_RELIABLY_PUBLIC", "PROVIDER_SURVEY_OR_LIVE_QUEUE_INTEGRATION",
        "LOW", "REAL_TIME",
        "Useful pilot metric; never infer from opening hours."
    ),
    "hospital_bed_availability": DataGap(
        "hospital_bed_availability", "provider_operations", "live_bed_availability",
        "LIMITED_AND_FRAGMENTED", "HOSPITAL_INTEGRATION_OR_AUTHORIZED_GOVERNMENT_FEED",
        "LOW", "REAL_TIME",
        "Static bed capacity is different from current vacant beds."
    ),
    "icu_bed_availability": DataGap(
        "icu_bed_availability", "provider_operations", "live_icu_bed_availability",
        "LIMITED_AND_FRAGMENTED", "HOSPITAL_INTEGRATION_OR_AUTHORIZED_GOVERNMENT_FEED",
        "LOW", "REAL_TIME",
        "Treat as high-stakes operational data and require timestamped authoritative source."
    ),
    "pharmacy_live_stock": DataGap(
        "pharmacy_live_stock", "pharmacy_operations", "medicine_sku_stock",
        "GENERALLY_NOT_PUBLIC", "PHARMACY_POS_INTEGRATION_OR_PROVIDER_SURVEY",
        "LOW", "REAL_TIME_OR_HOURLY",
        "Public pharmacy directories and medicine catalogs do not prove a medicine is currently in stock."
    ),
    "pharmacy_actual_price": DataGap(
        "pharmacy_actual_price", "pharmacy_operations", "transaction_price_and_discount",
        "GENERALLY_NOT_PUBLIC", "PHARMACY_INTEGRATION_OR_PROVIDER_SURVEY",
        "LOW", "DAILY",
        "NPPA/Jan Aushadhi can provide references or MRP; actual local selling price needs provider data."
    ),
    "lab_live_slots": DataGap(
        "lab_live_slots", "diagnostics_operations", "diagnostic_collection_slots",
        "GENERALLY_NOT_PUBLIC", "LAB_INTEGRATION_OR_PROVIDER_SURVEY",
        "LOW", "REAL_TIME_OR_DAILY",
        "Accreditation and lab directories do not imply collection-slot availability."
    ),
    "lab_actual_price": DataGap(
        "lab_actual_price", "diagnostics_operations", "diagnostic_test_transaction_price",
        "GENERALLY_NOT_PUBLIC", "LAB_INTEGRATION_OR_PROVIDER_SURVEY",
        "LOW", "DAILY_OR_WEEKLY",
        "Use timestamped provider-submitted offers; do not invent fallback prices."
    ),
    "ambulance_live_dispatch": DataGap(
        "ambulance_live_dispatch", "emergency_operations", "ambulance_location_eta_and_dispatch",
        "NOT_PUBLIC_FOR_GENERAL_INTEGRATION", "AUTHORIZED_AMBULANCE_PARTNER_OR_GOVERNMENT_INTEGRATION",
        "LOW", "REAL_TIME",
        "Emergency intake may be supported, but real dispatch/ETA must come from an authorized dispatcher."
    ),
    "provider_response_time": DataGap(
        "provider_response_time", "pilot_metrics", "provider_response_time",
        "NOT_PUBLIC", "MEASURE_FROM_ZENDOC_PROVIDER_WORKFLOW",
        "LOW", "CONTINUOUS",
        "Collect automatically from request/acknowledgement timestamps during pilot."
    ),
    "provider_service_radius": DataGap(
        "provider_service_radius", "provider_operations", "home_service_or_delivery_radius",
        "OCCASIONALLY_PUBLIC_BUT_UNRELIABLE", "PROVIDER_SURVEY_AND_VERIFICATION",
        "LOW", "MONTHLY_OR_ON_CHANGE",
        "Especially useful for pharmacies, home health, labs and transport providers."
    ),
    "provider_languages": DataGap(
        "provider_languages", "provider_profile", "languages_supported",
        "PARTIALLY_PUBLIC", "PROVIDER_SURVEY_AND_PROFILE_ONBOARDING",
        "LOW", "ON_CHANGE",
        "Important for multilingual care routing; let providers self-report and patients validate experience."
    ),
    "provider_accessibility": DataGap(
        "provider_accessibility", "provider_profile", "wheelchair_access_and_accessibility",
        "PARTIALLY_PUBLIC", "PROVIDER_SURVEY_AND_FIELD_VERIFICATION",
        "LOW", "ON_CHANGE",
        "Collect structured accessibility facts; avoid vague labels."
    ),
    "provider_payment_modes": DataGap(
        "provider_payment_modes", "provider_operations", "accepted_payment_modes",
        "PARTIALLY_PUBLIC", "PROVIDER_SURVEY",
        "LOW", "MONTHLY_OR_ON_CHANGE",
        "Do not infer cashless/insurance support from general scheme empanelment."
    ),
    "patient_satisfaction": DataGap(
        "patient_satisfaction", "research", "patient_experience_and_satisfaction",
        "NOT_PUBLIC_AT_ZENDOC_LEVEL", "PATIENT_CONSENTED_SURVEY_AFTER_VERIFIED_INTERACTION",
        "SENSITIVE", "AFTER_INTERACTION",
        "Collect only with consent and only after a real interaction to reduce fabricated reviews."
    ),
    "care_barriers": DataGap(
        "care_barriers", "research", "patient_access_barriers",
        "AGGREGATES_EXIST_BUT_LOCAL_DETAIL_MISSING", "ANONYMOUS_OR_CONSENTED_PATIENT_SURVEY",
        "SENSITIVE", "PERIODIC",
        "Ask about travel, cost, language, digital access and wait-time barriers; avoid unnecessary diagnosis data."
    ),
    "medicine_unavailability_experience": DataGap(
        "medicine_unavailability_experience", "research", "medicine_access_gaps",
        "NOT_PUBLIC_AT_LOCAL_REAL_TIME_LEVEL", "PATIENT_AND_PHARMACY_SURVEY",
        "SENSITIVE", "PERIODIC",
        "Useful for future inventory planning, but do not collect full prescriptions unless necessary and consented."
    ),
    "diagnostic_delay_experience": DataGap(
        "diagnostic_delay_experience", "research", "diagnostic_access_delays",
        "NOT_PUBLIC_AT_LOCAL_REAL_TIME_LEVEL", "PATIENT_AND_LAB_SURVEY",
        "SENSITIVE", "PERIODIC",
        "Collect delay reasons and broad categories rather than unnecessary clinical details."
    ),
    "scheme_outcome": DataGap(
        "scheme_outcome", "carefin", "actual_scheme_eligibility_approval_or_payment",
        "PRIVATE_OR_AUTHORIZED_ONLY", "AUTHORIZED_PARTNER_RESPONSE_OR_USER_UPLOADED_EVIDENCE_WITH_CONSENT",
        "HIGH", "EVENT_BASED",
        "CareFin discovery must never convert into confirmed eligibility without authoritative evidence."
    ),
    "claims_and_insurance": DataGap(
        "claims_and_insurance", "financial_health", "insurance_claims_and_policy_details",
        "PRIVATE", "AUTHORIZED_INSURER_INTEGRATION_OR_USER_CONSENTED_UPLOAD",
        "HIGH", "EVENT_BASED",
        "Do not attempt public scraping. Store minimum necessary fields and explicit provenance."
    ),
    "personal_health_records": DataGap(
        "personal_health_records", "clinical", "individual_medical_history",
        "PRIVATE", "PATIENT_CONSENTED_UPLOAD_OR_AUTHORIZED_PROVIDER_ABDM_WORKFLOW",
        "HIGH", "EVENT_BASED",
        "Never collect through public-source ingestion."
    ),
}



COLLECTION_METADATA = {
    "doctor_live_slots": {
        "tier": "PROVIDER_SURVEY_OR_INTEGRATION",
        "priority": "P0",
        "pilot_owner": "provider_onboarding",
        "minimum_fields": ["provider_id", "date", "slot_start", "slot_end", "consultation_type", "confirmed_at"],
        "funding_dependency": "NONE_FOR_SURVEY",
    },
    "provider_wait_time": {
        "tier": "AUTOMATIC_OR_PROVIDER_SURVEY",
        "priority": "P1",
        "pilot_owner": "provider_operations",
        "minimum_fields": ["provider_id", "queue_observed_at", "estimated_wait_minutes", "source"],
        "funding_dependency": "NONE_FOR_PILOT",
    },
    "hospital_bed_availability": {
        "tier": "AUTHORIZED_PARTNER_FEED",
        "priority": "P1",
        "pilot_owner": "hospital_integration",
        "minimum_fields": ["hospital_id", "bed_type", "available_count", "confirmed_at", "source_reference"],
        "funding_dependency": "PARTNER_OR_FUTURE_INTEGRATION",
    },
    "icu_bed_availability": {
        "tier": "AUTHORIZED_PARTNER_FEED",
        "priority": "P0",
        "pilot_owner": "hospital_integration",
        "minimum_fields": ["hospital_id", "icu_type", "available_count", "confirmed_at", "source_reference"],
        "funding_dependency": "PARTNER_OR_FUTURE_INTEGRATION",
    },
    "pharmacy_live_stock": {
        "tier": "PROVIDER_SURVEY_OR_INTEGRATION",
        "priority": "P0",
        "pilot_owner": "pharmacy_onboarding",
        "minimum_fields": ["pharmacy_id", "sku_id", "quantity_available", "stock_status", "observed_at"],
        "funding_dependency": "NONE_FOR_MANUAL_PILOT",
    },
    "pharmacy_actual_price": {
        "tier": "PROVIDER_SURVEY_OR_INTEGRATION",
        "priority": "P0",
        "pilot_owner": "pharmacy_onboarding",
        "minimum_fields": ["pharmacy_id", "sku_id", "price_inr", "discount_percent", "observed_at"],
        "funding_dependency": "NONE_FOR_MANUAL_PILOT",
    },
    "lab_live_slots": {
        "tier": "PROVIDER_SURVEY_OR_INTEGRATION",
        "priority": "P0",
        "pilot_owner": "diagnostic_onboarding",
        "minimum_fields": ["lab_id", "test_id", "date", "slot_start", "slot_end", "confirmed_at"],
        "funding_dependency": "NONE_FOR_MANUAL_PILOT",
    },
    "lab_actual_price": {
        "tier": "PROVIDER_SURVEY_OR_INTEGRATION",
        "priority": "P0",
        "pilot_owner": "diagnostic_onboarding",
        "minimum_fields": ["lab_id", "test_id", "price_inr", "home_collection_fee_inr", "observed_at"],
        "funding_dependency": "NONE_FOR_MANUAL_PILOT",
    },
    "ambulance_live_dispatch": {
        "tier": "AUTHORIZED_PARTNER_FEED",
        "priority": "P0",
        "pilot_owner": "transport_integration",
        "minimum_fields": ["provider_id", "request_id", "dispatch_status", "eta_minutes", "confirmed_at"],
        "funding_dependency": "PARTNER_REQUIRED",
    },
    "provider_response_time": {
        "tier": "AUTOMATIC_ZENDOC_MEASUREMENT",
        "priority": "P0",
        "pilot_owner": "pilot_analytics",
        "minimum_fields": ["request_created_at", "provider_response_at", "provider_id", "workflow_type"],
        "funding_dependency": "NONE",
    },
    "provider_service_radius": {
        "tier": "PROVIDER_SURVEY",
        "priority": "P1",
        "pilot_owner": "provider_onboarding",
        "minimum_fields": ["provider_id", "service_type", "radius_km", "verified_at"],
        "funding_dependency": "NONE",
    },
    "provider_languages": {
        "tier": "PROVIDER_SURVEY",
        "priority": "P1",
        "pilot_owner": "provider_onboarding",
        "minimum_fields": ["provider_id", "languages", "self_reported_at"],
        "funding_dependency": "NONE",
    },
    "provider_accessibility": {
        "tier": "PROVIDER_SURVEY_THEN_FIELD_VERIFY",
        "priority": "P2",
        "pilot_owner": "provider_onboarding",
        "minimum_fields": ["provider_id", "wheelchair_access", "accessible_toilet", "lift_available", "verified_at"],
        "funding_dependency": "FIELD_VERIFICATION_LATER",
    },
    "provider_payment_modes": {
        "tier": "PROVIDER_SURVEY",
        "priority": "P1",
        "pilot_owner": "provider_onboarding",
        "minimum_fields": ["provider_id", "payment_modes", "cashless_claimed", "verified_at"],
        "funding_dependency": "NONE",
    },
    "patient_satisfaction": {
        "tier": "PATIENT_CONSENTED_SURVEY",
        "priority": "P1",
        "pilot_owner": "verified_reviews",
        "minimum_fields": ["interaction_type", "interaction_id", "rating", "consented_at"],
        "funding_dependency": "NONE",
    },
    "care_barriers": {
        "tier": "ANONYMOUS_OR_CONSENTED_SURVEY",
        "priority": "P1",
        "pilot_owner": "research",
        "minimum_fields": ["district", "barrier_categories", "travel_minutes_band", "cost_band", "language_barrier", "digital_access_barrier"],
        "funding_dependency": "NONE_FOR_DIGITAL_SURVEY",
    },
    "medicine_unavailability_experience": {
        "tier": "PATIENT_AND_PROVIDER_SURVEY",
        "priority": "P1",
        "pilot_owner": "research",
        "minimum_fields": ["district", "medicine_category", "unavailable_count_band", "alternative_distance_band"],
        "funding_dependency": "NONE_FOR_DIGITAL_SURVEY",
    },
    "diagnostic_delay_experience": {
        "tier": "PATIENT_AND_PROVIDER_SURVEY",
        "priority": "P1",
        "pilot_owner": "research",
        "minimum_fields": ["district", "test_category", "delay_days_band", "delay_reason"],
        "funding_dependency": "NONE_FOR_DIGITAL_SURVEY",
    },
    "scheme_outcome": {
        "tier": "AUTHORIZED_PARTNER_OR_USER_EVIDENCE",
        "priority": "P1",
        "pilot_owner": "carefin",
        "minimum_fields": ["source_id", "state", "evidence_type", "evidence_reference", "confirmed_at"],
        "funding_dependency": "PARTNER_OR_AUTHORIZED_WORKFLOW",
    },
    "claims_and_insurance": {
        "tier": "AUTHORIZED_PARTNER_OR_USER_EVIDENCE",
        "priority": "P2",
        "pilot_owner": "carefin",
        "minimum_fields": ["payer", "claim_reference", "status", "confirmed_at"],
        "funding_dependency": "PARTNER_REQUIRED_FOR_SCALE",
    },
    "personal_health_records": {
        "tier": "PATIENT_CONSENTED_OR_AUTHORIZED_PROVIDER",
        "priority": "P0",
        "pilot_owner": "health_memory",
        "minimum_fields": ["patient_id", "record_type", "source", "recorded_at", "consent_scope"],
        "funding_dependency": "NONE_FOR_USER_UPLOAD_PARTNER_FOR_SCALE",
    },
}


def list_data_gaps() -> list[dict]:
    result = []
    for gap_id, gap in DATA_GAPS.items():
        item = gap.to_dict()
        item.update(COLLECTION_METADATA.get(gap_id, {}))
        result.append(item)
    return result


def build_collection_plan() -> dict:
    gaps = list_data_gaps()
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    gaps.sort(key=lambda item: (order.get(item.get("priority"), 9), item["gap_id"]))

    by_tier = {}
    for item in gaps:
        by_tier.setdefault(item.get("tier", "UNCLASSIFIED"), []).append(item["gap_id"])

    p0 = [item for item in gaps if item.get("priority") == "P0"]
    no_capital_now = [
        item["gap_id"]
        for item in gaps
        if item.get("funding_dependency") in {"NONE", "NONE_FOR_SURVEY", "NONE_FOR_PILOT", "NONE_FOR_MANUAL_PILOT", "NONE_FOR_DIGITAL_SURVEY", "NONE_FOR_USER_UPLOAD_PARTNER_FOR_SCALE"}
    ]
    partner_required = [
        item["gap_id"]
        for item in gaps
        if "PARTNER" in str(item.get("funding_dependency") or "")
        or item.get("tier") == "AUTHORIZED_PARTNER_FEED"
    ]

    return {
        "priority_zero": p0,
        "no_capital_collect_now": no_capital_now,
        "partner_or_authorized_integration_required": partner_required,
        "by_collection_tier": by_tier,
        "survey_design_rule": (
            "Collect the minimum operational fields needed for the stated purpose. "
            "Do not collect diagnosis, prescription text, identity, financial details, or other sensitive data "
            "when an aggregate/non-clinical field is sufficient."
        ),
    }


def get_data_gap(gap_id: str) -> dict | None:
    key = str(gap_id or "").strip().lower()
    gap = DATA_GAPS.get(key)
    if not gap:
        return None
    item = gap.to_dict()
    item.update(COLLECTION_METADATA.get(key, {}))
    return item

