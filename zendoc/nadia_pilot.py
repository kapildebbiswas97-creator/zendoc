"""Conservative source plan and quality gate for the Nadia pilot.

The plan describes what can be collected through a permitted snapshot or
lookup.  It does not claim that a source was downloaded or that a provider is
verified.  Actual counts come only from an acquisition/ingestion report.
"""
from __future__ import annotations

from typing import Any

from .data_gap_registry import get_data_gap
from .public_source_registry import get_public_ingestion_source


NADIA_SOURCE_PLAN: tuple[dict[str, Any], ...] = (
    {
        "source_id": "lgd",
        "classification": "DOWNLOADABLE_SNAPSHOT",
        "data_classes": ["canonical geography"],
        "scope": "West Bengal and Nadia administrative hierarchy",
        "status": "NOT_ACQUIRED",
        "notes": "Use an exact dated LGD export with stable identifiers and parent references.",
    },
    {
        "source_id": "data_gov_hospitals",
        "classification": "DOWNLOADABLE_SNAPSHOT",
        "data_classes": ["public hospitals and health facilities"],
        "scope": "Filter normalized rows to West Bengal and Nadia",
        "status": "NOT_ACQUIRED",
        "notes": "Use only a permitted dataset artifact; preserve source row identifiers and freshness.",
    },
    {
        "source_id": "wbhs_empanelled_hco",
        "classification": "MANUAL_VERIFICATION_REQUIRED",
        "data_classes": ["scheme-empanelled facilities"],
        "scope": "West Bengal directory, Nadia rows where published",
        "status": "NOT_ACQUIRED",
        "notes": "Confirm the current download/usage path before retaining an artifact.",
    },
    {
        "source_id": "swasthya_sathi_hospitals",
        "classification": "PUBLIC_LOOKUP_ONLY",
        "data_classes": ["scheme-empanelled facilities"],
        "scope": "West Bengal lookup results",
        "status": "LOOKUP_ONLY",
        "notes": "No bulk import is assumed; do not scrape the lookup into a permanent provider table.",
    },
    {
        "source_id": "pmbjp_kendras",
        "classification": "PUBLIC_LOOKUP_ONLY",
        "data_classes": ["Jan Aushadhi pharmacy locations"],
        "scope": "Nadia discovery when a public result is returned",
        "status": "LOOKUP_ONLY",
        "notes": "A location listing does not imply live stock, price, or ZENDOC connectivity.",
    },
    {
        "source_id": "nabl_labs",
        "classification": "PUBLIC_LOOKUP_ONLY",
        "data_classes": ["laboratory accreditation lookup"],
        "scope": "Nadia facilities where a public lookup exists",
        "status": "LOOKUP_ONLY",
        "notes": "Accreditation is a sourced external fact, not automatic ZENDOC verification.",
    },
    {
        "source_id": "data_gov_blood_banks",
        "classification": "DOWNLOADABLE_SNAPSHOT",
        "data_classes": ["blood-centre directory"],
        "scope": "Filter normalized rows to Nadia",
        "status": "NOT_ACQUIRED",
        "notes": "Directory metadata is separate from time-sensitive blood availability.",
    },
    {
        "source_id": "cdsco_state_drug_control",
        "classification": "PUBLIC_LOOKUP_ONLY",
        "data_classes": ["pharmacy licensing discovery"],
        "scope": "West Bengal regulator lookup",
        "status": "LOOKUP_ONLY",
        "notes": "A licence result does not prove current stock, opening hours, or booking connectivity.",
    },
    {
        "source_id": "nmc_imr",
        "classification": "PUBLIC_LOOKUP_ONLY",
        "data_classes": ["professional registration lookup"],
        "scope": "Individual doctor evidence checks only",
        "status": "LOOKUP_ONLY",
        "notes": "Do not bulk-copy a professional roster or mark a ZENDOC profile verified automatically.",
    },
)


def nadia_source_plan() -> list[dict[str, Any]]:
    """Return the plan with registry metadata and explicit data-gap links."""
    result = []
    for item in NADIA_SOURCE_PLAN:
        source = get_public_ingestion_source(item["source_id"])
        enriched = {**item}
        if source:
            enriched["source_name"] = source["name"]
            enriched["official_url"] = source["official_url"]
            enriched["trust_level"] = source["trust_level"]
            enriched["live_fetch_status"] = source["live_fetch_status"]
        result.append(enriched)
    return result


def nadia_data_quality_gate(report: dict[str, Any]) -> dict[str, Any]:
    """Evaluate required pilot checks without turning missing data into green."""
    report = report if isinstance(report, dict) else {}
    checks = {
        "SOURCE_VALID": report.get("source_valid") is True,
        "SNAPSHOT_HASHED": bool(report.get("snapshot_uid") and report.get("file_sha256")),
        "LICENSE_OR_USAGE_RECORDED": bool(report.get("usage_basis") and report.get("license_or_terms")),
        "SCHEMA_MAPPED": report.get("schema_mapped") is True,
        "DRY_RUN": report.get("dry_run") is True,
        "GEOGRAPHY_VALIDATED": report.get("geography_validated") is True,
        "DUPLICATES_REVIEWED": report.get("duplicates_reviewed") is True,
        "PROVENANCE_PERSISTED": report.get("provenance_persisted") is True,
        "NO_FAKE_VERIFICATION": report.get("no_fake_verification") is True,
        "NO_FAKE_AVAILABILITY": report.get("no_fake_availability") is True,
        "SECURITY_TESTS": report.get("security_tests") is True,
        "POSTGRESQL_TESTS": report.get("postgresql_tests") is True,
    }
    failed = [key for key, value in checks.items() if not value]
    return {
        "status": "PASS" if not failed else "BLOCKED",
        "checks": checks,
        "failed_checks": failed,
        "record_counts": {
            "source": int(report.get("source_record_count") or 0),
            "mapped": int(report.get("mapped_record_count") or 0),
            "accepted": int(report.get("accepted_count") or 0),
            "rejected": int(report.get("rejected_count") or 0),
            "conflicts": int(report.get("conflict_count") or 0),
        },
        "notice": "A blocked or empty report is not a production-ready Nadia dataset.",
    }


def nadia_known_data_gaps() -> list[dict[str, Any]]:
    """Expose the existing data-gap registry entries relevant to this pilot."""
    gap_ids = (
        "doctor_live_slots",
        "hospital_bed_availability",
        "pharmacy_live_stock",
        "lab_live_slots",
        "provider_languages",
        "provider_accessibility",
    )
    return [gap for gap_id in gap_ids if (gap := get_data_gap(gap_id)) is not None]

