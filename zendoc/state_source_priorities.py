"""Priority source stacks for operational geography expansion."""
from __future__ import annotations

STATE_SOURCE_PRIORITIES = {
    "west_bengal": {
        "official_directory_sources": [
            "lgd",
            "data_gov_hospitals",
            "clinical_establishments",
            "wbhs_empanelled_hco",
            "swasthya_sathi_hospitals",
            "nabl_labs",
            "nabh_directory",
            "pmbjp_kendras",
            "cdsco_state_drug_control",
        ],
        "priority_districts": ["Nadia"],
        "live_data_gaps": [
            "doctor_live_slots",
            "pharmacy_live_stock",
            "pharmacy_actual_price",
            "lab_live_slots",
            "lab_actual_price",
            "hospital_bed_availability",
            "ambulance_live_dispatch",
        ],
    },
    "assam": {
        "official_directory_sources": [
            "lgd",
            "assam_health_institutes",
            "assam_first_referral_units",
            "assam_medical_colleges",
            "data_gov_hospitals",
            "clinical_establishments",
            "nabl_labs",
            "nabh_directory",
            "pmbjp_kendras",
            "cdsco_state_drug_control",
        ],
        "priority_districts": ["Dibrugarh"],
        "live_data_gaps": [
            "doctor_live_slots",
            "pharmacy_live_stock",
            "pharmacy_actual_price",
            "lab_live_slots",
            "lab_actual_price",
            "hospital_bed_availability",
            "ambulance_live_dispatch",
        ],
    },
    "uttar_pradesh": {
        "official_directory_sources": [
            "lgd",
            "data_gov_hospitals",
            "clinical_establishments",
            "pmjay_hospitals",
            "nabl_labs",
            "nabh_directory",
            "pmbjp_kendras",
            "cdsco_state_drug_control",
        ],
        "priority_districts": [],
        "live_data_gaps": [
            "doctor_live_slots",
            "pharmacy_live_stock",
            "pharmacy_actual_price",
            "lab_live_slots",
            "lab_actual_price",
            "hospital_bed_availability",
            "ambulance_live_dispatch",
        ],
    },
}


def state_source_priority(state_slug: str) -> dict:
    key = str(state_slug or "").strip().lower().replace("-", "_").replace(" ", "_")
    profile = STATE_SOURCE_PRIORITIES.get(key)
    if not profile:
        return {
            "state_slug": key,
            "configured": False,
            "official_directory_sources": ["lgd", "data_gov_hospitals", "clinical_establishments"],
            "priority_districts": [],
            "live_data_gaps": [
                "doctor_live_slots",
                "pharmacy_live_stock",
                "lab_live_slots",
                "hospital_bed_availability",
                "ambulance_live_dispatch",
            ],
        }
    return {"state_slug": key, "configured": True, **profile}
