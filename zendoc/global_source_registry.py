"""Country-aware official/public healthcare source registry.

This registry extends the existing India source registry without weakening any
truth boundary. A source being listed here means it is approved for discovery
and/or controlled import according to its declared access mode. It never means
ZENDOC has live API access, verified a provider, or can book/dispatch/order.
"""
from __future__ import annotations

from copy import deepcopy

from .public_source_registry import (
    get_public_ingestion_source as get_india_public_source,
    list_public_ingestion_sources as list_india_public_sources,
)


COUNTRIES: dict[str, dict] = {
    "IN": {
        "country_code": "IN",
        "country_name": "India",
        "coverage_status": "NATIONAL_OFFICIAL_PIPELINE_READY",
        "notes": "National official sources cover geography and multiple facility classes; state/UT supplements remain source-specific.",
    },
    "SG": {
        "country_code": "SG",
        "country_name": "Singapore",
        "coverage_status": "OFFICIAL_LOOKUP_READY_BULK_EXPORT_REVIEW",
        "notes": "MOH/HCSA and professional-board sources are authoritative; systematic bulk ingestion requires an approved export/access path.",
    },
    "GB": {
        "country_code": "GB",
        "country_name": "United Kingdom",
        "coverage_status": "NHS_ODS_EXPORT_READY",
        "notes": "NHS Organisation Data Service supports structured organisation search/export. London is handled as a UK locality/region, not a country.",
    },
    "US": {
        "country_code": "US",
        "country_name": "United States",
        "coverage_status": "CMS_OPEN_DATA_READY",
        "notes": "CMS Provider Data Catalog exposes downloadable/API datasets for hospitals and clinicians; coverage is Medicare-oriented rather than every provider in the country.",
    },
    "RU": {
        "country_code": "RU",
        "country_name": "Russia",
        "coverage_status": "AUTHORIZED_EGISZ_EXPORT_REQUIRED",
        "notes": "The Federal Register of Medical Organisations is authoritative, but systematic export/access must use an authorised EGISZ path.",
    },
    "CN": {
        "country_code": "CN",
        "country_name": "China",
        "coverage_status": "OFFICIAL_LOOKUP_READY_NO_VERIFIED_BULK_EXPORT",
        "notes": "National Health Commission/government-service lookups are authoritative references; ZENDOC must not scrape captcha-protected or non-export services.",
    },
    "BD": {
        "country_code": "BD",
        "country_name": "Bangladesh",
        "coverage_status": "DGHS_PUBLIC_REGISTRY_READY_FOR_NORMALIZED_IMPORT",
        "notes": "DGHS publishes a public facility registry with administrative hierarchy and facility metadata. Imports still require provenance and freshness snapshots.",
    },
    "PK": {
        "country_code": "PK",
        "country_name": "Pakistan",
        "coverage_status": "PROVINCIAL_OFFICIAL_SOURCES_PARTIAL_NATIONAL_COVERAGE",
        "notes": "Official facility material is available from federal/provincial health authorities, but no single verified national bulk facility export is assumed.",
    },
}


INDIA_ADMIN1: tuple[dict[str, str], ...] = (
    {"code": "AN", "name": "Andaman and Nicobar Islands", "type": "union_territory"},
    {"code": "AP", "name": "Andhra Pradesh", "type": "state"},
    {"code": "AR", "name": "Arunachal Pradesh", "type": "state"},
    {"code": "AS", "name": "Assam", "type": "state"},
    {"code": "BR", "name": "Bihar", "type": "state"},
    {"code": "CH", "name": "Chandigarh", "type": "union_territory"},
    {"code": "CG", "name": "Chhattisgarh", "type": "state"},
    {"code": "DH", "name": "Dadra and Nagar Haveli and Daman and Diu", "type": "union_territory"},
    {"code": "DL", "name": "Delhi", "type": "union_territory"},
    {"code": "GA", "name": "Goa", "type": "state"},
    {"code": "GJ", "name": "Gujarat", "type": "state"},
    {"code": "HR", "name": "Haryana", "type": "state"},
    {"code": "HP", "name": "Himachal Pradesh", "type": "state"},
    {"code": "JK", "name": "Jammu and Kashmir", "type": "union_territory"},
    {"code": "JH", "name": "Jharkhand", "type": "state"},
    {"code": "KA", "name": "Karnataka", "type": "state"},
    {"code": "KL", "name": "Kerala", "type": "state"},
    {"code": "LA", "name": "Ladakh", "type": "union_territory"},
    {"code": "LD", "name": "Lakshadweep", "type": "union_territory"},
    {"code": "MP", "name": "Madhya Pradesh", "type": "state"},
    {"code": "MH", "name": "Maharashtra", "type": "state"},
    {"code": "MN", "name": "Manipur", "type": "state"},
    {"code": "ML", "name": "Meghalaya", "type": "state"},
    {"code": "MZ", "name": "Mizoram", "type": "state"},
    {"code": "NL", "name": "Nagaland", "type": "state"},
    {"code": "OD", "name": "Odisha", "type": "state"},
    {"code": "PY", "name": "Puducherry", "type": "union_territory"},
    {"code": "PB", "name": "Punjab", "type": "state"},
    {"code": "RJ", "name": "Rajasthan", "type": "state"},
    {"code": "SK", "name": "Sikkim", "type": "state"},
    {"code": "TN", "name": "Tamil Nadu", "type": "state"},
    {"code": "TS", "name": "Telangana", "type": "state"},
    {"code": "TR", "name": "Tripura", "type": "state"},
    {"code": "UP", "name": "Uttar Pradesh", "type": "state"},
    {"code": "UK", "name": "Uttarakhand", "type": "state"},
    {"code": "WB", "name": "West Bengal", "type": "state"},
)


