"""Data-driven geography import-region registry.

India state/UT codes are imported from official LGD state snapshots rather than
hard-coded beyond the currently validated priority states.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .db import get_db, now_iso


def slugify_region(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())
    return text.strip("_")


def upsert_import_region(
    *,
    country_code: str,
    region_level: str,
    region_code: str,
    name: str,
    source: str,
    aliases: list[str] | tuple[str, ...] | None = None,
    source_ref: str | None = None,
    slug: str | None = None,
) -> dict:
    country_code = str(country_code or "").strip().upper()
    region_level = str(region_level or "").strip().lower()
    region_code = str(region_code or "").strip()
    name = str(name or "").strip()
    source = str(source or "").strip()
    slug = slugify_region(slug or name)
    if not all((country_code, region_level, region_code, name, source, slug)):
        raise ValueError("country_code, region_level, region_code, name and source are required.")

    alias_values = sorted({
        str(item).strip().lower()
        for item in (aliases or [])
        if str(item).strip()
    })
    now = now_iso()
    db = get_db()
    existing = db.execute(
        """
        SELECT id FROM geography_import_regions
        WHERE country_code=? AND region_level=? AND region_code=?
        """,
        (country_code, region_level, region_code),
    ).fetchone()
    if existing:
        db.execute(
            """
            UPDATE geography_import_regions
            SET slug=?, name=?, aliases_json=?, source=?, source_ref=?, active=1, updated_at=?
            WHERE id=?
            """,
            (
                slug, name, json.dumps(alias_values, ensure_ascii=False),
                source, source_ref, now, existing["id"],
            ),
        )
        region_id = existing["id"]
    else:
        cursor = db.execute(
            """
            INSERT INTO geography_import_regions
            (country_code,region_level,region_code,slug,name,aliases_json,source,source_ref,active,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,1,?,?)
            """,
            (
                country_code, region_level, region_code, slug, name,
                json.dumps(alias_values, ensure_ascii=False), source, source_ref, now, now,
            ),
        )
        region_id = cursor.lastrowid
    db.commit()
    return get_import_region(region_id)


def get_import_region(region_id: int) -> dict:
    row = get_db().execute(
        "SELECT * FROM geography_import_regions WHERE id=?",
        (int(region_id),),
    ).fetchone()
    if not row:
        raise LookupError(f"Import region #{region_id} not found.")
    return _row(row)


def find_import_region(
    *,
    country_code: str,
    region_level: str,
    slug_or_code: str,
) -> dict | None:
    country_code = str(country_code or "").strip().upper()
    region_level = str(region_level or "").strip().lower()
    value = str(slug_or_code or "").strip()
    slug = slugify_region(value)
    row = get_db().execute(
        """
        SELECT * FROM geography_import_regions
        WHERE country_code=? AND region_level=? AND active=1
          AND (region_code=? OR slug=?)
        LIMIT 1
        """,
        (country_code, region_level, value, slug),
    ).fetchone()
    if row:
        return _row(row)

    rows = get_db().execute(
        """
        SELECT * FROM geography_import_regions
        WHERE country_code=? AND region_level=? AND active=1
        """,
        (country_code, region_level),
    ).fetchall()
    lowered = value.lower()
    for candidate in rows:
        item = _row(candidate)
        if lowered == item["name"].lower() or lowered in item["aliases"]:
            return item
    return None


def list_import_regions(*, country_code: str = "IN", region_level: str = "state") -> list[dict]:
    rows = get_db().execute(
        """
        SELECT * FROM geography_import_regions
        WHERE country_code=? AND region_level=? AND active=1
        ORDER BY name
        """,
        (str(country_code).upper(), str(region_level).lower()),
    ).fetchall()
    return [_row(row) for row in rows]


def import_lgd_state_registry(rows: list[dict[str, Any]], *, source: str = "lgd") -> dict:
    """Import official LGD State/UT rows using conservative known header aliases."""
    if not isinstance(rows, list):
        raise ValueError("rows must be a list.")

    accepted = []
    rejected = []
    for index, raw in enumerate(rows, start=1):
        if not isinstance(raw, dict):
            rejected.append({"row_number": index, "reason": "row is not an object"})
            continue
        normalized = {_key(key): value for key, value in raw.items()}
        code = _first(normalized, "state code", "statecode")
        name = _first(
            normalized,
            "state name in english",
            "state name",
            "state ut name",
            "state union territory name",
        )
        if not code or not name:
            rejected.append({"row_number": index, "reason": "state code/name missing"})
            continue

        item = upsert_import_region(
            country_code="IN",
            region_level="state",
            region_code=code,
            name=name,
            source=source,
            source_ref=f"state:{code}",
            aliases=[],
        )
        accepted.append(item)

    return {
        "status": "IMPORTED",
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "rejected": rejected[:200],
        "regions": accepted,
    }


def seed_priority_india_states() -> None:
    """Seed only the state codes already validated in current ZENDOC tests."""
    for code, name, aliases in (
        ("19", "West Bengal", ["west bengal", "wb"]),
        ("18", "Assam", ["assam"]),
        ("9", "Uttar Pradesh", ["uttar pradesh", "up"]),
    ):
        upsert_import_region(
            country_code="IN",
            region_level="state",
            region_code=code,
            name=name,
            source="lgd_validated_seed",
            source_ref=f"state:{code}",
            aliases=aliases,
        )


def _row(row) -> dict:
    item = dict(row)
    try:
        item["aliases"] = json.loads(item.pop("aliases_json") or "[]")
    except json.JSONDecodeError:
        item["aliases"] = []
    return item


def _key(value: Any) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split())


def _first(row: dict[str, Any], *aliases: str) -> str:
    for alias in aliases:
        value = row.get(_key(alias))
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""
