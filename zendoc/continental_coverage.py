"""Continent-wide ZENDOC jurisdiction coverage.

Coverage here is intentionally conservative. A jurisdiction entry means ZENDOC
can represent/search/import data for that jurisdiction without country collision.
It does NOT mean a national facility dataset has already been imported.

Country/area grouping follows the UN M49 regional model where practical. The
catalog is operational, not a statement about disputed sovereignty.
"""
from __future__ import annotations

from copy import deepcopy

from .global_source_registry import COUNTRIES, GLOBAL_SOURCES


def _country(code: str, name: str, continent: str, status: str = "SOURCE_DISCOVERY_REQUIRED", notes: str | None = None) -> dict:
    return {
        "country_code": code,
        "country_name": name,
        "continent": continent,
        "coverage_status": status,
        "notes": notes or "Country-aware ZENDOC storage/search is supported; an authoritative national facility import source still requires review.",
    }


ASIA = (
    ("AF", "Afghanistan"), ("AM", "Armenia"), ("AZ", "Azerbaijan"), ("BH", "Bahrain"),
    ("BD", "Bangladesh"), ("BT", "Bhutan"), ("BN", "Brunei Darussalam"), ("KH", "Cambodia"),
    ("CN", "China"), ("CY", "Cyprus"), ("GE", "Georgia"), ("IN", "India"),
    ("ID", "Indonesia"), ("IR", "Iran"), ("IQ", "Iraq"), ("IL", "Israel"),
    ("JP", "Japan"), ("JO", "Jordan"), ("KZ", "Kazakhstan"), ("KW", "Kuwait"),
    ("KG", "Kyrgyzstan"), ("LA", "Lao People's Democratic Republic"), ("LB", "Lebanon"),
    ("MY", "Malaysia"), ("MV", "Maldives"), ("MN", "Mongolia"), ("MM", "Myanmar"),
    ("NP", "Nepal"), ("KP", "North Korea"), ("OM", "Oman"), ("PK", "Pakistan"),
    ("PS", "State of Palestine"), ("PH", "Philippines"), ("QA", "Qatar"),
    ("SA", "Saudi Arabia"), ("SG", "Singapore"), ("KR", "South Korea"),
    ("LK", "Sri Lanka"), ("SY", "Syrian Arab Republic"), ("TJ", "Tajikistan"),
    ("TH", "Thailand"), ("TL", "Timor-Leste"), ("TR", "Türkiye"), ("TM", "Turkmenistan"),
    ("AE", "United Arab Emirates"), ("UZ", "Uzbekistan"), ("VN", "Viet Nam"), ("YE", "Yemen"),
)

EUROPE = (
    ("AL", "Albania"), ("AD", "Andorra"), ("AT", "Austria"), ("BY", "Belarus"),
    ("BE", "Belgium"), ("BA", "Bosnia and Herzegovina"), ("BG", "Bulgaria"), ("HR", "Croatia"),
    ("CZ", "Czechia"), ("DK", "Denmark"), ("EE", "Estonia"), ("FI", "Finland"),
    ("FR", "France"), ("DE", "Germany"), ("GR", "Greece"), ("VA", "Holy See"),
    ("HU", "Hungary"), ("IS", "Iceland"), ("IE", "Ireland"), ("IT", "Italy"),
    ("LV", "Latvia"), ("LI", "Liechtenstein"), ("LT", "Lithuania"), ("LU", "Luxembourg"),
    ("MT", "Malta"), ("MD", "Moldova"), ("MC", "Monaco"), ("ME", "Montenegro"),
    ("NL", "Netherlands"), ("MK", "North Macedonia"), ("NO", "Norway"), ("PL", "Poland"),
    ("PT", "Portugal"), ("RO", "Romania"), ("RU", "Russia"), ("SM", "San Marino"),
    ("RS", "Serbia"), ("SK", "Slovakia"), ("SI", "Slovenia"), ("ES", "Spain"),
    ("SE", "Sweden"), ("CH", "Switzerland"), ("UA", "Ukraine"), ("GB", "United Kingdom"),
)

OCEANIA = (
    ("AU", "Australia"), ("FJ", "Fiji"), ("KI", "Kiribati"), ("MH", "Marshall Islands"),
    ("FM", "Micronesia (Federated States of)"), ("NR", "Nauru"), ("NZ", "New Zealand"),
    ("PW", "Palau"), ("PG", "Papua New Guinea"), ("WS", "Samoa"), ("SB", "Solomon Islands"),
    ("TO", "Tonga"), ("TV", "Tuvalu"), ("VU", "Vanuatu"),
)

# Deliberately selected first-wave African jurisdictions. More can be added
# without a schema change.
AFRICA_FIRST_WAVE = (
    ("ZA", "South Africa"), ("KE", "Kenya"), ("EG", "Egypt"), ("NG", "Nigeria"),
    ("GH", "Ghana"), ("ET", "Ethiopia"), ("TZ", "United Republic of Tanzania"),
    ("UG", "Uganda"), ("RW", "Rwanda"), ("MA", "Morocco"), ("DZ", "Algeria"),
)

