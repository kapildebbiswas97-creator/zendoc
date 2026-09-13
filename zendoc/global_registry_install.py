"""Install international public sources into the existing ingestion registry."""
from __future__ import annotations

from .global_source_registry import GLOBAL_SOURCES
from .public_source_registry import PublicIngestionSource, SOURCES


def install_global_public_sources() -> None:
    for source_id, source in GLOBAL_SOURCES.items():
        if source_id in SOURCES:
            continue
        SOURCES[source_id] = PublicIngestionSource(
            source_id=source["source_id"],
            name=source["name"],
            owner=source["owner"],
            official_url=source["official_url"],
            data_class=source["data_class"],
            geography=source["geography"],
            ingestion_types=tuple(source.get("ingestion_types") or ()),
            trust_level=source["trust_level"],
            live_fetch_status=source["live_fetch_status"],
            personal_data_allowed=bool(source.get("personal_data_allowed", False)),
            notes=source["notes"],
        )
