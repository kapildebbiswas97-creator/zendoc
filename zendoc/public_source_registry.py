"""Official/public source registry for pilot ingestion.

Only public metadata is represented here. Personal beneficiary, claims,
coverage, health-record, or private provider data must use separately
authorized partner integrations.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PublicIngestionSource:
    source_id: str
    name: str
    owner: str
    official_url: str
    data_class: str
    geography: str
    ingestion_types: tuple[str, ...]
    trust_level: str
    live_fetch_status: str
    personal_data_allowed: bool
    notes: str

    def to_dict(self) -> dict:
        data = asdict(self)
        data["ingestion_types"] = list(self.ingestion_types)
        return data


SOURCES = {
    "lgd": PublicIngestionSource(
        source_id="lgd",
        name="Local Government Directory",
        owner="Ministry of Panchayati Raj, Government of India",
        official_url="https://lgdirectory.gov.in/",
        data_class="official_administrative_directory",
        geography="INDIA",
        ingestion_types=("geography_nodes",),
        trust_level="OFFICIAL_PUBLIC_DATA",
        live_fetch_status="MANUAL_OR_CONFIGURED_CONNECTOR_REQUIRED",
        personal_data_allowed=False,
        notes="Use downloadable official administrative directories with batch checksum, source date, and provenance.",
    ),
    "data_gov_hospitals": PublicIngestionSource(
        source_id="data_gov_hospitals",
        name="Open Government Data Platform India - Hospital Directory",
        owner="Government of India / NIC",
        official_url="https://www.data.gov.in/",
        data_class="official_public_healthcare_directory",
        geography="INDIA",
        ingestion_types=("public_healthcare_entities",),
        trust_level="OFFICIAL_PUBLIC_DATA",
        live_fetch_status="DATASET_SPECIFIC_API_OR_DOWNLOAD_REQUIRED",
        personal_data_allowed=False,
        notes="Imported records remain OFFICIAL_PUBLIC_DATA and are not automatically ZENDOC_VERIFIED or bookable.",
    ),
    "abdm_hfr": PublicIngestionSource(
        source_id="abdm_hfr",
        name="ABDM Health Facility Registry",
        owner="National Health Authority",
        official_url="https://hfr.abdm.gov.in/",
        data_class="authoritative_health_facility_registry",
        geography="INDIA",
        ingestion_types=("public_healthcare_entities",),
        trust_level="AUTHORITATIVE_REGISTRY",
        live_fetch_status="ONBOARDING_OR_AUTHORIZED_ACCESS_REQUIRED",
        personal_data_allowed=False,
        notes="Do not claim live HFR access unless ABDM onboarding and authorized access are configured and verified.",
    ),
    "abdm_hpr": PublicIngestionSource(
        source_id="abdm_hpr",
        name="ABDM Healthcare Professionals Registry",
        owner="National Health Authority",
        official_url="https://hpr.abdm.gov.in/",
        data_class="authoritative_health_professional_registry",
        geography="INDIA",
        ingestion_types=(),
        trust_level="AUTHORITATIVE_REGISTRY",
        live_fetch_status="PUBLIC_INFORMATION_WITH_AUTHORIZED_INTEGRATION_REQUIRED_FOR_SYSTEMATIC_ACCESS",
        personal_data_allowed=False,
        notes="Use for professional verification boundaries. Do not bulk-copy personal/professional records without an authorized access path and purpose.",
    ),
    "nmc_imr": PublicIngestionSource(
        source_id="nmc_imr",
        name="National Medical Commission - Indian Medical Register",
        owner="National Medical Commission",
        official_url="https://www.nmc.org.in/information-desk/indian-medical-register/",
        data_class="official_professional_registration_lookup",
        geography="INDIA",
        ingestion_types=(),
        trust_level="OFFICIAL_PUBLIC_DATA",
        live_fetch_status="PUBLIC_WEB_LOOKUP_NO_VERIFIED_BULK_API",
        personal_data_allowed=False,
        notes="Useful for doctor registration verification. NMC states the IMR view is still being updated; use lookup verification rather than treating it as a complete live roster.",
    ),
    "nmc_medical_colleges": PublicIngestionSource(
        source_id="nmc_medical_colleges",
        name="National Medical Commission - College and Course Search",
        owner="National Medical Commission",
        official_url="https://www.nmc.org.in/information-desk/college-and-course-search/",
        data_class="official_medical_education_directory",
        geography="INDIA",
        ingestion_types=(),
        trust_level="OFFICIAL_PUBLIC_DATA",
        live_fetch_status="PUBLIC_WEB_LOOKUP_OR_PUBLISHED_SEAT_MATRIX",
        personal_data_allowed=False,
        notes="Medical colleges, courses, recognition state and seat information. Keep academic-year freshness with every imported snapshot.",
    ),
    "inc_nursing_institutions": PublicIngestionSource(
        source_id="inc_nursing_institutions",
        name="Indian Nursing Council - Recognised Nursing Institutions",
        owner="Indian Nursing Council",
        official_url="https://www.indiannursingcouncil.org/nursing-institute-for-the-year-2025-26-and-2026-27",
        data_class="official_nursing_education_directory",
        geography="INDIA",
        ingestion_types=(),
        trust_level="OFFICIAL_PUBLIC_DATA",
        live_fetch_status="PUBLIC_PUBLISHED_LISTS",
        personal_data_allowed=False,
        notes="Use academic-year-specific institution lists and preserve recognition/withdrawal status and source date.",
    ),
    "pci_approved_institutions": PublicIngestionSource(
        source_id="pci_approved_institutions",
        name="Pharmacy Council of India - Approved Institutions",
        owner="Pharmacy Council of India",
        official_url="https://pci.gov.in/",
        data_class="official_pharmacy_education_directory",
        geography="INDIA",
        ingestion_types=(),
        trust_level="OFFICIAL_PUBLIC_DATA",
        live_fetch_status="PUBLIC_PUBLISHED_LISTS",
        personal_data_allowed=False,
        notes="Approved pharmacy institutions and intake/approval information. Treat each published academic cycle as a dated snapshot.",
    ),
    "data_gov_hmis": PublicIngestionSource(
        source_id="data_gov_hmis",
        name="Open Government Data Platform India - HMIS Indicators",
        owner="Ministry of Health and Family Welfare / Government of India",
        official_url="https://www.data.gov.in/catalog/item-wise-hmis-report-all-states-and-districts-across-months",
        data_class="official_aggregate_public_health_indicators",
        geography="INDIA",
        ingestion_types=(),
        trust_level="OFFICIAL_PUBLIC_DATA",
        live_fetch_status="CATALOG_API_OR_DOWNLOAD_AVAILABLE_DATASET_DEPENDENT",
        personal_data_allowed=False,
        notes="Aggregate state/district health-service and disease indicators for planning/analytics only; never infer an individual patient's condition from aggregate HMIS data.",
    ),
    "eraktkosh": PublicIngestionSource(
        source_id="eraktkosh",
        name="e-RaktKosh Blood Centre Directory and Blood Availability",
        owner="Ministry of Health and Family Welfare / C-DAC",
        official_url="https://eraktkosh.mohfw.gov.in/",
        data_class="official_blood_centre_directory_and_live_availability",
        geography="INDIA",
        ingestion_types=("public_healthcare_entities",),
        trust_level="OFFICIAL_PUBLIC_DATA",
        live_fetch_status="PUBLIC_WEB_LOOKUP_LIVE_STOCK_API_NOT_VERIFIED",
        personal_data_allowed=False,
        notes="Directory metadata may be ingested with freshness. Blood availability is dynamic and must retain last-updated time; never cache it as indefinitely available.",
    ),
    "clinical_establishments": PublicIngestionSource(
        source_id="clinical_establishments",
        name="National Register of Clinical Establishments",
        owner="Ministry of Health and Family Welfare",
        official_url="https://clinicalestablishments.mohfw.gov.in/portal/cerrs/national-register",
        data_class="official_clinical_establishment_register",
        geography="INDIA_PARTICIPATING_STATES_UTS",
        ingestion_types=("public_healthcare_entities",),
        trust_level="OFFICIAL_PUBLIC_DATA",
        live_fetch_status="PUBLIC_WEB_REGISTER_STATE_COVERAGE_VARIES",
        personal_data_allowed=False,
        notes="Coverage is limited to adopting States/UTs and portal migration may be incomplete. Preserve registration type/status and jurisdiction.",
    ),
    "nabh_directory": PublicIngestionSource(
        source_id="nabh_directory",
        name="NABH Accredited Healthcare Organisation Directory",
        owner="National Accreditation Board for Hospitals and Healthcare Providers / Quality Council of India",
        official_url="https://nabh.co/find-a-healthcare-organisation/",
        data_class="official_accreditation_directory",
        geography="INDIA",
        ingestion_types=("public_healthcare_entities",),
        trust_level="ACCREDITATION_BODY_PUBLIC_DATA",
        live_fetch_status="PUBLIC_WEB_LOOKUP_NO_VERIFIED_BULK_API",
        personal_data_allowed=False,
        notes="Use accreditation/certification as a quality signal only. NABH warns its new-site migration may leave some records incomplete or inconsistent.",
    ),
    "nabl_labs": PublicIngestionSource(
        source_id="nabl_labs",
        name="NABL Accredited Laboratory Directory",
        owner="National Accreditation Board for Testing and Calibration Laboratories / Quality Council of India",
        official_url="https://nabl-india.org/",
        data_class="official_laboratory_accreditation_directory",
        geography="INDIA",
        ingestion_types=("public_healthcare_entities",),
        trust_level="ACCREDITATION_BODY_PUBLIC_DATA",
        live_fetch_status="PUBLIC_WEB_LOOKUP_NO_VERIFIED_BULK_API",
        personal_data_allowed=False,
        notes="Useful for verified medical-lab accreditation and scope lookup. Accreditation does not imply a live appointment slot, current price, or ZENDOC connectivity.",
    ),
    "pmbjp_kendras": PublicIngestionSource(
        source_id="pmbjp_kendras",
        name="Pradhan Mantri Bhartiya Janaushadhi Pariyojana - Kendra Directory",
        owner="Pharmaceuticals & Medical Devices Bureau of India",
        official_url="https://janaushadhi.gov.in/locate-kendra",
        data_class="official_public_pharmacy_directory",
        geography="INDIA",
        ingestion_types=("public_healthcare_entities",),
        trust_level="OFFICIAL_PUBLIC_DATA",
        live_fetch_status="PUBLIC_WEB_SEARCH_NO_VERIFIED_BULK_API",
        personal_data_allowed=False,
        notes="Kendra code/location/address metadata can support discovery. Do not infer live medicine stock from Kendra presence.",
    ),
    "pmbjp_products": PublicIngestionSource(
        source_id="pmbjp_products",
        name="Jan Aushadhi Product and MRP List",
        owner="Pharmaceuticals & Medical Devices Bureau of India",
        official_url="https://www.janaushadhi.gov.in/productportfolio/ProductmrpList",
        data_class="official_medicine_product_price_list",
        geography="INDIA",
        ingestion_types=(),
        trust_level="OFFICIAL_PUBLIC_DATA",
        live_fetch_status="PUBLIC_SEARCH_AND_DOWNLOAD",
        personal_data_allowed=False,
        notes="Product code/name/unit size/MRP can support medicine-price reference. It is not proof of stock at a particular Kendra.",
    ),
    "nppa_prices": PublicIngestionSource(
        source_id="nppa_prices",
        name="NPPA Pharma Sahi Daam",
        owner="National Pharmaceutical Pricing Authority",
        official_url="https://www.nppaindia.nic.in/pharma_sahi_daam",
        data_class="official_medicine_price_reference",
        geography="INDIA",
        ingestion_types=(),
        trust_level="OFFICIAL_PUBLIC_DATA",
        live_fetch_status="PUBLIC_PRICE_LOOKUP_NO_VERIFIED_BULK_API",
        personal_data_allowed=False,
        notes="Use for government price-limit/reference checks. Retail availability and actual transaction price still require pharmacy/provider data.",
    ),
    "cdsco_approved_drugs": PublicIngestionSource(
        source_id="cdsco_approved_drugs",
        name="CDSCO Approved New Drugs",
        owner="Central Drugs Standard Control Organization",
        official_url="https://www.cdsco.gov.in/opencms/opencms/en/Approval_new/Approved-New-Drugs/",
        data_class="official_drug_regulatory_reference",
        geography="INDIA",
        ingestion_types=(),
        trust_level="OFFICIAL_PUBLIC_DATA",
        live_fetch_status="PUBLIC_PUBLISHED_LISTS",
        personal_data_allowed=False,
        notes="Regulatory approval reference only. Do not convert regulatory listing into prescribing advice.",
    ),
    "cdsco_nlem": PublicIngestionSource(
        source_id="cdsco_nlem",
        name="National List of Essential Medicines",
        owner="Ministry of Health and Family Welfare / CDSCO",
        official_url="https://cdsco.mohfw.gov.in/opencms/opencms/en/consumer/Essential-Medicines/",
        data_class="official_essential_medicines_reference",
        geography="INDIA",
        ingestion_types=(),
        trust_level="OFFICIAL_PUBLIC_DATA",
        live_fetch_status="PUBLIC_PUBLISHED_LIST",
        personal_data_allowed=False,
        notes="Use for essential-medicine reference and planning, not individualized prescribing.",
    ),
    "pmjay_hospitals": PublicIngestionSource(
        source_id="pmjay_hospitals",
        name="AB PM-JAY Empanelled Hospital Discovery",
        owner="National Health Authority / Government of India",
        official_url="https://abdm.gov.in/UHI",
        data_class="official_scheme_empanelled_provider_directory",
        geography="INDIA",
        ingestion_types=("public_healthcare_entities",),
        trust_level="OFFICIAL_PUBLIC_DATA",
        live_fetch_status="PUBLIC_FIND_HOSPITAL_SERVICE_INTEGRATION_NOT_ASSUMED",
        personal_data_allowed=False,
        notes="Empanelment can support scheme-aware discovery. Do not infer patient eligibility, authorization, package approval, or a live bed/slot.",
    ),
    "myscheme": PublicIngestionSource(
        source_id="myscheme",
        name="myScheme Government Scheme Discovery",
        owner="Digital India Corporation / NeGD / Government of India",
        official_url="https://www.myscheme.gov.in/",
        data_class="official_government_scheme_discovery",
        geography="INDIA",
        ingestion_types=(),
        trust_level="OFFICIAL_PUBLIC_DATA",
        live_fetch_status="PUBLIC_WEB_DISCOVERY_NO_VERIFIED_BULK_API",
        personal_data_allowed=False,
        notes="Useful for CareFin scheme discovery, eligibility criteria, benefits, documents and application links. ZENDOC must still label results as discovery until authoritative eligibility is confirmed.",
    ),
    "swasthya_sathi_hospitals": PublicIngestionSource(
        source_id="swasthya_sathi_hospitals",
        name="Swasthya Sathi Active Hospital Directory",
        owner="Government of West Bengal",
        official_url="https://swasthyasathi.gov.in/",
        data_class="official_state_scheme_empanelled_provider_directory",
        geography="WEST_BENGAL",
        ingestion_types=("public_healthcare_entities",),
        trust_level="OFFICIAL_PUBLIC_DATA",
        live_fetch_status="PUBLIC_ACTIVE_HOSPITAL_LOOKUP_NO_VERIFIED_BULK_API",
        personal_data_allowed=False,
        notes="Use active hospital/facility/service metadata for West Bengal pilot discovery. Beneficiary entitlement, preauthorization and claims remain private/authoritative workflows.",
    ),
    "wbhs_empanelled_hco": PublicIngestionSource(
        source_id="wbhs_empanelled_hco",
        name="West Bengal Health Scheme Empanelled Health Care Organisations",
        owner="Finance Department, Government of West Bengal",
        official_url="https://healthscheme.wb.gov.in/Home/wbhs_empanelled_hco.aspx",
        data_class="official_state_scheme_empanelled_provider_directory",
        geography="WEST_BENGAL",
        ingestion_types=("public_healthcare_entities",),
        trust_level="OFFICIAL_PUBLIC_DATA",
        live_fetch_status="PUBLIC_WEB_DIRECTORY_AND_DOWNLOAD",
        personal_data_allowed=False,
        notes="Includes hospital code, name, address, phone, class, validity and facilities. Scheme membership does not prove general-public eligibility or live capacity.",
    ),
    "data_gov_cghs_hospitals": PublicIngestionSource(
        source_id="data_gov_cghs_hospitals",
        name="CGHS Empanelled Hospitals - Open Government Data",
        owner="Central Government Health Scheme / Ministry of Health and Family Welfare",
        official_url="https://www.data.gov.in/resource/list-hospitals-empaneled-under-cghs-all-over-india",
        data_class="official_scheme_empanelled_provider_directory",
        geography="INDIA",
        ingestion_types=("public_healthcare_entities",),
        trust_level="OFFICIAL_PUBLIC_DATA",
        live_fetch_status="PUBLIC_DOWNLOAD_RESOURCE_API_NOT_AVAILABLE",
        personal_data_allowed=False,
        notes="Useful scheme-provider directory snapshot. Preserve update date; do not infer current appointment availability or beneficiary entitlement.",
    ),
    "cdsco_state_drug_control": PublicIngestionSource(
        source_id="cdsco_state_drug_control",
        name="CDSCO State Drugs Control Gateway",
        owner="Central Drugs Standard Control Organization / State Drug Controllers",
        official_url="https://cdsco.gov.in/opencms/opencms/en/State-Drugs-Control/",
        data_class="official_state_drug_regulator_directory",
        geography="INDIA_ALL_STATES_UTS",
        ingestion_types=("public_healthcare_entities",),
        trust_level="OFFICIAL_PUBLIC_DATA",
        live_fetch_status="STATE_SPECIFIC_PUBLIC_PORTALS_BULK_ACCESS_VARIES",
        personal_data_allowed=False,
        notes=(
            "Gateway to every State/UT Drug Controller. Use state-specific public retail/wholesale licence "
            "searches or published lists where available. A licence directory is not proof of current stock."
        ),
    ),
    "delhi_government_hospitals": PublicIngestionSource(
        source_id="delhi_government_hospitals",
        name="Delhi Government Hospitals Directory",
        owner="Department of Health & Family Welfare, Government of NCT of Delhi",
        official_url="https://health.delhi.gov.in/health/delhi-government-hospitals",
        data_class="official_state_public_hospital_directory",
        geography="DELHI",
        ingestion_types=("public_healthcare_entities",),
        trust_level="OFFICIAL_PUBLIC_DATA",
        live_fetch_status="PUBLIC_WEB_DIRECTORY",
        personal_data_allowed=False,
        notes="Official government-hospital names, addresses and public contacts. Does not imply live beds or appointments.",
    ),
    "delhi_registered_nursing_homes": PublicIngestionSource(
        source_id="delhi_registered_nursing_homes",
        name="Delhi Registered Functional Nursing Homes",
        owner="Department of Health & Family Welfare, Government of NCT of Delhi",
        official_url="https://health.delhi.gov.in/health/services",
        data_class="official_state_nursing_home_register",
        geography="DELHI",
        ingestion_types=("public_healthcare_entities",),
        trust_level="OFFICIAL_PUBLIC_DATA",
        live_fetch_status="PUBLIC_PUBLISHED_LIST_SNAPSHOT",
        personal_data_allowed=False,
        notes=(
            "Use registration number, facility name/address, beds and registration validity from the official list. "
            "Validity/renewal must be preserved; do not treat expired/under-process status as current approval."
        ),
    ),
    "data_gov_blood_banks": PublicIngestionSource(
        source_id="data_gov_blood_banks",
        name="Blood Bank Directory - Open Government Data",
        owner="Ministry of Health and Family Welfare / NIHFW",
        official_url="https://www.data.gov.in/catalog/blood-bank-directory-national-health-portal",
        data_class="official_public_blood_bank_directory",
        geography="INDIA",
        ingestion_types=("public_healthcare_entities",),
        trust_level="OFFICIAL_PUBLIC_DATA",
        live_fetch_status="PUBLIC_CATALOG_API_OR_DOWNLOAD",
        personal_data_allowed=False,
        notes="Directory snapshot with address/geolocation/contact metadata. Prefer e-RaktKosh for dynamic blood availability and retain source freshness.",
    ),
}


def get_public_ingestion_source(source_id: str) -> dict | None:
    source = SOURCES.get(str(source_id or "").strip().lower())
    return source.to_dict() if source else None


def list_public_ingestion_sources() -> list[dict]:
    return [source.to_dict() for source in SOURCES.values()]

PUBLIC_DATA_COVERAGE = {
    "geography": {
        "status": "STRONG_OFFICIAL_COVERAGE",
        "sources": ["lgd"],
        "notes": "State/UT, district, sub-district, local-body and village coverage through official LGD snapshots.",
    },
    "hospitals_and_nursing_homes": {
        "status": "MULTI_SOURCE_PARTIAL_TO_STRONG",
        "sources": [
            "data_gov_hospitals",
            "clinical_establishments",
            "nabh_directory",
            "pmjay_hospitals",
            "data_gov_cghs_hospitals",
            "wbhs_empanelled_hco",
            "swasthya_sathi_hospitals",
            "delhi_government_hospitals",
            "delhi_registered_nursing_homes",
        ],
        "notes": "Coverage varies by scheme/state/registration law; merge by provenance, never assume one registry is complete.",
    },
    "diagnostics_and_labs": {
        "status": "MULTI_SOURCE_PARTIAL",
        "sources": ["clinical_establishments", "nabl_labs", "nabh_directory"],
        "notes": "Public/accreditation directories are useful for discovery/verification; live prices and slots require provider data.",
    },
    "doctors_and_health_professionals": {
        "status": "PUBLIC_VERIFICATION_LOOKUP_NOT_BULK_ROSTER",
        "sources": ["abdm_hpr", "nmc_imr"],
        "notes": "Use professional registration for verification. Do not bulk-copy personal professional records without authorized access.",
    },
    "pharmacies_and_medical_shops": {
        "status": "STATE_FRAGMENTED",
        "sources": ["pmbjp_kendras", "cdsco_state_drug_control"],
        "notes": "Jan Aushadhi has national public discovery; general retail pharmacy licences are mainly state-regulator systems with varying public access.",
    },
    "medicine_catalog_and_prices": {
        "status": "STRONG_REFERENCE_COVERAGE",
        "sources": ["pmbjp_products", "nppa_prices", "cdsco_approved_drugs", "cdsco_nlem"],
        "notes": "Useful for catalogue/regulatory/MRP/reference data, not pharmacy-specific live stock or actual transaction price.",
    },
    "blood_centres": {
        "status": "OFFICIAL_DIRECTORY_PLUS_DYNAMIC_LOOKUP",
        "sources": ["data_gov_blood_banks", "eraktkosh"],
        "notes": "Directory can be cached with freshness; live blood availability must remain time-sensitive.",
    },
    "schemes_and_empanelled_providers": {
        "status": "STRONG_DISCOVERY_PARTIAL_OUTCOME",
        "sources": ["pmjay_hospitals", "myscheme", "swasthya_sathi_hospitals", "wbhs_empanelled_hco", "data_gov_cghs_hospitals"],
        "notes": "Discovery/empanelment can be public; beneficiary eligibility, approval, claims and payments require authoritative/private workflows.",
    },
    "aggregate_public_health": {
        "status": "OFFICIAL_AGGREGATE",
        "sources": ["data_gov_hmis"],
        "notes": "Use only for planning/analytics; never infer an individual's health condition.",
    },
    "patient_medical_records": {
        "status": "PRIVATE_AUTHORIZATION_ONLY",
        "sources": [],
        "notes": (
            "There is no lawful public patient-record dataset for ZENDOC to scrape. Records must come from the patient, "
            "an authorized provider/ABDM-style workflow, or another explicitly consented source."
        ),
    },
    "provider_private_clinical_records": {
        "status": "PRIVATE_AUTHORIZATION_ONLY",
        "sources": [],
        "notes": "Clinical notes and private provider records are not public-directory data and remain purpose/consent gated.",
    },
}


def public_data_coverage_matrix() -> dict:
    return {
        category: {
            **details,
            "source_details": [
                SOURCES[source_id].to_dict()
                for source_id in details.get("sources", [])
                if source_id in SOURCES
            ],
        }
        for category, details in PUBLIC_DATA_COVERAGE.items()
    }

