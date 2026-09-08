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
    "delhi": {
        "official_directory_sources": [
            "lgd",
            "delhi_government_hospitals",
            "delhi_registered_nursing_homes",
            "clinical_establishments",
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
    "kerala": {
        "official_directory_sources": [
            "lgd",
            "kerala_health_institutions",
            "kerala_dhs_hospitals",
            "kerala_ehealth_hospitals",
            "clinical_establishments",
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
    "karnataka": {
        "official_directory_sources": [
            "lgd",
            "karnataka_health_infrastructure",
            "data_gov_hospitals",
            "clinical_establishments",
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
    "maharashtra": {
        "official_directory_sources": [
            "lgd",
            "maharashtra_dmer_hospitals",
            "data_gov_hospitals",
            "clinical_establishments",
            "nabl_labs",
            "nabh_directory",
            "pmbjp_kendras",
            "maharashtra_fda_drug_licenses",
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
    "uttar_pradesh": {
        "official_directory_sources": [
            "lgd",
            "up_nhm_health_facilities",
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


BASELINE_INDIA_DIRECTORY_SOURCES = [
    "lgd",
    "data_gov_hospitals",
    "clinical_establishments",
    "pmjay_hospitals",
    "nabl_labs",
    "nabh_directory",
    "pmbjp_kendras",
    "data_gov_blood_banks",
    "cdsco_state_drug_control",
]

BASELINE_LIVE_DATA_GAPS = [
    "doctor_live_slots",
    "pharmacy_live_stock",
    "pharmacy_actual_price",
    "lab_live_slots",
    "lab_actual_price",
    "hospital_bed_availability",
    "ambulance_live_dispatch",
]


def state_source_priority(state_slug: str) -> dict:
    key = str(state_slug or "").strip().lower().replace("-", "_").replace(" ", "_")
    profile = STATE_SOURCE_PRIORITIES.get(key)
    if not profile:
        return {
            "state_slug": key,
            "configured": False,
            "template": "INDIA_BASELINE_V1",
            "official_directory_sources": list(BASELINE_INDIA_DIRECTORY_SOURCES),
            "priority_districts": [],
            "live_data_gaps": list(BASELINE_LIVE_DATA_GAPS),
            "state_specific_sources": [],
            "truth_notice": (
                "Baseline national/central sources are enabled. State-specific portals are added only after official-source verification."
            ),
        }

    baseline = list(BASELINE_INDIA_DIRECTORY_SOURCES)
    state_sources = [
        source_id
        for source_id in profile["official_directory_sources"]
        if source_id not in baseline
    ]
    merged = []
    for source_id in profile["official_directory_sources"] + baseline:
        if source_id not in merged:
            merged.append(source_id)

    return {
        "state_slug": key,
        "configured": True,
        "template": "STATE_ENRICHED_V1",
        "official_directory_sources": merged,
        "priority_districts": list(profile["priority_districts"]),
        "live_data_gaps": list(profile["live_data_gaps"]),
        "state_specific_sources": state_sources,
        "truth_notice": (
            "National baseline sources plus verified state-specific sources. Directory coverage does not imply live provider operations."
        ),
    }