GLOBAL_SOURCES: dict[str, dict] = {
    "sg_moh_hcsa_facilities": {
        "source_id": "sg_moh_hcsa_facilities",
        "name": "Singapore MOH / HCSA Licensed Healthcare Services",
        "owner": "Ministry of Health, Singapore",
        "official_url": "https://www.hcsa.gov.sg/",
        "data_class": "authoritative_licensed_healthcare_service_reference",
        "geography": "SINGAPORE",
        "country_code": "SG",
        "country_name": "Singapore",
        "ingestion_types": ["public_healthcare_entities"],
        "trust_level": "AUTHORITATIVE_REGISTRY",
        "live_fetch_status": "APPROVED_EXPORT_OR_AUTHORISED_ACCESS_REQUIRED_FOR_SYSTEMATIC_IMPORT",
        "personal_data_allowed": False,
        "notes": "Use only an official export/access path. Do not scrape protected search interfaces. Licence status does not imply ZENDOC booking connectivity.",
    },
    "sg_moh_health_professionals": {
        "source_id": "sg_moh_health_professionals",
        "name": "Singapore MOH Healthcare Professionals Search",
        "owner": "Ministry of Health, Singapore / Professional Boards",
        "official_url": "https://hpp.moh.gov.sg/healthcare-professionals-search/",
        "data_class": "authoritative_professional_registration_lookup",
        "geography": "SINGAPORE",
        "country_code": "SG",
        "country_name": "Singapore",
        "ingestion_types": [],
        "trust_level": "AUTHORITATIVE_REGISTRY",
        "live_fetch_status": "PUBLIC_LOOKUP_REFERENCE_ONLY_NO_BULK_ACCESS_ASSUMED",
        "personal_data_allowed": False,
        "notes": "Use as verification evidence/reference. Do not bulk-copy professional records unless an authorised export is explicitly available.",
    },
    "uk_nhs_ods": {
        "source_id": "uk_nhs_ods",
        "name": "NHS Organisation Data Service",
        "owner": "NHS England",
        "official_url": "https://www.odsdatasearchandexport.nhs.uk/",
        "data_class": "official_health_and_social_care_organisation_directory",
        "geography": "UNITED_KINGDOM",
        "country_code": "GB",
        "country_name": "United Kingdom",
        "ingestion_types": ["public_healthcare_entities"],
        "trust_level": "AUTHORITATIVE_REGISTRY",
        "live_fetch_status": "PUBLIC_SEARCH_AND_EXPORT",
        "personal_data_allowed": False,
        "notes": "ODS organisation exports may be imported with source date/provenance. Practitioner data must remain within the published-use basis.",
    },
    "uk_nhs_website_datasets": {
        "source_id": "uk_nhs_website_datasets",
        "name": "NHS Website Organisation Datasets",
        "owner": "NHS",
        "official_url": "https://www.nhs.uk/about-us/nhs-website-datasets/",
        "data_class": "official_public_healthcare_directory",
        "geography": "UNITED_KINGDOM",
        "country_code": "GB",
        "country_name": "United Kingdom",
        "ingestion_types": ["public_healthcare_entities"],
        "trust_level": "OFFICIAL_PUBLIC_DATA",
        "live_fetch_status": "REQUEST_OR_APPROVED_SYNDICATION_ACCESS",
        "personal_data_allowed": False,
        "notes": "NHS organisation datasets include hospitals, GPs, dentists and pharmacies. Preserve ODS codes and dataset/syndication freshness.",
    },
    "us_cms_hospital_general": {
        "source_id": "us_cms_hospital_general",
        "name": "CMS Hospital General Information",
        "owner": "Centers for Medicare & Medicaid Services",
        "official_url": "https://data.cms.gov/provider-data/dataset/xubh-q36u",
        "data_class": "official_medicare_hospital_directory",
        "geography": "UNITED_STATES",
        "country_code": "US",
        "country_name": "United States",
        "ingestion_types": ["public_healthcare_entities"],
        "trust_level": "OFFICIAL_PUBLIC_DATA",
        "live_fetch_status": "PUBLIC_CSV_AND_API",
        "personal_data_allowed": False,
        "notes": "CMS hospital data is Medicare-oriented public provider data. Ratings/quality fields are source observations and never imply ZENDOC verification or availability.",
    },
    "us_cms_doctors_clinicians": {
        "source_id": "us_cms_doctors_clinicians",
        "name": "CMS Doctors and Clinicians Provider Data",
        "owner": "Centers for Medicare & Medicaid Services",
        "official_url": "https://data.cms.gov/provider-data/topics/doctors-clinicians",
        "data_class": "official_medicare_clinician_directory",
        "geography": "UNITED_STATES",
        "country_code": "US",
        "country_name": "United States",
        "ingestion_types": ["public_healthcare_entities"],
        "trust_level": "OFFICIAL_PUBLIC_DATA",
        "live_fetch_status": "PUBLIC_DOWNLOAD_AND_API",
        "personal_data_allowed": False,
        "notes": "Use only published provider fields and stated public-use terms. Public CMS listing is not the same as ZENDOC provider onboarding or live appointment connectivity.",
    },
    "ru_minzdrav_frmo": {
        "source_id": "ru_minzdrav_frmo",
        "name": "Federal Register of Medical Organisations (FRMO)",
        "owner": "Ministry of Health of the Russian Federation",
        "official_url": "https://minzdrav.gov.ru/special/ministry/web-site/informatsionnye-sistemy-minzdrava-rossii/katalog-podsistem-egisz/federalnyy-reestr-meditsinskih-organizatsiy",
        "data_class": "authoritative_healthcare_organisation_registry",
        "geography": "RUSSIA",
        "country_code": "RU",
        "country_name": "Russia",
        "ingestion_types": ["public_healthcare_entities"],
        "trust_level": "AUTHORITATIVE_REGISTRY",
        "live_fetch_status": "AUTHORISED_EGISZ_ACCESS_REQUIRED_FOR_SYSTEMATIC_EXPORT",
        "personal_data_allowed": False,
        "notes": "FRMO is authoritative, but ZENDOC must not claim or emulate EGISZ access. Import only an authorised lawful export with provenance.",
    },
    "cn_nhc_medical_licence_lookup": {
        "source_id": "cn_nhc_medical_licence_lookup",
        "name": "China NHC Medical Institution Licence Information Lookup",
        "owner": "National Health Commission of the People's Republic of China",
        "official_url": "https://app.gjzwfw.gov.cn/jmopen/webapp/html5/zwfwunitsearch/index.html",
        "data_class": "authoritative_medical_institution_licence_lookup",
        "geography": "CHINA",
        "country_code": "CN",
        "country_name": "China",
        "ingestion_types": [],
        "trust_level": "AUTHORITATIVE_REGISTRY",
        "live_fetch_status": "PUBLIC_LOOKUP_CAPTCHA_OR_AUTHENTICATION_NO_BULK_IMPORT_ASSUMED",
        "personal_data_allowed": False,
        "notes": "Use for manual/authorised verification. Never bypass captcha/authentication or convert lookup results into a bulk mirror.",
    },
    "cn_nhc_health_service_queries": {
        "source_id": "cn_nhc_health_service_queries",
        "name": "China National Health Commission Government Service Queries",
        "owner": "National Health Commission of the People's Republic of China",
        "official_url": "https://zwfw.nhc.gov.cn/cxx/",
        "data_class": "official_health_institution_and_professional_lookup",
        "geography": "CHINA",
        "country_code": "CN",
        "country_name": "China",
        "ingestion_types": [],
        "trust_level": "OFFICIAL_PUBLIC_DATA",
        "live_fetch_status": "PUBLIC_LOOKUP_REFERENCE_ONLY",
        "personal_data_allowed": False,
        "notes": "Supports institution/professional/drug reference lookups. No systematic bulk-import route is assumed.",
    },
    "bd_dghs_facility_registry": {
        "source_id": "bd_dghs_facility_registry",
        "name": "Bangladesh DGHS Facility Registry",
        "owner": "Directorate General of Health Services, Ministry of Health and Family Welfare, Bangladesh",
        "official_url": "https://hrm.dghs.gov.bd/index.php/public/facility-registry",
        "data_class": "authoritative_public_health_facility_registry",
        "geography": "BANGLADESH",
        "country_code": "BD",
        "country_name": "Bangladesh",
        "ingestion_types": ["public_healthcare_entities"],
        "trust_level": "AUTHORITATIVE_REGISTRY",
        "live_fetch_status": "PUBLIC_REGISTRY_APPROVED_EXPORT_OR_BOUNDED_CONNECTOR_REQUIRED",
        "personal_data_allowed": False,
        "notes": "Facility registry includes government/private facilities and administrative hierarchy. Preserve facility ID/code and snapshot date; do not infer availability.",
    },
    "pk_punjab_health_facilities": {
        "source_id": "pk_punjab_health_facilities",
        "name": "Punjab Health and Population Department Health Facilities",
        "owner": "Government of Punjab, Pakistan",
        "official_url": "https://pshealthpunjab.gov.pk/Home/HealthFacilities",
        "data_class": "official_provincial_health_facility_directory",
        "geography": "PAKISTAN_PUNJAB",
        "country_code": "PK",
        "country_name": "Pakistan",
        "ingestion_types": ["public_healthcare_entities"],
        "trust_level": "OFFICIAL_PUBLIC_DATA",
        "live_fetch_status": "PUBLIC_WEB_DIRECTORY_APPROVED_EXPORT_REQUIRED_FOR_BULK_IMPORT",
        "personal_data_allowed": False,
        "notes": "Covers DHQ/THQ hospitals, RHCs, BHUs and dispensaries in Punjab province. It is provincial, not complete national coverage.",
    },
    "pk_balochistan_health_facilities": {
        "source_id": "pk_balochistan_health_facilities",
        "name": "Balochistan Health Department Facility Publications",
        "owner": "Government of Balochistan, Pakistan",
        "official_url": "https://health.balochistan.gov.pk/",
        "data_class": "official_provincial_health_facility_reference",
        "geography": "PAKISTAN_BALOCHISTAN",
        "country_code": "PK",
        "country_name": "Pakistan",
        "ingestion_types": ["public_healthcare_entities"],
        "trust_level": "OFFICIAL_PUBLIC_DATA",
        "live_fetch_status": "DATED_PUBLIC_LISTS_APPROVED_ARTIFACT_IMPORT",
        "personal_data_allowed": False,
        "notes": "Use dated facility lists only. Exclude staff personal/contact fields unless clearly required and permitted; facility metadata is the ingestion target.",
    },
    "pk_federal_islamabad_facilities": {
        "source_id": "pk_federal_islamabad_facilities",
        "name": "Pakistan Federal Health Facility Publications - Islamabad",
        "owner": "Ministry of National Health Services, Regulations and Coordination, Pakistan",
        "official_url": "https://www.nhsrc.gov.pk/",
        "data_class": "official_federal_health_facility_reference",
        "geography": "PAKISTAN_ISLAMABAD",
        "country_code": "PK",
        "country_name": "Pakistan",
        "ingestion_types": ["public_healthcare_entities"],
        "trust_level": "OFFICIAL_PUBLIC_DATA",
        "live_fetch_status": "DATED_PUBLIC_DOCUMENTS_APPROVED_ARTIFACT_IMPORT",
        "personal_data_allowed": False,
        "notes": "Use only dated federal publications that enumerate facilities. This source does not establish national completeness.",
    },
}


