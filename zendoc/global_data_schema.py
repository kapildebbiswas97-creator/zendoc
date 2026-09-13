"""Additive country/currency schema for global ZENDOC data coverage."""
from __future__ import annotations

from flask import current_app

from .db import get_db, now_iso
from .global_source_registry import GLOBAL_SOURCES

MIGRATION_VERSION = "global_country_currency_v1"


def ensure_global_data_schema() -> None:
    db = get_db()
    additions = {
        "public_healthcare_entities": {
            "country_code": "TEXT",
            "country_name": "TEXT",
        },
        "provider_profiles": {
            "country_code": "TEXT",
            "country_name": "TEXT",
        },
        "medication_skus": {
            "country_code": "TEXT",
            "currency_code": "TEXT NOT NULL DEFAULT 'INR'",
        },
        "inventory_observations": {
            "currency_code": "TEXT NOT NULL DEFAULT 'INR'",
        },
        "fulfilment_plans": {
            "currency_code": "TEXT NOT NULL DEFAULT 'INR'",
        },
        "medicine_orders": {
            "currency_code": "TEXT NOT NULL DEFAULT 'INR'",
        },
    }
    for table, columns in additions.items():
        existing = _columns(db, table)
        for column, ddl in columns.items():
            if column not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    # Existing deployments were India-first, but never relabel a known
    # international source as India merely because an older code path omitted
    # the new country columns.
    global_ids = sorted(GLOBAL_SOURCES)
    placeholders = ",".join("?" for _ in global_ids)
    if global_ids:
        db.execute(
            f"UPDATE public_healthcare_entities SET country_code='IN',country_name='India' "
            f"WHERE (country_code IS NULL OR country_code='') AND source_id NOT IN ({placeholders})",
            tuple(global_ids),
        )
    else:
        db.execute(
            "UPDATE public_healthcare_entities SET country_code='IN',country_name='India' "
            "WHERE country_code IS NULL OR country_code=''"
        )

    db.execute(
        "UPDATE provider_profiles SET country_code='IN',country_name='India' "
        "WHERE country_code IS NULL OR country_code=''"
    )
    db.execute(
        "UPDATE medication_skus SET country_code='IN' WHERE country_code IS NULL OR country_code=''"
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_public_healthcare_country ON public_healthcare_entities(country_code,state,city)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_provider_profiles_country ON provider_profiles(country_code,state,city)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_medication_skus_country ON medication_skus(country_code,name)")
    db.execute(
        "INSERT OR IGNORE INTO schema_migrations (version,applied_at) VALUES (?,?)",
        (MIGRATION_VERSION, now_iso()),
    )
    db.commit()


def _columns(db, table: str) -> set[str]:
    engine = str(current_app.config.get("DATABASE_ENGINE") or "sqlite").lower()
    if engine == "postgresql":
        rows = db.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=?",
            (table,),
        ).fetchall()
        return {str(row["column_name"]) for row in rows}
    rows = db.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}
