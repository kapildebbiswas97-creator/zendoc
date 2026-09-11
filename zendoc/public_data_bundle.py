"""Statewide West Bengal + India public-data acquisition bundles.

This module defines *scope and acquisition policy*, not scraped rows. The actual
source metadata remains in :mod:`zendoc.public_source_registry` and raw
artifacts are acquired through the existing immutable acquisition layer.

Nadia is retained only as a regression/quality-validation district. It is not
an acquisition boundary: the West Bengal bundle is explicitly FULL_STATE.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from .india_regions import INDIA_REGIONS
from .public_source_registry import get_public_ingestion_source
from .state_source_priorities import STATE_SOURCE_PRIORITIES


FULL_WEST_BENGAL = "FULL_WEST_BENGAL"
ALL_INDIA = "ALL_INDIA"

WEST_BENGAL_FULL_STATE_SOURCE_IDS = (
    "lgd",
    "data_gov_hospitals",
    "clinical_establishments",
    "wbhs_empanelled_hco",
    "swasthya_sathi_hospitals",
    "nabl_labs",
    "nabh_directory",
    "pmbjp_kendras",
    "data_gov_blood_banks",
    "eraktkosh",
    "data_gov_cghs_hospitals",
    "pmjay_hospitals",
    "cdsco_state_drug_control",
)

INDIA_PUBLIC_SOURCE_IDS = (
    "lgd",
    "data_gov_hospitals",
    "clinical_establishments",
    "nabh_directory",
    "nabl_labs",
    "pmbjp_kendras",
    "pmbjp_products",
    "data_gov_blood_banks",
    "eraktkosh",
    "pmjay_hospitals",
    "data_gov_cghs_hospitals",
    "nmc_imr",
    "nmc_medical_colleges",
    "inc_nursing_institutions",
    "pci_approved_institutions",
    "data_gov_hmis",
    "nppa_prices",
    "cdsco_approved_drugs",
    "cdsco_nlem",
    "cdsco_state_drug_control",
    "myscheme",
)

AUTHORIZED_ONLY_SOURCE_IDS = (
    "abdm_hfr",
    "abdm_hpr",
)

VALIDATION_ONLY_DISTRICTS = {
    "west_bengal": ("Nadia",),
    "assam": ("Dibrugarh",),
}


def acquisition_mode(source: dict) -> str:
    source_id = source["source_id"]
    if source_id in AUTHORIZED_ONLY_SOURCE_IDS:
        return "AUTHORIZED_ONLY"
    status = str(source.get("live_fetch_status") or "").upper()
    if any(token in status for token in ("DOWNLOAD", "API_OR_DOWNLOAD", "CSV_EXCEL", "PUBLISHED_LIST")):
        return "PUBLIC_ARTIFACT"
    return "PUBLIC_LOOKUP_SNAPSHOT"


def _source_descriptor(source_id: str, *, scope: str, priority: str) -> dict:
    source = get_public_ingestion_source(source_id)
    if not source:
        raise LookupError(f"Unknown public source in bundle: {source_id}")
    return {
        "source_id": source_id,
        "name": source["name"],
        "owner": source["owner"],
        "official_url": source["official_url"],
        "official_host": (urlsplit(source["official_url"]).hostname or "").lower(),
        "geography": source["geography"],
        "data_class": source["data_class"],
        "trust_level": source["trust_level"],
        "live_fetch_status": source["live_fetch_status"],
        "acquisition_mode": acquisition_mode(source),
        "priority": priority,
        "bundle_scope": scope,
        "personal_data_allowed": False,
        "notes": source["notes"],
    }


def west_bengal_bundle() -> dict:
    return {
        "bundle_id": "west_bengal_full_state_v1",
        "scope": FULL_WEST_BENGAL,
        "coverage_rule": "ALL_DISTRICTS_FROM_CURRENT_OFFICIAL_LGD_SNAPSHOT",
        "validation_districts": list(VALIDATION_ONLY_DISTRICTS["west_bengal"]),
        "validation_is_not_scope_limit": True,
        "sources": [
            _source_descriptor(source_id, scope=FULL_WEST_BENGAL, priority="P0")
            for source_id in WEST_BENGAL_FULL_STATE_SOURCE_IDS
        ],
        "truth_notice": (
            "West Bengal acquisition is statewide. Nadia is only a regression/quality-validation subset. "
            "Provider directories are not live availability, booking connectivity, or ZENDOC verification."
        ),
    }


def _state_enrichment_catalog() -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    national = set(INDIA_PUBLIC_SOURCE_IDS)
    for state_slug, profile in sorted(STATE_SOURCE_PRIORITIES.items()):
        descriptors = []
        for source_id in profile["official_directory_sources"]:
            if source_id in national or source_id in AUTHORIZED_ONLY_SOURCE_IDS:
                continue
            descriptor = _source_descriptor(source_id, scope=f"STATE:{state_slug.upper()}", priority="STATE_ENRICHMENT")
            descriptors.append(descriptor)
        if descriptors:
            result[state_slug] = descriptors
    return result


def india_bundle() -> dict:
    public_sources = [
        _source_descriptor(source_id, scope=ALL_INDIA, priority="P0" if source_id in {
            "lgd", "data_gov_hospitals", "clinical_establishments", "nabh_directory",
            "nabl_labs", "pmbjp_kendras", "data_gov_blood_banks", "pmjay_hospitals",
        } else "P1")
        for source_id in INDIA_PUBLIC_SOURCE_IDS
    ]
    authorized_sources = [
        _source_descriptor(source_id, scope=ALL_INDIA, priority="AUTHORIZED")
        for source_id in AUTHORIZED_ONLY_SOURCE_IDS
    ]
    return {
        "bundle_id": "india_public_official_v1",
        "scope": ALL_INDIA,
        "coverage_rule": "ALL_STATES_AND_UTS_FROM_CURRENT_OFFICIAL_LGD_SNAPSHOT",
        "region_count": len(INDIA_REGIONS),
        "regions": [dict(item) for item in INDIA_REGIONS],
        "sources": public_sources,
        "state_enrichment_sources": _state_enrichment_catalog(),
        "authorized_only_sources": authorized_sources,
        "truth_notice": (
            "Every State/UT receives the national baseline. Verified state-specific source families are catalogued as enrichments where ZENDOC already has an official source entry. "
            "Interactive/public lookup sources require dated permitted snapshots; authorized registries remain blocked until onboarding."
        ),
    }


def bundle_catalog() -> dict:
    return {
        "west_bengal": west_bengal_bundle(),
        "india": india_bundle(),
        "raw_data_git_policy": "DO_NOT_COMMIT_RAW_SNAPSHOTS_BY_DEFAULT",
    }
