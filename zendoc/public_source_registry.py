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
}


def get_public_ingestion_source(source_id: str) -> dict | None:
    source = SOURCES.get(str(source_id or "").strip().lower())
    return source.to_dict() if source else None


def list_public_ingestion_sources() -> list[dict]:
    return [source.to_dict() for source in SOURCES.values()]
