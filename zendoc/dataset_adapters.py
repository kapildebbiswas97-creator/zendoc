"""Explicit dataset-to-ZENDOC canonical mapping for public ingestion.

Government/open-data column names change across datasets and versions. ZENDOC
therefore does not silently guess schemas. The owner supplies a mapping from
canonical fields to source columns (plus optional defaults), previews the
result, then sends canonical records through the normal dry-run/apply engine.
"""
from __future__ import annotations

import csv
import io
from typing import Any


CANONICAL_FIELDS = {
    "geography_nodes": {
        "required": {"source_record_id", "node_type", "name"},
        "optional": {
            "parent_source_record_id", "latitude", "longitude",
            "freshness_at", "verified",
        },
    },
    "public_healthcare_entities": {
        "required": {"source_record_id", "category", "name"},
        "optional": {
            "specialty", "address", "city", "district", "state", "postal_code",
            "latitude", "longitude", "public_phone", "public_email", "website",
            "freshness_at", "metadata",
        },
    },
}


def parse_csv_text(csv_text: str, *, max_rows: int = 5000) -> list[dict[str, str]]:
    text = str(csv_text or "")
    if not text.strip():
        raise ValueError("csv_text is required.")
    if len(text.encode("utf-8")) > 5_000_000:
        raise ValueError("CSV preview is limited to 5 MB.")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV header row is required.")
    rows = []
    for index, row in enumerate(reader, start=1):
        if index > max_rows:
            raise ValueError(f"CSV preview is limited to {max_rows} data rows.")
        rows.append({str(k or "").strip(): v for k, v in row.items()})
    return rows


def adapt_records(
    *,
    ingestion_type: str,
    rows: list[dict[str, Any]],
    mapping: dict[str, str] | None = None,
    defaults: dict[str, Any] | None = None,
) -> dict:
    schema = CANONICAL_FIELDS.get(str(ingestion_type or "").strip())
    if not schema:
        raise ValueError("Unsupported ingestion_type for dataset adaptation.")
    if not isinstance(rows, list):
        raise ValueError("rows must be a list.")
    if len(rows) > 5000:
        raise ValueError("A mapping preview may contain at most 5000 rows.")

    mapping = {str(k): str(v) for k, v in (mapping or {}).items() if str(k).strip() and str(v).strip()}
    defaults = dict(defaults or {})
    allowed = schema["required"] | schema["optional"]
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        raise ValueError(f"Unknown canonical mapping field(s): {', '.join(unknown)}")

    missing_mapping = sorted(
        field for field in schema["required"]
        if field not in mapping and field not in defaults
    )
    if missing_mapping:
        raise ValueError(
            "Required canonical fields need a source-column mapping or default: "
            + ", ".join(missing_mapping)
        )

    canonical = []
    rejected = []
    for row_number, raw in enumerate(rows, start=1):
        if not isinstance(raw, dict):
            rejected.append({"row_number": row_number, "reason": "row is not an object"})
            continue
        item = {}
        for field in allowed:
            if field in mapping:
                source_column = mapping[field]
                item[field] = raw.get(source_column)
            elif field in defaults:
                item[field] = defaults[field]

        missing_values = [
            field for field in schema["required"]
            if str(item.get(field) or "").strip() == ""
        ]
        if missing_values:
            rejected.append({
                "row_number": row_number,
                "reason": "missing canonical value(s): " + ", ".join(sorted(missing_values)),
            })
            continue

        if "metadata" in item and not isinstance(item["metadata"], dict):
            item["metadata"] = {"source_metadata": item["metadata"]}
        canonical.append(item)

    return {
        "ingestion_type": ingestion_type,
        "mapping": mapping,
        "defaults": defaults,
        "source_row_count": len(rows),
        "canonical_record_count": len(canonical),
        "rejected_count": len(rejected),
        "records": canonical,
        "rejected": rejected[:100],
        "truth_notice": (
            "Schema adaptation only normalizes columns. It does not verify the factual accuracy, freshness, "
            "licensing, availability, or ZENDOC connectivity of any source record."
        ),
    }
