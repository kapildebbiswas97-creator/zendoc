"""CI production-readiness smoke test against a real PostgreSQL service."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from zendoc import create_app
from zendoc.database_reliability import REQUIRED_MIGRATIONS, REQUIRED_TABLES, readiness_report
from zendoc.db import get_db


def fail(message: str) -> None:
    print(f"CI PostgreSQL readiness FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        fail("DATABASE_URL is not PostgreSQL.")

    app = create_app()
    if app.config.get("DATABASE_ENGINE") != "postgresql":
        fail(f"Expected postgresql engine, got {app.config.get('DATABASE_ENGINE')!r}.")
    if app.config.get("ZENDOC_ENV") != "production":
        fail("Smoke test must run with ZENDOC_ENV=production.")
    if not app.config.get("PERSISTENCE_VERIFIED"):
        fail("PERSISTENCE_VERIFIED must be true in this production smoke test.")

    with app.app_context():
        report = readiness_report()
        if report.get("status") != "ready":
            fail(f"Initial readiness failed: {report}")
        if report.get("database_engine") != "postgresql":
            fail(f"Readiness reported wrong engine: {report.get('database_engine')}")

        db = get_db()
        migrations = {
            str(row["version"])
            for row in db.execute("SELECT version FROM schema_migrations").fetchall()
        }
        missing_migrations = sorted(set(REQUIRED_MIGRATIONS) - migrations)
        if missing_migrations:
            fail(f"Required migrations missing: {missing_migrations}")

        rows = db.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema=current_schema()
            """
        ).fetchall()
        tables = {str(row["table_name"]) for row in rows}
        missing_tables = sorted(set(REQUIRED_TABLES) - tables)
        if missing_tables:
            fail(f"Required tables missing: {missing_tables}")

        marker = "ci-production-restart-marker"
        db.execute(
            """
            INSERT INTO integration_health_checks
            (integration_key,status,detail,checked_at)
            VALUES ('ci_postgres','HEALTHY',?,CURRENT_TIMESTAMP)
            """,
            (marker,),
        )
        db.commit()

    app2 = create_app()
    with app2.app_context():
        report2 = readiness_report()
        if report2.get("status") != "ready":
            fail(f"Readiness after reconnect failed: {report2}")
        marker_row = get_db().execute(
            """
            SELECT detail FROM integration_health_checks
            WHERE integration_key='ci_postgres'
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        if not marker_row or marker_row["detail"] != marker:
            fail("Persistence marker was not readable after reconnect.")

    print("CI PostgreSQL production readiness PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
