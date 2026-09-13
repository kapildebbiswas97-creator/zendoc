from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from zendoc import create_app
from zendoc.db import get_db
from zendoc.global_public_data import ingest_global_public_healthcare


def main() -> int:
    parser = argparse.ArgumentParser(description="Import normalized official healthcare rows for a configured country source.")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    path = Path(args.input)
    if not path.is_file():
        print("Input artifact was not found.", file=sys.stderr)
        return 2
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("Input artifact must be a readable UTF-8 JSON array.", file=sys.stderr)
        return 2
    if not isinstance(records, list):
        print("Input artifact must contain a JSON array.", file=sys.stderr)
        return 2

    config = {}
    if os.getenv("DATABASE_URL"):
        config["DATABASE_URL"] = os.environ["DATABASE_URL"]
        config["DATABASE_ENGINE"] = "postgresql"
    app = create_app(config or None)
    with app.app_context():
        owner_email = str(app.config.get("ADMIN_EMAIL") or "").strip().lower()
        owner = get_db().execute(
            "SELECT * FROM users WHERE email_normalized=? AND role='admin' AND active=1",
            (owner_email,),
        ).fetchone()
        if not owner:
            print("Configured owner account was not found.", file=sys.stderr)
            return 2
        result = ingest_global_public_healthcare(
            owner,
            source_id=args.source_id,
            records=records,
            dry_run=not args.apply,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
