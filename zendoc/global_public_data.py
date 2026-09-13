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
    country_code = str(source["country_code"]).upper()
    for raw in records:
        row = dict(raw or {})
        metadata = dict(row.get("metadata") or {}) if isinstance(row.get("metadata"), dict) else {}
        metadata.update({
            "country_code": country_code,
            "country_name": source["country_name"],
            "source_jurisdiction": source.get("geography"),
        })
        row["metadata"] = metadata

        # Never resolve an international row against India's LGD hierarchy by
        # name. A country-specific geography import may later populate these
        # source namespaces and create exact links; until then the row remains
        # explicitly unresolved rather than falsely linked to an Indian place.
        if country_code != "IN" and not str(row.get("geography_source") or "").strip():
            row["geography_source"] = f"global_{country_code.lower()}"
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
            (country_code, source["country_name"], source_id),
        )
        db.commit()
    result["country_code"] = country_code
    result["country_name"] = source["country_name"]
    return result
