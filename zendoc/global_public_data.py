from __future__ import annotations

from typing import Any

from .db import get_db
from .global_source_registry import get_global_public_ingestion_source
from .public_data_ingestion import ingest_public_records
from .security import assert_owner


def ingest_global_public_healthcare(actor: Any, *, source_id: str, records: list[dict], dry_run: bool = True) -> dict:
    assert_owner(actor)
    source = get_global_public_ingestion_source(source_id)
    if not source:
        raise LookupError(f"Unknown global public source '{source_id}'.")
    if "public_healthcare_entities" not in (source.get("ingestion_types") or []):
        raise ValueError("This source is reference-only and cannot be bulk-ingested.")

    prepared = []
    for raw in records:
        row = dict(raw or {})
        metadata = dict(row.get("metadata") or {}) if isinstance(row.get("metadata"), dict) else {}
        metadata.update({
            "country_code": source["country_code"],
            "country_name": source["country_name"],
            "source_jurisdiction": source.get("geography"),
        })
        row["metadata"] = metadata
        prepared.append(row)

    result = ingest_public_records(
        actor,
        source_id=source_id,
        ingestion_type="public_healthcare_entities",
        records=prepared,
        dry_run=dry_run,
    )
    if not dry_run:
        db = get_db()
        db.execute(
            "UPDATE public_healthcare_entities SET country_code=?,country_name=? WHERE source_id=?",
            (source["country_code"], source["country_name"], source_id),
        )
        db.commit()
    result["country_code"] = source["country_code"]
    result["country_name"] = source["country_name"]
    return result
