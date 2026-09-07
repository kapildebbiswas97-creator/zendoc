"""State-scale LGD geography bootstrap for ZENDOC.

Targets:
- West Bengal
- Assam
- Uttar Pradesh

The service ingests official LGD-style state snapshots in dependency order and
keeps administrative hierarchy separate from block/panchayat/local-body
relationships. It never fabricates missing villages or parent relationships.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from flask import has_app_context

from .db import get_db, now_iso
from .geography_graph import link_geography_nodes, upsert_geography_node
from .geography_region_registry import find_import_region, list_import_regions
from .security import assert_owner


@dataclass(frozen=True)
class TargetState:
    slug: str
    name: str
    aliases: tuple[str, ...]
    lgd_state_code: str

    def to_dict(self) -> dict:
        data = asdict(self)
        data["aliases"] = list(self.aliases)
        return data


TARGET_STATES = {
    "west_bengal": TargetState("west_bengal", "West Bengal", ("west bengal", "wb"), "19"),
    "assam": TargetState("assam", "Assam", ("assam",), "18"),
    "uttar_pradesh": TargetState("uttar_pradesh", "Uttar Pradesh", ("uttar pradesh", "up"), "9"),
}


def list_target_states() -> list[dict]:
    if has_app_context():
        dynamic = list_import_regions(country_code="IN", region_level="state")
        if dynamic:
            return [
                {
                    "slug": item["slug"],
                    "name": item["name"],
                    "aliases": item["aliases"],
                    "lgd_state_code": item["region_code"],
                    "source": item["source"],
                }
                for item in dynamic
            ]
    return [state.to_dict() for state in TARGET_STATES.values()]


def bootstrap_state_geography(
    actor: Any,
    *,
    state_slug: str,
    districts: list[dict] | None = None,
    subdistricts: list[dict] | None = None,
    villages: list[dict] | None = None,
    blocks: list[dict] | None = None,
    panchayats: list[dict] | None = None,
    local_bodies: list[dict] | None = None,
    village_panchayat_links: list[dict] | None = None,
    source: str = "lgd",
    freshness_at: str | None = None,
    dry_run: bool = True,
) -> dict:
    assert_owner(actor)
    state = _state(state_slug)

    collections = {
        "districts": list(districts or []),
        "subdistricts": list(subdistricts or []),
        "villages": list(villages or []),
        "blocks": list(blocks or []),
        "panchayats": list(panchayats or []),
        "local_bodies": list(local_bodies or []),
        "village_panchayat_links": list(village_panchayat_links or []),
    }
    total = sum(len(rows) for rows in collections.values())
    if total > 250000:
        raise ValueError("A single state bootstrap may contain at most 250000 rows.")

    preview = _validate_state_payload(state, collections)
    if dry_run:
        return {
            "status": "PREVIEW",
            "state": state.to_dict(),
            "source": source,
            "freshness_at": freshness_at,
            "counts": {key: len(value) for key, value in collections.items()},
            "validation": preview,
            "truth_notice": (
                "Preview only. Missing parents/rows are reported; ZENDOC does not synthesize geography."
            ),
        }

    if preview["rejected"]:
        raise ValueError("State bootstrap contains rejected rows; preview and correct them before apply.")

    country = _ensure_india(source=source, freshness_at=freshness_at)
    state_node = upsert_geography_node(
        node_type="state",
        name=state.name,
        parent_id=country["id"],
        source=source,
        source_ref=f"state:{state.lgd_state_code}",
        verified=True,
        freshness_at=freshness_at,
    )

    refs: dict[str, int] = {f"state:{state.lgd_state_code}": int(state_node["id"])}
    applied = {
        "districts": 0,
        "subdistricts": 0,
        "villages": 0,
        "blocks": 0,
        "panchayats": 0,
        "local_bodies": 0,
        "relationships": 0,
    }

    for row in collections["districts"]:
        node = upsert_geography_node(
            node_type="district",
            name=_required(row, "name"),
            parent_id=state_node["id"],
            source=source,
            source_ref=f"district:{_required(row, 'code')}",
            verified=True,
            freshness_at=freshness_at,
        )
        refs[f"district:{_required(row, 'code')}"] = int(node["id"])
        applied["districts"] += 1

    for row in collections["subdistricts"]:
        parent = refs.get(f"district:{_required(row, 'district_code')}")
        if not parent:
            raise ValueError(f"Unknown district_code {_required(row, 'district_code')} for sub-district.")
        node = upsert_geography_node(
            node_type="subdivision",
            name=_required(row, "name"),
            parent_id=parent,
            source=source,
            source_ref=f"subdistrict:{_required(row, 'code')}",
            verified=True,
            freshness_at=freshness_at,
        )
        refs[f"subdistrict:{_required(row, 'code')}"] = int(node["id"])
        applied["subdistricts"] += 1

    for row in collections["blocks"]:
        district_code = str(row.get("district_code") or "").strip()
        subdistrict_code = str(row.get("subdistrict_code") or "").strip()
        parent = refs.get(f"subdistrict:{subdistrict_code}") if subdistrict_code else None
        if not parent and district_code:
            parent = refs.get(f"district:{district_code}")
        if not parent:
            raise ValueError(f"Block {_required(row, 'code')} has no resolvable district/sub-district parent.")
        node = upsert_geography_node(
            node_type="block",
            name=_required(row, "name"),
            parent_id=parent,
            source=source,
            source_ref=f"block:{_required(row, 'code')}",
            verified=True,
            freshness_at=freshness_at,
        )
        refs[f"block:{_required(row, 'code')}"] = int(node["id"])
        applied["blocks"] += 1

    for row in collections["panchayats"]:
        block_code = str(row.get("block_code") or "").strip()
        district_code = str(row.get("district_code") or "").strip()
        parent = refs.get(f"block:{block_code}") if block_code else None
        if not parent and district_code:
            parent = refs.get(f"district:{district_code}")
        if not parent:
            raise ValueError(f"Panchayat {_required(row, 'code')} has no resolvable block/district parent.")
        node = upsert_geography_node(
            node_type="panchayat",
            name=_required(row, "name"),
            parent_id=parent,
            source=source,
            source_ref=f"panchayat:{_required(row, 'code')}",
            verified=True,
            freshness_at=freshness_at,
        )
        refs[f"panchayat:{_required(row, 'code')}"] = int(node["id"])
        applied["panchayats"] += 1

    for row in collections["local_bodies"]:
        district_code = str(row.get("district_code") or "").strip()
        subdistrict_code = str(row.get("subdistrict_code") or "").strip()
        parent = refs.get(f"subdistrict:{subdistrict_code}") if subdistrict_code else None
        if not parent and district_code:
            parent = refs.get(f"district:{district_code}")
        if not parent:
            raise ValueError(f"Local body {_required(row, 'code')} has no resolvable district/sub-district parent.")
        body_type = str(row.get("node_type") or "municipality").strip().lower()
        if body_type not in {"municipality", "town", "city", "panchayat"}:
            body_type = "municipality"
        node = upsert_geography_node(
            node_type=body_type,
            name=_required(row, "name"),
            parent_id=parent,
            source=source,
            source_ref=f"localbody:{_required(row, 'code')}",
            verified=True,
            freshness_at=freshness_at,
        )
        refs[f"localbody:{_required(row, 'code')}"] = int(node["id"])
        applied["local_bodies"] += 1

    for row in collections["villages"]:
        subdistrict_code = str(row.get("subdistrict_code") or "").strip()
        block_code = str(row.get("block_code") or "").strip()
        panchayat_code = str(row.get("panchayat_code") or "").strip()
        district_code = str(row.get("district_code") or "").strip()

        # Administrative parent preference: sub-district, then block, then district.
        # Panchayat membership is modeled separately below.
        parent = refs.get(f"subdistrict:{subdistrict_code}") if subdistrict_code else None
        if not parent and block_code:
            parent = refs.get(f"block:{block_code}")
        if not parent and district_code:
            parent = refs.get(f"district:{district_code}")
        if not parent:
            raise ValueError(f"Village {_required(row, 'code')} has no resolvable administrative parent.")

        node = upsert_geography_node(
            node_type="village",
            name=_required(row, "name"),
            parent_id=parent,
            source=source,
            source_ref=f"village:{_required(row, 'code')}",
            verified=True,
            freshness_at=freshness_at,
        )
        refs[f"village:{_required(row, 'code')}"] = int(node["id"])
        applied["villages"] += 1

        if panchayat_code and refs.get(f"panchayat:{panchayat_code}"):
            link_geography_nodes(
                from_node_id=node["id"],
                to_node_id=refs[f"panchayat:{panchayat_code}"],
                relationship_type="VILLAGE_TO_PANCHAYAT",
                source=source,
                source_ref=f"village:{_required(row, 'code')}:panchayat:{panchayat_code}",
                freshness_at=freshness_at,
            )
            applied["relationships"] += 1

        if block_code and refs.get(f"block:{block_code}"):
            link_geography_nodes(
                from_node_id=node["id"],
                to_node_id=refs[f"block:{block_code}"],
                relationship_type="BLOCK_MEMBERSHIP",
                source=source,
                source_ref=f"village:{_required(row, 'code')}:block:{block_code}",
                freshness_at=freshness_at,
            )
            applied["relationships"] += 1

    for row in collections["village_panchayat_links"]:
        village = refs.get(f"village:{_required(row, 'village_code')}")
        panchayat = refs.get(f"panchayat:{_required(row, 'panchayat_code')}")
        if not village or not panchayat:
            raise ValueError("Village-panchayat relationship references unknown code.")
        link_geography_nodes(
            from_node_id=village,
            to_node_id=panchayat,
            relationship_type="VILLAGE_TO_PANCHAYAT",
            source=source,
            source_ref=str(row.get("source_ref") or "").strip() or None,
            freshness_at=freshness_at,
        )
        applied["relationships"] += 1

    return {
        "status": "APPLIED",
        "state": state.to_dict(),
        "state_node_id": state_node["id"],
        "source": source,
        "freshness_at": freshness_at,
        "applied": applied,
        "truth_notice": "Only supplied official rows were created; no missing locality was synthesized.",
    }


def state_coverage_summary(state_slug: str) -> dict:
    state = _state(state_slug)
    db = get_db()
    state_row = db.execute(
        "SELECT id FROM geography_nodes WHERE node_type='state' AND source_ref=? ORDER BY id DESC LIMIT 1",
        (f"state:{state.lgd_state_code}",),
    ).fetchone()
    if not state_row:
        return {
            "state": state.to_dict(),
            "loaded": False,
            "counts": {},
        }

    state_id = int(state_row["id"])
    district_rows = db.execute(
        "SELECT id FROM geography_nodes WHERE node_type='district' AND parent_id=?",
        (state_id,),
    ).fetchall()
    district_ids = [int(row["id"]) for row in district_rows]

    counts = {"district": len(district_ids), "subdivision": 0, "block": 0, "panchayat": 0, "municipality": 0, "city": 0, "town": 0, "village": 0}
    if district_ids:
        placeholders = ",".join("?" for _ in district_ids)
        rows = db.execute(
            f"""
            WITH RECURSIVE descendants(id,node_type) AS (
              SELECT id,node_type FROM geography_nodes WHERE parent_id IN ({placeholders})
              UNION ALL
              SELECT g.id,g.node_type
              FROM geography_nodes g JOIN descendants d ON g.parent_id=d.id
            )
            SELECT node_type, COUNT(*) c FROM descendants GROUP BY node_type
            """,
            district_ids,
        ).fetchall()
        for row in rows:
            counts[str(row["node_type"])] = int(row["c"])

    relationships = db.execute(
        """
        SELECT relationship_type, COUNT(*) c
        FROM geography_relationships
        WHERE from_node_id IN (
            WITH RECURSIVE descendants(id) AS (
              SELECT id FROM geography_nodes WHERE parent_id=?
              UNION ALL
              SELECT g.id FROM geography_nodes g JOIN descendants d ON g.parent_id=d.id
            )
            SELECT id FROM descendants
        )
        GROUP BY relationship_type
        """,
        (state_id,),
    ).fetchall()

    return {
        "state": state.to_dict(),
        "loaded": True,
        "counts": counts,
        "relationships": {row["relationship_type"]: int(row["c"]) for row in relationships},
    }


def _validate_state_payload(state: TargetState, collections: dict[str, list[dict]]) -> dict:
    rejected = []
    duplicates = {}

    for key, rows in collections.items():
        seen = set()
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                rejected.append({"collection": key, "row_number": index, "reason": "row is not an object"})
                continue
            if key == "village_panchayat_links":
                required = ("village_code", "panchayat_code")
            else:
                required = ("code", "name")
            missing = [field for field in required if not str(row.get(field) or "").strip()]
            if missing:
                rejected.append({"collection": key, "row_number": index, "reason": "missing: " + ", ".join(missing)})
                continue

            code = str(row.get(required[0]) or "").strip()
            if code in seen:
                duplicates.setdefault(key, []).append(code)
            seen.add(code)

            row_state_code = str(row.get("state_code") or "").strip()
            if row_state_code and row_state_code != state.lgd_state_code:
                rejected.append({
                    "collection": key,
                    "row_number": index,
                    "reason": f"state_code {row_state_code} does not match target state code {state.lgd_state_code}",
                })

    for key, codes in duplicates.items():
        for code in sorted(set(codes)):
            rejected.append({"collection": key, "reason": f"duplicate code in payload: {code}"})

    return {
        "rejected": rejected[:500],
        "rejected_count": len(rejected),
        "valid": not rejected,
    }


def _ensure_india(*, source: str, freshness_at: str | None) -> dict:
    return upsert_geography_node(
        node_type="country",
        name="India",
        source=source,
        source_ref="country:IN",
        verified=True,
        freshness_at=freshness_at,
    )


def _state(slug: str) -> TargetState:
    key = str(slug or "").strip().lower().replace("-", "_").replace(" ", "_")
    dynamic = find_import_region(
        country_code="IN",
        region_level="state",
        slug_or_code=key,
    )
    if dynamic:
        return TargetState(
            dynamic["slug"],
            dynamic["name"],
            tuple(dynamic["aliases"]),
            dynamic["region_code"],
        )
    state = TARGET_STATES.get(key)
    if not state:
        raise LookupError(
            f"Unsupported target state '{slug}'. Import the official LGD States registry first."
        )
    return state


def _required(row: dict, key: str) -> str:
    value = str(row.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value