ADDITIONAL_AMERICAS = (("BR", "Brazil"),)


EXTENDED_PUBLIC_SOURCES: dict[str, dict] = {
    "jp_mhlw_nabii": {
        "source_id": "jp_mhlw_nabii",
        "name": "Japan Medical Information Net (NABII) Open Data",
        "owner": "Ministry of Health, Labour and Welfare, Japan",
        "official_url": "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/kenkou_iryou/iryou/teikyouseido/",
        "data_class": "official_national_medical_institution_and_pharmacy_directory",
        "geography": "JAPAN",
        "country_code": "JP",
        "country_name": "Japan",
        "ingestion_types": ["public_healthcare_entities"],
        "trust_level": "OFFICIAL_PUBLIC_DATA",
        "live_fetch_status": "PUBLIC_OPEN_DATA_AVAILABLE_IMPORT_ADAPTER_REQUIRED",
        "personal_data_allowed": False,
        "notes": "MHLW describes NABII as a nationwide search system for medical institutions and pharmacies and publishes open data. Imported rows remain unverified/not-connected in ZENDOC.",
    },
    "fr_ans_annuaire_sante": {
        "source_id": "fr_ans_annuaire_sante",
        "name": "France Annuaire Sante / FINESS-RPPS public data",
        "owner": "Agence du Numerique en Sante, France",
        "official_url": "https://esante.gouv.fr/produits-services/annuaire-sante",
        "data_class": "authoritative_health_structure_and_professional_directory",
        "geography": "FRANCE",
        "country_code": "FR",
        "country_name": "France",
        "ingestion_types": ["public_healthcare_entities"],
        "trust_level": "AUTHORITATIVE_REGISTRY",
        "live_fetch_status": "PUBLIC_FHIR_API_AND_DOWNLOADS_AVAILABLE",
        "personal_data_allowed": False,
        "notes": "Use public structure fields from FINESS/Annuaire Sante and comply with published terms. Do not treat professional data as unrestricted personal-data bulk content.",
    },
    "br_cnes": {
        "source_id": "br_cnes",
        "name": "Brazil CNES National Registry of Health Establishments",
        "owner": "Ministry of Health, Brazil / DATASUS",
        "official_url": "https://dadosabertos.saude.gov.br/dataset/cnes-cadastro-nacional-de-estabelecimentos-de-saude",
        "data_class": "authoritative_national_health_establishment_registry",
        "geography": "BRAZIL",
        "country_code": "BR",
        "country_name": "Brazil",
        "ingestion_types": ["public_healthcare_entities"],
        "trust_level": "AUTHORITATIVE_REGISTRY",
        "live_fetch_status": "PUBLIC_DOWNLOAD_AND_API",
        "personal_data_allowed": False,
        "notes": "CNES is the official registry for health establishments in Brazil. Preserve CNES identifier and snapshot/update date.",
    },
    "il_moh_health_centers": {
        "source_id": "il_moh_health_centers",
        "name": "Israel Ministry of Health medical center lists",
        "owner": "Ministry of Health, Israel",
        "official_url": "https://www.gov.il/he/departments/dynamiccollectors/health-centers-list-db",
        "data_class": "official_medical_center_directory",
        "geography": "ISRAEL",
        "country_code": "IL",
        "country_name": "Israel",
        "ingestion_types": [],
        "trust_level": "OFFICIAL_PUBLIC_DATA",
        "live_fetch_status": "PUBLIC_LOOKUP_REFERENCE_ONLY_UNTIL_APPROVED_EXPORT_IDENTIFIED",
        "personal_data_allowed": False,
        "notes": "Government medical-center and registry lookups are approved for discovery/verification. No bulk extraction path is assumed.",
    },
    "au_nhsd": {
        "source_id": "au_nhsd",
        "name": "Australia National Health Services Directory",
        "owner": "Healthdirect Australia",
        "official_url": "https://about.healthdirect.gov.au/resources/news/national-health-service-directory-connecting-the-community-to-care",
        "data_class": "national_health_service_directory",
        "geography": "AUSTRALIA",
        "country_code": "AU",
        "country_name": "Australia",
        "ingestion_types": [],
        "trust_level": "AUTHORITATIVE_REGISTRY",
        "live_fetch_status": "NATIONAL_DIRECTORY_PUBLIC_SEARCH_INTEGRATION_ACCESS_REVIEW_REQUIRED",
        "personal_data_allowed": False,
        "notes": "NHSD is a trusted national directory and Service Finder is its public interface. Do not bulk-copy it unless an authorised API/export path is approved.",
    },
    "nz_healthpoint": {
        "source_id": "nz_healthpoint",
        "name": "New Zealand Healthpoint provider directory",
        "owner": "Healthpoint New Zealand",
        "official_url": "https://www.healthpoint.co.nz/",
        "data_class": "national_health_service_directory",
        "geography": "NEW_ZEALAND",
        "country_code": "NZ",
        "country_name": "New Zealand",
        "ingestion_types": [],
        "trust_level": "PUBLIC_PROVIDER_DIRECTORY",
        "live_fetch_status": "PUBLIC_SEARCH_SCRAPING_PROHIBITED_PERMISSION_REQUIRED_FOR_EXTRACTION",
        "personal_data_allowed": False,
        "notes": "Healthpoint states automated extraction/scraping is prohibited without prior written permission. ZENDOC must use an authorised integration or independent official source instead.",
    },
    "za_national_health": {
        "source_id": "za_national_health",
        "name": "South Africa National Department of Health facility/service references",
        "owner": "National Department of Health, South Africa",
        "official_url": "https://www.health.gov.za/",
        "data_class": "official_public_health_facility_reference",
        "geography": "SOUTH_AFRICA",
        "country_code": "ZA",
        "country_name": "South Africa",
        "ingestion_types": [],
        "trust_level": "OFFICIAL_PUBLIC_DATA",
        "live_fetch_status": "PUBLIC_PROGRAM_AND_FACILITY_PAGES_NO_NATIONAL_BULK_EXPORT_ASSUMED",
        "personal_data_allowed": False,
        "notes": "Use official PHC/facility publications and provincial sources only when a dated, permitted artifact is available.",
    },
    "ir_mohme": {
        "source_id": "ir_mohme",
        "name": "Iran Ministry of Health and Medical Education",
        "owner": "Ministry of Health and Medical Education, Iran",
        "official_url": "https://behdasht.gov.ir/",
        "data_class": "official_health_authority_reference",
        "geography": "IRAN",
        "country_code": "IR",
        "country_name": "Iran",
        "ingestion_types": [],
        "trust_level": "OFFICIAL_PUBLIC_DATA",
        "live_fetch_status": "OFFICIAL_REFERENCE_SOURCE_DATASET_DISCOVERY_REQUIRED",
        "personal_data_allowed": False,
        "notes": "Authority registered for source discovery. No national bulk facility feed is claimed until a verified permitted dataset is identified.",
    },
}


