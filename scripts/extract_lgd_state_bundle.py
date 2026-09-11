#!/usr/bin/env python3
"""Extract one State/UT bundle from national LGD CSV files by official State Code.

West Bengal example:
  python scripts/extract_lgd_state_bundle.py \
    --state-code 19 --output-dir D:\\ZENDOC_DATA\\curated\\lgd\\west_bengal \
    --districts D:\\ZENDOC_DATA\\raw_input\\districts.csv \
    --subdistricts D:\\ZENDOC_DATA\\raw_input\\subdistricts.csv \
    --villages D:\\ZENDOC_DATA\\raw_input\\villages.csv
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

from zendoc.lgd_state_extract import extract_state_csv


DATASET_ARGS = (
    "districts",
    "subdistricts",
    "villages",
    "blocks",
    "panchayats",
    "urban_local_bodies",
    "villages_by_blocks",
    "ulb_coverage",
)


def extract_bundle(*, state_code: str, output_dir: str | Path, datasets: dict[str, str | None]) -> dict:
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    results = {}
    for label in DATASET_ARGS:
        source_path = datasets.get(label)
        if not source_path:
            continue
        suffix = Path(source_path).suffix.lower() or ".csv"
        target = root / f"{label}{suffix}"
        results[label] = extract_state_csv(source_path, target, state_code=state_code)

    if not results:
        raise ValueError("At least one LGD dataset file is required.")

    manifest = {
        "manifest_version": "lgd_state_extract_v1",
        "state_code": str(state_code),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "datasets": results,
        "truth_notice": (
            "This bundle contains only rows whose official LGD State Code matched the requested state. "
            "Completeness depends on the supplied national LGD artifacts."
        ),
    }
    manifest_path = root / "extract_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Stream-filter national LGD CSVs into one State/UT bundle.")
    parser.add_argument("--state-code", required=True, help="Official LGD State/UT code, e.g. West Bengal=19")
    parser.add_argument("--output-dir", required=True)
    for label in DATASET_ARGS:
        parser.add_argument("--" + label.replace("_", "-"), dest=label)
    args = parser.parse_args()
    try:
        manifest = extract_bundle(
            state_code=args.state_code,
            output_dir=args.output_dir,
            datasets={label: getattr(args, label) for label in DATASET_ARGS},
        )
    except (OSError, ValueError) as exc:
        print(f"LGD state extraction failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
