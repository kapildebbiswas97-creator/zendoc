"""Validate and import a normalized official/public healthcare artifact.

Input must be a UTF-8 JSON array of normalized facility records. Dry-run is the
default. Passing --apply is an explicit production mutation and still preserves
the source trust level; it never marks imported facilities ZENDOC_VERIFIED.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from zendoc import create_app
from zendoc.db import get_db
from zendoc.public_data_ingestion import ingest_public_records


def _load_records(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("Artifact must contain a JSON array.")
    if len(payload) > 5000:
        raise ValueError("Artifact has more than 5000 rows; split it into bounded batches.")
    if not all(isinstance(row, dict) for row in payload):
        raise ValueError("Every artifact row must be a JSON object.")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Import one normalized official healthcare artifact.")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--apply", action="store_true", help="Persist validated rows. Default is dry-run only.")
    args = parser.parse_args()

    try:
        records = _load_records(Path(args.input))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"Artifact validation failed: {exc}", file=sys.stderr)
        return 2

    app = create_app()
    with app.app_context():
        owner_email = str(app.config.get("ADMIN_EMAIL") or "").strip().lower()
        owner = get_db().execute(
            "SELECT * FROM users WHERE email_normalized=? AND role='admin' AND active=1",
            (owner_email,),
        ).fetchone()
        if owner is None:
            print("Import blocked: configured owner account is not present and active.", file=sys.stderr)
            return 3
        try:
            result = ingest_public_records(
                owner,
                source_id=args.source_id,
                ingestion_type="public_healthcare_entities",
                records=records,
                dry_run=not args.apply,
            )
        except (LookupError, PermissionError, ValueError) as exc:
            print(f"Import blocked: {exc}", file=sys.stderr)
            return 4

    safe = {
        "source_id": result.get("source_id"),
        "ingestion_type": result.get("ingestion_type"),
        "dry_run": result.get("dry_run"),
        "status": result.get("status"),
        "record_count": result.get("record_count"),
        "accepted_count": result.get("accepted_count"),
        "rejected_count": result.get("rejected_count"),
        "duplicate": result.get("duplicate", False),
        "batch_id": result.get("id"),
    }
    print(json.dumps(safe, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