def _decorate_india(source: dict) -> dict:
    item = deepcopy(source)
    item.setdefault("country_code", "IN")
    item.setdefault("country_name", "India")
    item.setdefault("jurisdiction", item.get("geography") or "INDIA")
    return item


def get_global_public_ingestion_source(source_id: str) -> dict | None:
    key = str(source_id or "").strip().lower()
    global_source = GLOBAL_SOURCES.get(key)
    if global_source:
        return deepcopy(global_source)
    india = get_india_public_source(key)
    return _decorate_india(india) if india else None


def list_global_public_ingestion_sources() -> list[dict]:
    india = [_decorate_india(source) for source in list_india_public_sources()]
    international = [deepcopy(GLOBAL_SOURCES[key]) for key in sorted(GLOBAL_SOURCES)]
    return india + international


def country_coverage_manifest() -> list[dict]:
    sources = list_global_public_ingestion_sources()
    result = []
    for code in sorted(COUNTRIES):
        country = deepcopy(COUNTRIES[code])
        country_sources = [source for source in sources if source.get("country_code") == code]
        country["source_count"] = len(country_sources)
        country["ingestible_source_count"] = sum(bool(source.get("ingestion_types")) for source in country_sources)
        country["source_ids"] = [source["source_id"] for source in country_sources]
        if code == "IN":
            country["admin1_units"] = [deepcopy(item) for item in INDIA_ADMIN1]
            country["admin1_count"] = len(INDIA_ADMIN1)
        result.append(country)
    return result
