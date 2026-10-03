"""Governed global organization/company intelligence source registry.

This layer answers the user's "all companies" requirement without pretending
that every company exposes the same API. ZENDOC starts with authoritative legal
entity / filing registries, then attaches official company newsrooms, regulatory
filings and healthcare-specific sources as reviewed evidence feeds.

A registry entry permits discovery/planning only. It never authorizes private
database access, bypassing login/captcha/paywalls, copying personal user data,
or treating a corporate announcement as clinical truth.
"""
from __future__ import annotations

from copy import deepcopy
from urllib.parse import urlparse


ORGANIZATION_INTELLIGENCE_SOURCES: dict[str, dict] = {
    "gleif_lei": {
        "source_id": "gleif_lei",
        "name": "Global Legal Entity Identifier Foundation (GLEIF) LEI Data",
        "owner": "Global Legal Entity Identifier Foundation",
        "jurisdiction": "global",
        "official_url": "https://www.gleif.org/en/lei-data/gleif-api/",
        "source_kind": "global_legal_entity_identity_and_ownership",
        "access_mode": "PUBLIC_API_AND_BULK_FILES",
        "authentication_required": False,
        "machine_readable": True,
        "personal_data_allowed": False,
        "capabilities": ["legal_entity_search", "fuzzy_name_match", "ownership_relationships", "mapped_identifiers"],
        "refresh_strategy": "API_OR_PUBLISHED_DELTA_FILES",
        "notes": "Use LEI identity/ownership where available. Absence of an LEI does not mean an organization is invalid.",
    },
    "us_sec_edgar": {
        "source_id": "us_sec_edgar",
        "name": "U.S. SEC EDGAR Data APIs",
        "owner": "U.S. Securities and Exchange Commission",
        "jurisdiction": "US",
        "official_url": "https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
        "source_kind": "public_company_regulatory_filings",
        "access_mode": "PUBLIC_API_AND_BULK_FILES",
        "authentication_required": False,
        "machine_readable": True,
        "personal_data_allowed": False,
        "capabilities": ["company_submissions", "xbrl_company_facts", "filing_history", "bulk_archives"],
        "refresh_strategy": "API_PLUS_NIGHTLY_BULK_ARCHIVES",
        "notes": "Respect SEC automated-access policy and identify ZENDOC requests. Filings are evidence, not endorsement.",
    },
    "uk_companies_house": {
        "source_id": "uk_companies_house",
        "name": "UK Companies House API",
        "owner": "Companies House",
        "jurisdiction": "GB",
        "official_url": "https://developer.company-information.service.gov.uk/",
        "source_kind": "official_company_register",
        "access_mode": "AUTHENTICATED_PUBLIC_API",
        "authentication_required": True,
        "machine_readable": True,
        "personal_data_allowed": False,
        "capabilities": ["company_search", "company_profile", "filing_history", "officers_where_public"],
        "refresh_strategy": "API_WITH_PROVIDER_RATE_LIMITS",
        "notes": "API credentials and provider limits apply. Ingest only fields whose public-use basis is reviewed.",
    },
    "india_mca_master_data": {
        "source_id": "india_mca_master_data",
        "name": "Ministry of Corporate Affairs Company / LLP Master Data",
        "owner": "Ministry of Corporate Affairs, Government of India",
        "jurisdiction": "IN",
        "official_url": "https://www.mca.gov.in/",
        "source_kind": "official_company_and_llp_register",
        "access_mode": "OFFICIAL_LOOKUP_AND_AUTHORIZED_SERVICES",
        "authentication_required": False,
        "machine_readable": False,
        "personal_data_allowed": False,
        "capabilities": ["company_llp_master_data", "public_documents", "corporate_updates"],
        "refresh_strategy": "LOOKUP_OR_APPROVED_EXPORT_ONLY",
        "notes": "Use official MCA services. Do not automate captcha/login bypass or assume a bulk API that has not been approved.",
    },
}


