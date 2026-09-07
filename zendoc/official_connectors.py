"""Official/public connector planning and source-specific normalization.

This module intentionally separates:
- sources with a stable/configurable machine-readable feed;
- sources that need a dated download/manual snapshot;
- sources that require onboarding/authorized access.

It never treats a public directory as proof of live availability, booking,
beneficiary eligibility, provider verification, or partner connectivity.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any

from .dataset_adapters import adapt_records
from .public_source_registry import get_public_ingestion_source


@dataclass(frozen=True)
class ConnectorProfile:
    source_id: str
    connector_type: str
    ingestion_type: str | None
    availability: str
    config_keys: tuple[str, ...]
    refresh_cadence: str
    notes: str

    def to_dict(self) -> dict:
        data = asdict(self)
        data["config_keys"] = list(self.config_keys)
        return data


CONNECTOR_PROFILES = {
    "data_gov_hospitals": ConnectorProfile(
        source_id="data_gov_hospitals",
        connector_type="DATA_GOV_RESOURCE_API_OR_DOWNLOAD",
        ingestion_type="public_healthcare_entities",
        availability="CONFIGURABLE_NOW",
        config_keys=("ZENDOC_DATA_GOV_API_KEY", "ZENDOC_DATA_GOV_HOSPITAL_RESOURCE_ID"),
        refresh_cadence="MONTHLY",
        notes=(
            "Use the current National Hospital Directory resource. Resource/API identifiers are configuration, "
            "not code constants, so a dataset replacement does not require a release."
        ),
    ),
    "lgd": ConnectorProfile(
        source_id="lgd",
        connector_type="DATA_GOV_RESOURCE_API_OR_DOWNLOAD",
        ingestion_type="geography_nodes",
        availability="CONFIGURABLE_NOW",
        config_keys=("ZENDOC_DATA_GOV_API_KEY", "ZENDOC_LGD_RESOURCE_ID"),
        refresh_cadence="MONTHLY",
        notes="Use an official LGD resource/download and preserve LGD codes plus snapshot freshness.",
    ),
    "data_gov_blood_banks": ConnectorProfile(
        source_id="data_gov_blood_banks",
        connector_type="DATA_GOV_RESOURCE_API_OR_DOWNLOAD",
        ingestion_type="public_healthcare_entities",
        availability="CONFIGURABLE_NOW",
        config_keys=("ZENDOC_DATA_GOV_API_KEY", "ZENDOC_DATA_GOV_BLOOD_BANK_RESOURCE_ID"),
        refresh_cadence="MONTHLY_OR_SOURCE_UPDATE",
        notes="Directory only. Dynamic blood availability remains a separate real-time data gap.",
    ),
    "wbhs_empanelled_hco": ConnectorProfile(
        source_id="wbhs_empanelled_hco",
        connector_type="DATED_OFFICIAL_DOWNLOAD_OR_MANUAL_SNAPSHOT",
        ingestion_type="public_healthcare_entities",
        availability="MANUAL_SNAPSHOT_NOW",
        config_keys=(),
        refresh_cadence="WEEKLY_OR_SOURCE_UPDATE",
        notes=(
            "Use the official WBHS downloadable/searchable directory. Preserve hospital code, class, validity, "
            "facilities and snapshot date. Do not infer general-public eligibility or live capacity."
        ),
    ),
    "cdsco_state_drug_control": ConnectorProfile(
        source_id="cdsco_state_drug_control",
        connector_type="STATE_SPECIFIC_PUBLIC_LOOKUP_OR_SNAPSHOT",
        ingestion_type="public_healthcare_entities",
        availability="STATE_FRAGMENTED",
        config_keys=(),
        refresh_cadence="STATE_SOURCE_DEFINED",
        notes=(
            "Use State/UT Drug Controller public licence searches or published snapshots where available. "
            "Do not assume national bulk retail-pharmacy coverage from CDSCO."
        ),
    ),
    "kerala_health_institutions": ConnectorProfile(
        source_id="kerala_health_institutions",
        connector_type="PUBLIC_SEARCHABLE_DIRECTORY_SNAPSHOT",
        ingestion_type="public_healthcare_entities",
        availability="MANUAL_SNAPSHOT_NOW",
        config_keys=(),
        refresh_cadence="WEEKLY_OR_SOURCE_UPDATE",
        notes="Preserve district, category, address/contact, sanctioned beds and functional beds; never treat bed counts as live vacancy.",
    ),
    "kerala_dhs_hospitals": ConnectorProfile(
        source_id="kerala_dhs_hospitals",
        connector_type="DATED_OFFICIAL_WEB_SNAPSHOT",
        ingestion_type="public_healthcare_entities",
        availability="MANUAL_SNAPSHOT_NOW",
        config_keys=(),
        refresh_cadence="MONTHLY_OR_SOURCE_UPDATE",
        notes="Official DHS facility categories and public contacts.",
    ),
    "kerala_ehealth_hospitals": ConnectorProfile(
        source_id="kerala_ehealth_hospitals",
        connector_type="PUBLIC_SEARCH_PORTAL_SNAPSHOT",
        ingestion_type="public_healthcare_entities",
        availability="MANUAL_SNAPSHOT_NOW",
        config_keys=(),
        refresh_cadence="WEEKLY_OR_SOURCE_UPDATE",
        notes="Public hospital discovery only; authenticated patient/appointment data is out of scope for scraping.",
    ),
    "maharashtra_dmer_hospitals": ConnectorProfile(
        source_id="maharashtra_dmer_hospitals",
        connector_type="OFFICIAL_CSV_EXCEL_DOWNLOAD",
        ingestion_type="public_healthcare_entities",
        availability="MANUAL_SNAPSHOT_NOW",
        config_keys=(),
        refresh_cadence="MONTHLY_OR_SOURCE_UPDATE",
        notes="Official medical-college and attached-hospital table with district/location.",
    ),
    "maharashtra_fda_drug_licenses": ConnectorProfile(
        source_id="maharashtra_fda_drug_licenses",
        connector_type="STATE_REGULATOR_LOOKUP_OR_EXPORT",
        ingestion_type="public_healthcare_entities",
        availability="STATE_FRAGMENTED",
        config_keys=(),
        refresh_cadence="STATE_SOURCE_DEFINED",
        notes="Use only public licence lookup/export. Licence status is not proof of live medicine stock.",
    ),
    "karnataka_health_infrastructure": ConnectorProfile(
        source_id="karnataka_health_infrastructure",
        connector_type="OFFICIAL_REPORT_REFERENCE",
        ingestion_type="public_healthcare_entities",
        availability="REFERENCE_ONLY",
        config_keys=(),
        refresh_cadence="ANNUAL_OR_SOURCE_UPDATE",
        notes="Use as infrastructure/coverage reference unless a current facility-level official export is available.",
    ),
    "assam_health_institutes": ConnectorProfile(
        source_id="assam_health_institutes",
        connector_type="DATED_OFFICIAL_DOWNLOAD_OR_MANUAL_SNAPSHOT",
        ingestion_type="public_healthcare_entities",
        availability="MANUAL_SNAPSHOT_NOW",
        config_keys=(),
        refresh_cadence="MONTHLY_OR_SOURCE_UPDATE",
        notes="Assam DHS health-institute directory/download. Preserve facility type and district; no live bed/slot inference.",
    ),
    "assam_first_referral_units": ConnectorProfile(
        source_id="assam_first_referral_units",
        connector_type="DATED_OFFICIAL_WEB_SNAPSHOT",
        ingestion_type="public_healthcare_entities",
        availability="MANUAL_SNAPSHOT_NOW",
        config_keys=(),
        refresh_cadence="MONTHLY_OR_SOURCE_UPDATE",
        notes="Assam H&FW referral-unit list. Useful for district/BPHC referral discovery.",
    ),
    "assam_medical_colleges": ConnectorProfile(
        source_id="assam_medical_colleges",
        connector_type="DATED_OFFICIAL_WEB_SNAPSHOT",
        ingestion_type="public_healthcare_entities",
        availability="MANUAL_SNAPSHOT_NOW",
        config_keys=(),
        refresh_cadence="MONTHLY_OR_SOURCE_UPDATE",
        notes="Official Assam medical colleges/institutes; prioritize Dibrugarh records for competition deployment.",
    ),
    "delhi_government_hospitals": ConnectorProfile(
        source_id="delhi_government_hospitals",
        connector_type="DATED_OFFICIAL_DOWNLOAD_OR_MANUAL_SNAPSHOT",
        ingestion_type="public_healthcare_entities",
        availability="MANUAL_SNAPSHOT_NOW",
        config_keys=(),
        refresh_cadence="WEEKLY_OR_SOURCE_UPDATE",
        notes="Official Delhi government-hospital directory; operational availability remains separate.",
    ),
    "delhi_registered_nursing_homes": ConnectorProfile(
        source_id="delhi_registered_nursing_homes",
        connector_type="DATED_OFFICIAL_DOWNLOAD_OR_MANUAL_SNAPSHOT",
        ingestion_type="public_healthcare_entities",
        availability="MANUAL_SNAPSHOT_NOW",
        config_keys=(),
        refresh_cadence="WEEKLY_OR_SOURCE_UPDATE",
        notes="Preserve registration number/status/validity; do not promote expired or unverified facilities.",
    ),
    "abdm_hfr": ConnectorProfile(
        source_id="abdm_hfr",
        connector_type="AUTHORIZED_PARTNER_CONNECTOR",
        ingestion_type="public_healthcare_entities",
        availability="ONBOARDING_REQUIRED",
        config_keys=(),
        refresh_cadence="PARTNER_DEFINED",
        notes="No production HFR fetch should be enabled until ABDM onboarding and authorized access are verified.",
    ),
    "eraktkosh": ConnectorProfile(
        source_id="eraktkosh",
        connector_type="DIRECTORY_SNAPSHOT_PLUS_SEPARATE_LIVE_FEED",
        ingestion_type="public_healthcare_entities",
        availability="DIRECTORY_NOW_LIVE_STOCK_UNVERIFIED",
        config_keys=(),
        refresh_cadence="DIRECTORY_WEEKLY_LIVE_REAL_TIME",
        notes="Blood-centre directory can be imported separately from high-stakes dynamic blood availability.",
    ),
}


SOURCE_MAPPING_TEMPLATES: dict[str, dict[str, Any]] = {
    "data_gov_hospitals": {
        "ingestion_type": "public_healthcare_entities",
        "field_aliases": {
            "source_record_id": (
                "hospital_id", "hospital_code", "sr_no", "serial_no", "id",
            ),
            "name": ("hospital_name", "facility_name", "name"),
            "category": ("hospital_category", "category", "facility_type"),
            "specialty": ("specializations", "speciality", "specialty"),
            "address": ("address", "hospital_address"),
            "city": ("city", "town"),
            "district": ("district", "district_name"),
            "state": ("state", "state_name"),
            "postal_code": ("pincode", "pin_code", "postal_code"),
            "latitude": ("latitude", "lat"),
            "longitude": ("longitude", "lon", "lng"),
            "public_phone": ("telephone", "phone", "contact_number"),
            "public_email": ("email", "email_address"),
            "website": ("website", "website_link"),
        },
        "defaults": {"category": "hospital"},
    },
    "data_gov_blood_banks": {
        "ingestion_type": "public_healthcare_entities",
        "field_aliases": {
            "source_record_id": ("blood_bank_id", "bank_id", "sr_no", "id"),
            "name": ("blood_bank_name", "name", "hospital_name"),
            "address": ("address",),
            "city": ("city",),
            "district": ("district",),
            "state": ("state",),
            "postal_code": ("pincode", "pin_code"),
            "latitude": ("latitude", "lat"),
            "longitude": ("longitude", "lon", "lng"),
            "public_phone": ("contact_no", "phone", "telephone"),
            "public_email": ("email",),
        },
        "defaults": {"category": "blood_bank"},
    },
    "wbhs_empanelled_hco": {
        "ingestion_type": "public_healthcare_entities",
        "field_aliases": {
            "source_record_id": ("hospital_code", "hco_code", "code"),
            "name": ("hospital_name", "hco_name", "name"),
            "address": ("address",),
            "district": ("district",),
            "city": ("city",),
            "postal_code": ("pincode", "pin_code"),
            "public_phone": ("phone_number", "phone", "contact"),
        },
        "defaults": {"category": "hospital"},
        "metadata_aliases": {
            "hco_class": ("hco_class", "class"),
            "city_classification": ("city_classification",),
            "valid_upto": ("valid_upto", "valid_until"),
            "facilities_available": ("facilities_available", "facilities"),
        },
    },
    "kerala_health_institutions": {
        "ingestion_type": "public_healthcare_entities",
        "field_aliases": {
            "source_record_id": ("institution_code", "facility_code", "code", "id"),
            "name": ("institution_name", "facility_name", "name"),
            "category": ("institution_category", "facility_category", "category", "institution_type"),
            "address": ("address",),
            "city": ("city", "town"),
            "district": ("district",),
            "state": ("state",),
            "postal_code": ("pincode", "pin_code"),
            "public_phone": ("phone", "contact", "telephone"),
            "public_email": ("email",),
            "latitude": ("latitude", "lat"),
            "longitude": ("longitude", "lon", "lng"),
        },
        "defaults": {"state": "Kerala"},
        "metadata_aliases": {
            "sanctioned_beds": ("sanctioned_beds", "sanctioned bed", "sanctioned beds"),
            "functional_beds": ("functional_beds", "functional bed", "functional beds"),
            "rural_urban": ("rural_urban", "rural urban", "area_type"),
            "map_link": ("map", "map_link", "google_map"),
        },
    },
    "kerala_dhs_hospitals": {
        "ingestion_type": "public_healthcare_entities",
        "field_aliases": {
            "source_record_id": ("facility_code", "code", "id"),
            "name": ("facility_name", "hospital_name", "name"),
            "category": ("facility_type", "category"),
            "district": ("district",),
            "address": ("address",),
            "public_phone": ("phone", "telephone", "contact"),
        },
        "defaults": {"state": "Kerala"},
    },
    "maharashtra_dmer_hospitals": {
        "ingestion_type": "public_healthcare_entities",
        "field_aliases": {
            "source_record_id": ("college_code", "hospital_code", "code", "id"),
            "name": ("hospital_name", "attached_hospital", "medical_college_hospital", "name"),
            "category": ("category", "facility_type"),
            "district": ("district",),
            "city": ("location", "city"),
            "address": ("address",),
            "public_phone": ("phone", "telephone", "contact"),
            "website": ("website", "website_url"),
        },
        "defaults": {"state": "Maharashtra", "category": "hospital"},
        "metadata_aliases": {
            "medical_college": ("medical_college", "college_name", "medical college"),
        },
    },
    "assam_health_institutes": {
        "ingestion_type": "public_healthcare_entities",
        "field_aliases": {
            "source_record_id": ("institution_code", "facility_code", "code", "id"),
            "name": ("institution_name", "facility_name", "name"),
            "category": ("institution_type", "facility_type", "category"),
            "address": ("address",),
            "city": ("town", "city"),
            "district": ("district", "district_name"),
            "state": ("state",),
            "postal_code": ("pincode", "pin_code"),
            "public_phone": ("phone", "contact_no", "contact"),
            "public_email": ("email",),
        },
        "defaults": {"state": "Assam"},
    },
    "assam_first_referral_units": {
        "ingestion_type": "public_healthcare_entities",
        "field_aliases": {
            "source_record_id": ("facility_code", "fru_code", "code", "id"),
            "name": ("facility_name", "fru_name", "name"),
            "category": ("facility_type", "category"),
            "district": ("district",),
            "address": ("address",),
            "public_phone": ("phone", "contact"),
        },
        "defaults": {"state": "Assam", "category": "health_centre"},
    },
    "assam_medical_colleges": {
        "ingestion_type": "public_healthcare_entities",
        "field_aliases": {
            "source_record_id": ("college_code", "institute_code", "code", "id"),
            "name": ("college_name", "institute_name", "name"),
            "category": ("category", "facility_type"),
            "address": ("address",),
            "city": ("city",),
            "district": ("district",),
            "public_phone": ("phone", "telephone", "contact"),
            "public_email": ("email",),
            "website": ("website", "website_url"),
        },
        "defaults": {"state": "Assam", "category": "hospital"},
    },
    "delhi_government_hospitals": {
        "ingestion_type": "public_healthcare_entities",
        "field_aliases": {
            "source_record_id": ("hospital_code", "code", "id"),
            "name": ("hospital_name", "name"),
            "category": ("category", "hospital_type"),
            "address": ("address", "hospital_address"),
            "city": ("city",),
            "district": ("district",),
            "state": ("state",),
            "postal_code": ("pincode", "pin_code", "postal_code"),
            "public_phone": ("phone", "telephone", "contact_number"),
            "public_email": ("email", "email_address"),
            "website": ("website", "website_url"),
        },
        "defaults": {"category": "hospital", "state": "Delhi"},
    },
    "delhi_registered_nursing_homes": {
        "ingestion_type": "public_healthcare_entities",
        "field_aliases": {
            "source_record_id": ("registration_no", "registration_number", "reg_no", "code"),
            "name": ("nursing_home_name", "facility_name", "name"),
            "category": ("category", "facility_type"),
            "address": ("address",),
            "city": ("city",),
            "district": ("district",),
            "state": ("state",),
            "postal_code": ("pincode", "pin_code"),
            "public_phone": ("phone", "contact", "telephone"),
        },
        "defaults": {"category": "nursing_home", "state": "Delhi"},
        "metadata_aliases": {
            "registration_status": ("registration_status", "status"),
            "valid_upto": ("valid_upto", "valid_until", "expiry_date"),
            "beds": ("beds", "bed_strength", "number_of_beds"),
        },
    },
    "lgd": {
        "ingestion_type": "geography_nodes",
        "field_aliases": {
            "source_record_id": ("lgd_code", "district_code", "local_body_code", "code"),
            "name": ("district_name", "local_body_name", "name"),
            "parent_source_record_id": ("parent_lgd_code", "state_code", "parent_code"),
            "node_type": ("node_type", "entity_type"),
        },
        "defaults": {},
    },
}


def list_connector_profiles() -> list[dict]:
    result = []
    for source_id, profile in CONNECTOR_PROFILES.items():
        item = profile.to_dict()
        source = get_public_ingestion_source(source_id) or {}
        item["official_url"] = source.get("official_url")
        item["trust_level"] = source.get("trust_level")
        item["configured"] = all(bool(os.getenv(key)) for key in profile.config_keys) if profile.config_keys else True
        item["missing_config"] = [key for key in profile.config_keys if not os.getenv(key)]
        result.append(item)
    return result


def connector_readiness(source_id: str) -> dict:
    key = str(source_id or "").strip().lower()
    profile = CONNECTOR_PROFILES.get(key)
    if not profile:
        raise LookupError(f"No connector profile exists for source '{source_id}'.")
    item = next(row for row in list_connector_profiles() if row["source_id"] == key)
    if profile.availability == "ONBOARDING_REQUIRED":
        item["ready_for_fetch"] = False
        item["reason"] = "Authorized onboarding/access is required before any live fetch."
    elif profile.config_keys and not item["configured"]:
        item["ready_for_fetch"] = False
        item["reason"] = "Connector configuration is incomplete."
    else:
        item["ready_for_fetch"] = True
        item["reason"] = "Source can be used through its documented configured/manual ingestion path."
    return item


def infer_mapping(source_id: str, rows: list[dict[str, Any]]) -> dict:
    """Build a deterministic source-column mapping from an explicit allowlist of aliases.

    This is deliberately conservative: no fuzzy guessing is performed.
    Missing required mappings remain an error at the normal adapter layer.
    """
    key = str(source_id or "").strip().lower()
    template = SOURCE_MAPPING_TEMPLATES.get(key)
    if not template:
        raise LookupError(f"No mapping template exists for source '{source_id}'.")
    if not isinstance(rows, list):
        raise ValueError("rows must be a list.")

    columns: set[str] = set()
    for row in rows[:50]:
        if isinstance(row, dict):
            columns.update(str(name).strip() for name in row.keys())
    lower_columns = {name.lower(): name for name in columns}

    mapping: dict[str, str] = {}
    for canonical, aliases in template["field_aliases"].items():
        for alias in aliases:
            if alias.lower() in lower_columns:
                mapping[canonical] = lower_columns[alias.lower()]
                break

    defaults = dict(template.get("defaults") or {})
    if key == "lgd" and "node_type" not in mapping and "node_type" not in defaults:
        # LGD resources are entity-specific; owner must state the node type
        # instead of ZENDOC guessing from a file name.
        pass

    metadata_aliases = template.get("metadata_aliases") or {}
    adapted_rows = []
    for raw in rows:
        if not isinstance(raw, dict):
            adapted_rows.append(raw)
            continue
        copy = dict(raw)
        metadata = {}
        for field, aliases in metadata_aliases.items():
            for alias in aliases:
                source_column = lower_columns.get(alias.lower())
                if source_column and raw.get(source_column) not in (None, ""):
                    metadata[field] = raw.get(source_column)
                    break
        if metadata:
            copy["__zendoc_metadata__"] = metadata
        adapted_rows.append(copy)

    if metadata_aliases:
        mapping["metadata"] = "__zendoc_metadata__"

    result = adapt_records(
        ingestion_type=template["ingestion_type"],
        rows=adapted_rows,
        mapping=mapping,
        defaults=defaults,
    )
    result["source_id"] = key
    result["mapping_template"] = {
        "mapping": mapping,
        "defaults": defaults,
        "deterministic_alias_match_only": True,
    }
    return result