def install_continental_coverage() -> None:
    for code, name in ASIA:
        existing = COUNTRIES.get(code, {})
        merged = _country(code, name, "Asia")
        merged.update(existing)
        merged["continent"] = "Asia"
        COUNTRIES[code] = merged
    for code, name in EUROPE:
        existing = COUNTRIES.get(code, {})
        merged = _country(code, name, "Europe")
        merged.update(existing)
        merged["continent"] = "Europe"
        COUNTRIES[code] = merged
    for code, name in OCEANIA:
        existing = COUNTRIES.get(code, {})
        merged = _country(code, name, "Oceania")
        merged.update(existing)
        merged["continent"] = "Oceania"
        COUNTRIES[code] = merged
    for code, name in AFRICA_FIRST_WAVE:
        existing = COUNTRIES.get(code, {})
        merged = _country(code, name, "Africa", "FIRST_WAVE_SOURCE_DISCOVERY")
        merged.update(existing)
        merged["continent"] = "Africa"
        COUNTRIES[code] = merged
    for code, name in ADDITIONAL_AMERICAS:
        existing = COUNTRIES.get(code, {})
        merged = _country(code, name, "South America", "OFFICIAL_SOURCE_REGISTERED")
        merged.update(existing)
        merged["continent"] = "South America"
        COUNTRIES[code] = merged

    for source_id, source in EXTENDED_PUBLIC_SOURCES.items():
        GLOBAL_SOURCES[source_id] = deepcopy(source)

    # Promote source maturity only where we have an explicit reviewed source.
    source_country_codes = {source["country_code"] for source in EXTENDED_PUBLIC_SOURCES.values()}
    for code in source_country_codes:
        if code in COUNTRIES and COUNTRIES[code]["coverage_status"] == "SOURCE_DISCOVERY_REQUIRED":
            COUNTRIES[code]["coverage_status"] = "OFFICIAL_SOURCE_REGISTERED"


def continent_coverage_summary() -> dict[str, dict]:
    summary: dict[str, dict] = {}
    for country in COUNTRIES.values():
        continent = country.get("continent") or "Other"
        bucket = summary.setdefault(continent, {"jurisdiction_count": 0, "source_registered_count": 0})
        bucket["jurisdiction_count"] += 1
        if country.get("coverage_status") not in {"SOURCE_DISCOVERY_REQUIRED", "FIRST_WAVE_SOURCE_DISCOVERY"}:
            bucket["source_registered_count"] += 1
    return summary