DYNAMIC_SOURCE_KINDS = {
    "official_company_newsroom",
    "official_investor_relations",
    "official_regulatory_filing_feed",
    "official_product_or_service_catalog",
    "authorized_partner_api",
    "licensed_commercial_dataset",
}


def list_organization_intelligence_sources() -> list[dict]:
    return [deepcopy(ORGANIZATION_INTELLIGENCE_SOURCES[key]) for key in sorted(ORGANIZATION_INTELLIGENCE_SOURCES)]


def get_organization_intelligence_source(source_id: str) -> dict | None:
    item = ORGANIZATION_INTELLIGENCE_SOURCES.get(str(source_id or "").strip().lower())
    return deepcopy(item) if item else None


def organization_discovery_plan(organization_name: str, *, country_code: str | None = None) -> dict:
    name = str(organization_name or "").strip()
    if not name:
        raise ValueError("organization_name is required.")
    country = str(country_code or "").strip().upper() or None
    source_ids = ["gleif_lei"]
    if country == "US":
        source_ids.append("us_sec_edgar")
    elif country == "GB":
        source_ids.append("uk_companies_house")
    elif country == "IN":
        source_ids.append("india_mca_master_data")

    return {
        "organization_name": name,
        "country_code": country,
        "identity_sources": [get_organization_intelligence_source(source_id) for source_id in source_ids],
        "next_evidence_sources": [
            "official_company_newsroom",
            "official_investor_relations",
            "official_regulatory_filing_feed",
            "official_healthcare_regulator_or_provider_registry",
        ],
        "required_checks": [
            "resolve_legal_entity_before_merging_names",
            "confirm_official_domain_or_authoritative_registry_link",
            "record_retrieved_at_and_source_url",
            "record_usage_or_licensing_basis",
            "deduplicate_by_stable_identifier_when_available",
            "keep_corporate_claims_separate_from_clinical_or_regulatory_truth",
        ],
        "automatic_private_data_collection": False,
        "notice": "Discovery may use public/licensed sources only. Authentication, terms, rate limits and jurisdiction rules remain binding.",
    }


def validate_dynamic_organization_source(candidate: dict) -> dict:
    if not isinstance(candidate, dict):
        raise ValueError("Organization source candidate must be an object.")
    name = str(candidate.get("organization_name") or "").strip()
    url = str(candidate.get("official_url") or "").strip()
    kind = str(candidate.get("source_kind") or "").strip()
    usage_basis = str(candidate.get("usage_basis") or "").strip()
    if not name:
        raise ValueError("organization_name is required.")
    if kind not in DYNAMIC_SOURCE_KINDS:
        raise ValueError("Unsupported organization source_kind.")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("official_url must be a valid HTTPS URL.")
    if len(usage_basis) < 8:
        raise ValueError("usage_basis must record a meaningful permission/licensing/public-use basis.")
    if bool(candidate.get("personal_data_allowed")):
        raise ValueError("Dynamic organization intelligence sources cannot opt into personal user data collection.")

    return {
        "status": "REVIEWABLE",
        "organization_name": name,
        "country_code": str(candidate.get("country_code") or "").strip().upper() or None,
        "official_url": url,
        "source_kind": kind,
        "usage_basis": usage_basis,
        "ingestion_allowed": False,
        "next_gate": "SOURCE_TERMS_AND_SCHEMA_REVIEW",
        "notice": "Reviewable source metadata only; this does not authorize scraping, ingestion, or access to private systems.",
    }


def organization_intelligence_manifest() -> dict:
    sources = list_organization_intelligence_sources()
    return {
        "source_count": len(sources),
        "sources": sources,
        "dynamic_source_kinds": sorted(DYNAMIC_SOURCE_KINDS),
        "principles": [
            "legal_entity_identity_before_name_merge",
            "official_or_licensed_evidence_first",
            "provenance_and_retrieval_time_required",
            "no_private_user_data_without_separate_authorized_consent_path",
            "no_auth_captcha_paywall_or_access_control_bypass",
            "corporate_claims_do_not_become_clinical_truth",
        ],
    }
