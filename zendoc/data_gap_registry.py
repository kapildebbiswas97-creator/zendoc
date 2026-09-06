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


def list_data_gaps() -> list[dict]:
    return [gap.to_dict() for gap in DATA_GAPS.values()]


def get_data_gap(gap_id: str) -> dict | None:
    gap = DATA_GAPS.get(str(gap_id or "").strip().lower())
    return gap.to_dict() if gap else None
