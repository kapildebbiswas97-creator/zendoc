"""ZENDOC Benefits & Coverage source registry.

This module intentionally stores source metadata and integration boundaries, not
beneficiary records or policy secrets. Public scheme discovery can be indexed;
personal eligibility, policy status, claims, balances, and cashless approvals
must come from an authorized provider flow or explicit user-supplied evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


PUBLIC_DATA_API = "PUBLIC_DATA_API"
PUBLIC_PORTAL = "PUBLIC_PORTAL"
SANDBOX_PARTNER_API = "SANDBOX_PARTNER_API"
PARTNER_REQUIRED = "PARTNER_REQUIRED"
REGULATED_PARTNER_REQUIRED = "REGULATED_PARTNER_REQUIRED"


@dataclass(frozen=True)
class BenefitSource:
    source_id: str
    name: str
    owner: str
    source_type: str
    geography: str
    categories: tuple[str, ...]
    official_url: str
    integration_status: str
    personal_data_allowed: bool
    notes: str

    def to_dict(self) -> dict:
        data = asdict(self)
        data["categories"] = list(self.categories)
        return data


SOURCES: tuple[BenefitSource, ...] = (
    BenefitSource(
        source_id="myscheme",
        name="myScheme",
        owner="Government of India / Digital India",
        source_type=PUBLIC_PORTAL,
        geography="INDIA",
        categories=("government_scheme", "eligibility_discovery"),
        official_url="https://www.myscheme.gov.in/",
        integration_status="PUBLIC_DISCOVERY_AVAILABLE_PARTNER_API_TO_VERIFY",
        personal_data_allowed=False,
        notes="Use for scheme discovery and application guidance. Do not claim eligibility solely from indexed text.",
    ),
    BenefitSource(
        source_id="data_gov_in",
        name="Open Government Data Platform India",
        owner="Government of India / NIC",
        source_type=PUBLIC_DATA_API,
        geography="INDIA",
        categories=("hospital_directory", "cghs", "health_statistics", "government_open_data"),
        official_url="https://www.data.gov.in/",
        integration_status="PUBLIC_API_AVAILABLE_PER_DATASET",
        personal_data_allowed=False,
        notes="Prefer datasets released under Government Open Data License. Track dataset update timestamps and provenance.",
    ),
    BenefitSource(
        source_id="abdm",
        name="Ayushman Bharat Digital Mission",
        owner="National Health Authority",
        source_type=SANDBOX_PARTNER_API,
        geography="INDIA",
        categories=("abha", "hfr", "hpr", "health_records", "consent"),
        official_url="https://abdm.gov.in/",
        integration_status="SANDBOX_ONBOARDING_REQUIRED",
        personal_data_allowed=True,
        notes="Personal health data requires ABDM-compliant consent, sandbox certification, security testing, and production approval.",
    ),
    BenefitSource(
        source_id="pmjay",
        name="Ayushman Bharat - PM-JAY",
        owner="National Health Authority",
        source_type=PARTNER_REQUIRED,
        geography="INDIA",
        categories=("government_health_assurance", "cashless_hospitalization", "empanelled_hospitals"),
        official_url="https://pmjay.gov.in/",
        integration_status="PUBLIC_SCHEME_DATA_PARTNER_ACCESS_FOR_BENEFICIARY_AND_CLAIMS",
        personal_data_allowed=True,
        notes="Public benefit/package information may be indexed. Beneficiary identity, wallet, pre-auth, or claims require authorized NHA/SHA workflows.",
    ),
    BenefitSource(
        source_id="swasthya_sathi",
        name="Swasthya Sathi",
        owner="Government of West Bengal",
        source_type=PARTNER_REQUIRED,
        geography="WEST_BENGAL",
        categories=("state_health_scheme", "cashless_hospitalization", "empanelled_hospitals"),
        official_url="https://swasthyasathi.gov.in/",
        integration_status="PUBLIC_PORTAL_PARTNER_ACCESS_REQUIRED_FOR_PERSONAL_STATUS",
        personal_data_allowed=True,
        notes="Index only official public scheme/provider information. Card status and patient-level entitlement require authorized verification.",
    ),
    BenefitSource(
        source_id="cghs",
        name="Central Government Health Scheme",
        owner="Ministry of Health and Family Welfare",
        source_type=PUBLIC_DATA_API,
        geography="INDIA",
        categories=("government_employee_health", "empanelled_hospitals", "diagnostics", "medicines"),
        official_url="https://cghs.mohfw.gov.in/",
        integration_status="PUBLIC_DIRECTORY_DATA_AVAILABLE_SOME_ACTIONS_PARTNER_REQUIRED",
        personal_data_allowed=False,
        notes="Use public CGHS directory/catalog data for discovery; never infer an individual's CGHS entitlement.",
    ),
    BenefitSource(
        source_id="lic",
        name="Life Insurance Corporation of India",
        owner="LIC of India",
        source_type=REGULATED_PARTNER_REQUIRED,
        geography="INDIA",
        categories=("life_insurance", "group_insurance", "critical_illness", "government_linked_insurance"),
        official_url="https://licindia.in/",
        integration_status="PUBLIC_PRODUCT_CATALOG_PARTNER_OR_USER_AUTH_REQUIRED_FOR_POLICY_DATA",
        personal_data_allowed=True,
        notes="Public product information may be indexed. Policy, nominee, premium, loan, benefit, and claim data require explicit user authorization or LIC partnership.",
    ),
    BenefitSource(
        source_id="irdai",
        name="IRDAI",
        owner="Insurance Regulatory and Development Authority of India",
        source_type=PUBLIC_PORTAL,
        geography="INDIA",
        categories=("insurance_regulation", "insurer_registry", "policyholder_protection", "bima_sugam"),
        official_url="https://irdai.gov.in/",
        integration_status="PUBLIC_REGULATORY_DATA",
        personal_data_allowed=False,
        notes="Use for regulator-verified insurer/product/regulatory metadata and grievance guidance, not as a source of customer policy data.",
    ),
    BenefitSource(
        source_id="ngo_darpan",
        name="NGO Darpan",
        owner="NITI Aayog / Government of India",
        source_type=PUBLIC_PORTAL,
        geography="INDIA",
        categories=("ngo", "trust", "charitable_support", "health_welfare"),
        official_url="https://ngodarpan.gov.in/",
        integration_status="PUBLIC_REGISTRY_DISCOVERY_PARTNERSHIP_REQUIRED_FOR_FUNDING",
        personal_data_allowed=False,
        notes="Use as an organization-discovery source. Funding availability, patient selection, and grant decisions must be verified with the organization.",
    ),
    BenefitSource(
        source_id="mca_csr",
        name="MCA CSR Ecosystem",
        owner="Ministry of Corporate Affairs",
        source_type=PUBLIC_PORTAL,
        geography="INDIA",
        categories=("csr", "corporate_health_program", "implementing_agency"),
        official_url="https://www.csr.gov.in/",
        integration_status="PUBLIC_PROGRAM_DATA_PARTNERSHIP_REQUIRED_FOR_CASE_FUNDING",
        personal_data_allowed=False,
        notes="Use public CSR/project and implementing-agency data for matching. A company or implementing agency must explicitly accept a patient/program before funding is shown as confirmed.",
    ),
)


def list_sources(
    *,
    geography: str | None = None,
    categories: Iterable[str] | None = None,
) -> list[dict]:
    geo = str(geography or "").strip().upper()
    wanted = {str(item).strip().lower() for item in (categories or []) if str(item).strip()}
    results: list[dict] = []
    for source in SOURCES:
        if geo and source.geography not in {"INDIA", geo}:
            continue
        source_categories = {item.lower() for item in source.categories}
        if wanted and not wanted.intersection(source_categories):
            continue
        results.append(source.to_dict())
    return results


def get_source(source_id: str) -> dict | None:
    normalized = str(source_id or "").strip().lower()
    for source in SOURCES:
        if source.source_id == normalized:
            return source.to_dict()
    return None


def coverage_truth_state(
    *,
    source_id: str,
    evidence_type: str | None = None,
    provider_confirmed: bool = False,
) -> dict:
    """Return a non-deceptive coverage state for downstream agents/UI."""
    source = get_source(source_id)
    if not source:
        return {"status": "UNKNOWN_SOURCE", "confirmed": False}

    evidence = str(evidence_type or "").strip().upper()
    if provider_confirmed and evidence in {
        "OFFICIAL_API",
        "INSURER_RESPONSE",
        "GOVERNMENT_RESPONSE",
        "EMPLOYER_RESPONSE",
        "TRUST_APPROVAL",
        "USER_AUTHORIZED_POLICY",
    }:
        return {
            "status": "CONFIRMED",
            "confirmed": True,
            "source_id": source_id,
            "evidence_type": evidence,
        }

    if evidence:
        return {
            "status": "EVIDENCE_RECEIVED_NOT_CONFIRMED",
            "confirmed": False,
            "source_id": source_id,
            "evidence_type": evidence,
        }

    return {
        "status": "DISCOVERY_ONLY",
        "confirmed": False,
        "source_id": source_id,
    }
