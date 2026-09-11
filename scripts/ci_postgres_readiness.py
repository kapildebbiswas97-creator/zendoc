"""CI production-readiness smoke test against a real PostgreSQL service."""
from __future__ import annotations

import os
import csv
import io
import json
import sys
import tempfile
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


def check_snapshot_round_trip(app) -> None:
    """Exercise actual import writes on the disposable GitHub PostgreSQL DB."""
    from zendoc.data_acquisition import acquire_source_bytes
    from zendoc.dataset_snapshot_ingestion import ingest_public_snapshot

    if os.environ.get("ZENDOC_CI_FIXTURES") != "true":
        fail("Snapshot smoke requires ZENDOC_CI_FIXTURES=true on a disposable test database.")
    db = get_db()
    actor = db.execute(
        "SELECT * FROM users WHERE email_normalized=? AND role='admin'",
        (app.config["ADMIN_EMAIL"].lower(),),
    ).fetchone()
    if not actor:
        fail("Configured CI owner account is missing.")
    # Synthetic fixture only: no source facts or real provider counts claimed.
    payload = (
        b"source_record_id,category,name,district,state\n"
        b"CI-SNAPSHOT-001,hospital,Synthetic CI Hospital,Nadia,West Bengal\n"
    )
    with tempfile.TemporaryDirectory(prefix="zendoc-ci-snapshot-") as raw_root:
        acquired = acquire_source_bytes(
            "data_gov_hospitals", "https://example.invalid/ci-snapshot.csv", payload,
            storage_root=raw_root, usage_basis="manual_public_snapshot",
            license_or_terms="Synthetic CI fixture; not official or real provider data.",
            dataset_version="ci-v1", retrieved_at="2026-09-11T00:00:00+00:00",
            file_name="ci-snapshot.csv",
        )
        records = list(csv.DictReader(io.StringIO(payload.decode("utf-8"))))
        args = dict(
            source_id="data_gov_hospitals", ingestion_type="public_healthcare_entities",
            records=records, dataset_snapshot=acquired["dataset_snapshot"],
        )
        preview = ingest_public_snapshot(actor, **args, dry_run=True)
        applied = ingest_public_snapshot(
            actor, **args, dry_run=False, preview_batch_uid=preview["batch_uid"],
        )
        if applied["accepted_count"] != 1 or applied["rejected_count"] != 0:
            fail("Snapshot smoke did not apply exactly one fixture.")
        row = db.execute(
            "SELECT * FROM public_healthcare_entities WHERE source_id=? AND source_record_id=?",
            ("data_gov_hospitals", "CI-SNAPSHOT-001"),
        ).fetchone()
        metadata = json.loads(row["metadata_json"])
        if metadata["_zendoc_source_snapshot"]["snapshot_uid"] != acquired["snapshot_uid"]:
            fail("Acquisition identity changed during PostgreSQL import.")
        if row["zendoc_verification_status"] != "not_verified" or row["booking_connectivity"] != "not_connected":
            fail("Public import incorrectly promoted verification or connectivity.")
        replay = ingest_public_snapshot(
            actor, **args, dry_run=False, preview_batch_uid=preview["batch_uid"],
        )
        if not replay["duplicate_batch"]:
            fail("Snapshot replay was not idempotent.")


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

        if os.environ.get("ZENDOC_CI_FIXTURES") == "true":
            check_snapshot_round_trip(app)

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

