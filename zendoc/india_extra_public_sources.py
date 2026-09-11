"""Additional India-wide official source metadata under acquisition validation."""
from __future__ import annotations


INDIA_EXTRA_SOURCES = {
    "data_gov_health_centres": {
        "source_id": "data_gov_health_centres",
        "name": "All India Health Centres Directory",
        "owner": "Ministry of Health and Family Welfare / Open Government Data Platform India",
        "official_url": "https://www.data.gov.in/catalog/all-india-health-centres-directory",
        "data_class": "official_historical_public_health_facility_directory",
        "geography": "INDIA",
        "ingestion_types": ["public_healthcare_entities"],
        "trust_level": "OFFICIAL_PUBLIC_DATA_HISTORICAL",
        "live_fetch_status": "PUBLIC_CATALOG_ZIP_DOWNLOAD_HISTORICAL_SNAPSHOT",
        "personal_data_allowed": False,
        "notes": (
            "Published directory covers Sub-Centres, PHCs, CHCs, district/state hospitals and geolocation, but the OGD catalog is historical. "
            "Use only as dated reference/enrichment and never as proof that a facility is currently operating or offering a service."
        ),
    },
}


def get_india_extra_source(source_id: str) -> dict | None:
    item = INDIA_EXTRA_SOURCES.get(str(source_id or "").strip().lower())
    return dict(item) if item else None
