"""Create a local ZENDOC public-data workspace and source catalogs.

Example (Windows):
    python scripts/bootstrap_public_data_workspace.py --storage-root D:\\ZENDOC_DATA

The command writes metadata/catalog files only. It does not copy private data
or silently scrape websites.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from zendoc.public_data_bundle import bundle_catalog


WORKSPACE_DIRS = ("raw", "incoming", "manifests", "curated", "samples", "rejected", "logs")


def bootstrap(storage_root: str | Path) -> dict:
    root = Path(storage_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    for name in WORKSPACE_DIRS:
        (root / name).mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    catalog = bundle_catalog()
    catalog["generated_at"] = generated_at
    catalog["workspace_layout"] = list(WORKSPACE_DIRS)

    catalog_path = root / "manifests" / "source_catalog.json"
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    readme = """# ZENDOC public-data workspace

This folder is intentionally outside normal Git history.

- `incoming/` — exact files downloaded/exported from an approved public source before acquisition.
- `raw/` — immutable, content-addressed acquired snapshots (`source/sha256/file`).
- `manifests/` — provenance/source catalogs and snapshot manifests.
- `curated/` — normalized outputs generated from accepted raw snapshots.
- `samples/` — small non-sensitive development samples only.
- `rejected/` — artifacts that failed schema/quality/source validation.
- `logs/` — acquisition/import summaries without private row content.

West Bengal is a FULL-STATE acquisition target. Nadia is only a regression/quality-validation district.
All-India public/official sources are catalogued in parallel. Authorized registries (for example ABDM HFR/HPR systematic access) stay blocked until legitimate onboarding/access exists.

Never place API keys, patient records, claims, prescriptions, private provider operational data, or other sensitive information in this public-data workspace or Git.
"""
    (root / "README.md").write_text(readme, encoding="utf-8")

    return {
        "status": "READY",
        "storage_root": str(root),
        "catalog_path": str(catalog_path),
        "directories": list(WORKSPACE_DIRS),
        "generated_at": generated_at,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the ZENDOC West Bengal + India public-data workspace.")
    parser.add_argument("--storage-root", required=True, help="Local drive/folder for raw data, e.g. D:\\ZENDOC_DATA")
    args = parser.parse_args()
    try:
        result = bootstrap(args.storage_root)
    except (OSError, ValueError):
        print("Workspace bootstrap failed safely.", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
