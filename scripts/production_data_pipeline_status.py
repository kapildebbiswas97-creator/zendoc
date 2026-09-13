"""Print a safe owner-only summary of ZENDOC's four production data tracks."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from zendoc import create_app
from zendoc.db import get_db
from zendoc.production_data_pipeline import production_data_pipeline_status


def main() -> int:
    app = create_app()
    with app.app_context():
        owner_email = str(app.config.get("ADMIN_EMAIL") or "").strip().lower()
        owner = get_db().execute(
            "SELECT * FROM users WHERE email_normalized=? AND role='admin' AND active=1",
            (owner_email,),
        ).fetchone()
        if owner is None:
            print("Pipeline status unavailable: configured owner account is not active.", file=sys.stderr)
            return 2
        report = production_data_pipeline_status(owner)

    print(json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
