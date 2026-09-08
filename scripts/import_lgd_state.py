#!/usr/bin/env python3
"""Import LGD geography exports into ZENDOC for a supported target state.

Example:
  python scripts/import_lgd_state.py \
    --state west_bengal \
    --districts districts.csv \
    --subdistricts subdistricts.csv \
    --villages villages.csv \
    --villages-by-blocks villages_by_blocks.csv \
    --apply
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from zendoc import create_app
from zendoc.db import get_db
from zendoc.lgd_files import normalize_lgd_bundle, parse_delimited_text
from zendoc.state_geography_bootstrap import TARGET_STATES, bootstrap_state_geography


def read_dataset(path: str | None):
    if not path:
        return [], None
    file_path = Path(path)
    raw_bytes = file_path.read_bytes()
    text = raw_bytes.decode("utf-8-sig")
    rows = parse_delimited_text(text)
    manifest = {
        "path": str(file_path),
        "filename": file_path.name,
        "size_bytes": len(raw_bytes),
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "row_count": len(rows),
    }
    return rows, manifest


def build_import_report(*, state, mode: str, source_files: dict, bundle: dict, result: dict) -> dict:
    return {
        "report_version": "lgd_import_v2",
        "state": state.slug,
        "state_name": state.name,
        "lgd_state_code": state.lgd_state_code,
        "mode": mode,
        "source": "lgd",
        "source_authority": "Local Government Directory / Ministry of Panchayati Raj, Government of India",
        "source_files": {key: value for key, value in source_files.items() if value is not None},
        "normalized_counts": {key: len(value) for key, value in bundle.items()},
        "result": result,
        "truth_notice": (
            "This report describes only files supplied to this command. It does not claim complete "
            "state coverage unless the supplied official LGD exports themselves are complete."
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True, choices=sorted(TARGET_STATES))
    parser.add_argument("--districts")
    parser.add_argument("--subdistricts")
    parser.add_argument("--villages")
    parser.add_argument("--blocks")
    parser.add_argument("--panchayats")
    parser.add_argument("--urban-local-bodies")
    parser.add_argument("--villages-by-blocks")
    parser.add_argument("--ulb-coverage")
    parser.add_argument("--freshness-at")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report-json", help="Optional path for the structured import report.")
    args = parser.parse_args()

    state = TARGET_STATES[args.state]
    dataset_args = {
        "districts": args.districts,
        "subdistricts": args.subdistricts,
        "villages": args.villages,
        "blocks": args.blocks,
        "panchayats": args.panchayats,
        "urban_local_bodies": args.urban_local_bodies,
        "villages_by_blocks": args.villages_by_blocks,
        "ulb_coverage": args.ulb_coverage,
    }
    datasets = {}
    source_files = {}
    for key, file_path in dataset_args.items():
        rows, manifest = read_dataset(file_path)
        datasets[key] = rows
        source_files[key] = manifest

    bundle = normalize_lgd_bundle(
        state_code=state.lgd_state_code,
        districts=datasets["districts"],
        subdistricts=datasets["subdistricts"],
        villages=datasets["villages"],
        blocks=datasets["blocks"],
        panchayats=datasets["panchayats"],
        urban_local_bodies=datasets["urban_local_bodies"],
        villages_by_blocks=datasets["villages_by_blocks"],
        ulb_coverage=datasets["ulb_coverage"],
    )

    app = create_app()
    with app.app_context():
        owner_email = str(app.config.get("ADMIN_EMAIL") or "").strip().lower()
        row = get_db().execute(
            "SELECT * FROM users WHERE LOWER(COALESCE(email_normalized,email))=? AND role='admin' AND active=1 LIMIT 1",
            (owner_email,),
        ).fetchone()
        if not row:
            raise RuntimeError("Configured ZENDOC owner account was not found in the database.")
        actor = dict(row)
        result = bootstrap_state_geography(
            actor,
            state_slug=args.state,
            freshness_at=args.freshness_at,
            dry_run=not args.apply,
            **bundle,
        )
        report = build_import_report(
            state=state,
            mode="apply" if args.apply else "preview",
            source_files=source_files,
            bundle=bundle,
            result=result,
        )
        rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
        if args.report_json:
            report_path = Path(args.report_json)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)


if __name__ == "__main__":
    main()
