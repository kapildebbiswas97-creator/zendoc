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
from pathlib import Path

from zendoc import create_app
from zendoc.db import get_db
from zendoc.lgd_files import normalize_lgd_bundle, parse_delimited_text
from zendoc.state_geography_bootstrap import TARGET_STATES, bootstrap_state_geography


def read_rows(path: str | None):
    if not path:
        return []
    text = Path(path).read_text(encoding="utf-8-sig")
    return parse_delimited_text(text)


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
    args = parser.parse_args()

    state = TARGET_STATES[args.state]
    bundle = normalize_lgd_bundle(
        state_code=state.lgd_state_code,
        districts=read_rows(args.districts),
        subdistricts=read_rows(args.subdistricts),
        villages=read_rows(args.villages),
        blocks=read_rows(args.blocks),
        panchayats=read_rows(args.panchayats),
        urban_local_bodies=read_rows(args.urban_local_bodies),
        villages_by_blocks=read_rows(args.villages_by_blocks),
        ulb_coverage=read_rows(args.ulb_coverage),
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
        print(result)


if __name__ == "__main__":
    main()
