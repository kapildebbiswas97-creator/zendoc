"""Report West Bengal/India public-data acquisition completeness from a local workspace."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _iter_sources(catalog: dict):
    seen = set()
    wb = catalog.get("west_bengal") or {}
    india = catalog.get("india") or {}
    for item in wb.get("sources") or []:
        key = item.get("source_id")
        if key and key not in seen:
            seen.add(key)
            yield item, "WEST_BENGAL"
    for item in india.get("sources") or []:
        key = item.get("source_id")
        if key and key not in seen:
            seen.add(key)
            yield item, "INDIA_BASELINE"
    for state_slug, items in (india.get("state_enrichment_sources") or {}).items():
        for item in items:
            key = item.get("source_id")
            if key and key not in seen:
                seen.add(key)
                yield item, f"STATE_ENRICHMENT:{state_slug}"
    for item in india.get("authorized_only_sources") or []:
        key = item.get("source_id")
        if key and key not in seen:
            seen.add(key)
            yield item, "AUTHORIZED_ONLY"


def _raw_snapshot_count(raw_root: Path, source_id: str) -> int:
    source_root = raw_root / source_id
    if not source_root.is_dir():
        return 0
    count = 0
    for digest_dir in source_root.iterdir():
        if not digest_dir.is_dir():
            continue
        if any(path.is_file() for path in digest_dir.iterdir()):
            count += 1
    return count


def workspace_status(storage_root: str | Path) -> dict:
    root = Path(storage_root).expanduser().resolve()
    catalog_path = root / "manifests" / "source_catalog.json"
    if not catalog_path.is_file():
        raise ValueError("source_catalog.json not found; run bootstrap_public_data_workspace.py first.")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    raw_root = root / "raw"
    rows = []
    for source, layer in _iter_sources(catalog):
        source_id = source["source_id"]
        snapshots = _raw_snapshot_count(raw_root, source_id)
        if snapshots:
            status = "ACQUIRED"
        elif source.get("acquisition_mode") == "AUTHORIZED_ONLY":
            status = "AUTHORIZED_BLOCKED"
        elif not source.get("ingestion_registered", True):
            status = "CATALOG_ONLY"
        elif source.get("acquisition_mode") == "PUBLIC_LOOKUP_SNAPSHOT":
            status = "MANUAL_SNAPSHOT_REQUIRED"
        else:
            status = "MISSING"
        rows.append({
            "source_id": source_id,
            "name": source.get("name"),
            "layer": layer,
            "acquisition_mode": source.get("acquisition_mode"),
            "ingestion_status": source.get("ingestion_status", "REGISTERED"),
            "snapshot_count": snapshots,
            "status": status,
            "official_url": source.get("official_url"),
        })

    counts = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {
        "status": "OK",
        "source_count": len(rows),
        "counts": counts,
        "sources": rows,
        "truth_notice": "ACQUIRED means at least one immutable raw snapshot exists locally; it does not by itself mean current, complete, mapped or production-approved.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Show local West Bengal + India public-data acquisition status.")
    parser.add_argument("--storage-root", required=True)
    args = parser.parse_args()
    try:
        result = workspace_status(args.storage_root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "ERROR", "message": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
