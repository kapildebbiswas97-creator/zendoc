#!/usr/bin/env python3
"""Run the bounded ZENDOC internal operations worker inside OCI."""
from __future__ import annotations

import os
import time

from zendoc import create_app
from zendoc.db import get_db
from zendoc.operations_digest import run_owner_operations_cycle


def _cycle_seconds() -> int:
    try:
        value = int(os.environ.get("ZENDOC_OPS_CYCLE_SECONDS", "3600"))
    except (TypeError, ValueError):
        value = 3600
    return max(300, min(value, 86400))


def _owner():
    configured = str(os.environ.get("ZENDOC_ADMIN_EMAIL") or "").strip().lower()
    if not configured:
        raise RuntimeError("ZENDOC_ADMIN_EMAIL is required for the operations worker.")
    row = get_db().execute(
        """
        SELECT * FROM users
        WHERE active=1 AND role='admin'
          AND LOWER(COALESCE(email_normalized,email))=?
        LIMIT 1
        """,
        (configured,),
    ).fetchone()
    if not row:
        raise RuntimeError("Configured ZENDOC owner account is not present in the database.")
    return row


def main() -> int:
    app = create_app()
    interval = _cycle_seconds()
    email_owner = str(os.environ.get("ZENDOC_OPS_DIGEST_EMAIL", "true")).strip().lower() in {
        "1", "true", "yes", "on"
    }

    while True:
        with app.app_context():
            try:
                result = run_owner_operations_cycle(_owner(), email_owner=email_owner)
                app.logger.info(
                    "Operations cycle completed: database=%s alerts=%s blockers=%s digest=%s",
                    result.get("database_status"),
                    result.get("active_alert_count"),
                    result.get("integration_blocker_count"),
                    result.get("digest_created"),
                )
            except Exception as exc:
                try:
                    get_db().rollback()
                except Exception:
                    pass
                # Keep operational logs free of potentially sensitive exception text.
                app.logger.exception(
                    "Operations cycle failed (%s).",
                    type(exc).__name__,
                )
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
