"""West Bengal-specific official public source metadata under active validation.

These sources are kept separate from the legacy central registry so the
statewide acquisition work can progress additively without rewriting the
existing registry. They are official portals, but no stable verified bulk API
is assumed.
"""
from __future__ import annotations


WEST_BENGAL_EXTRA_SOURCES = {
    "wb_clinical_establishments": {
        "source_id": "wb_clinical_establishments",
        "name": "West Bengal Clinical Establishment Portal",
        "owner": "Health & Family Welfare Department, Government of West Bengal",
        "official_url": "https://ce.wbhealth.gov.in/WBDHFW/",
        "data_class": "official_state_clinical_establishment_portal",
        "geography": "WEST_BENGAL",
        "ingestion_types": ["public_healthcare_entities"],
        "trust_level": "OFFICIAL_PUBLIC_DATA",
        "live_fetch_status": "PUBLIC_LOOKUP_AND_REGISTRATION_PORTAL_NO_VERIFIED_BULK_API",
        "personal_data_allowed": False,
        "notes": (
            "Official Clinical Establishment workflow/search context for private health facilities and service categories. "
            "Use only publicly exposed facility/licence facts through a permitted lookup/export path; do not scrape authenticated applicant data."
        ),
    },
    "wb_drug_license_verification": {
        "source_id": "wb_drug_license_verification",
        "name": "West Bengal E-Vesoj Drug Licence Verification",
        "owner": "Directorate of Drugs Control, Health & Family Welfare Department, Government of West Bengal",
        "official_url": "https://evesoj.wb.gov.in/WBDL/welcome.jsp",
        "data_class": "official_state_drug_license_verification_portal",
        "geography": "WEST_BENGAL",
        "ingestion_types": ["public_healthcare_entities"],
        "trust_level": "OFFICIAL_PUBLIC_DATA",
        "live_fetch_status": "PUBLIC_LICENSE_VERIFICATION_NO_VERIFIED_BULK_API",
        "personal_data_allowed": False,
        "notes": (
            "Portal exposes public verification by licence number/establishment name. Use for evidence-based pharmacy/licence verification only; "
            "a licence is not proof of current opening hours, medicine stock, selling price or ZENDOC connectivity."
        ),
    },
}


def get_west_bengal_extra_source(source_id: str) -> dict | None:
    item = WEST_BENGAL_EXTRA_SOURCES.get(str(source_id or "").strip().lower())
    return dict(item) if item else None
