"""Safe canonical geography resolution for public facility ingestion.

Resolution is deliberately conservative:
- explicit source/source_ref wins;
- otherwise only exact normalized names are considered;
- parent hierarchy is used to disambiguate;
- fuzzy/nearest-name guessing is never performed;
- ambiguous or missing matches are returned explicitly.
"""
from __future__ import annotations

from typing import Any

from .db import get_db
from .geography_graph import geography_path, normalize_geography_name


LEVELS = (
    ("state", ("state",)),
    ("district", ("district",)),
    ("subdistrict", ("subdivision",)),
    ("block", ("block",)),
    ("village", ("village",)),
    ("locality", ("locality", "city", "town")),
)


def resolve_canonical_geography(
    *,
    source: str = "lgd",
    source_ref: str | None = None,
    state: str | None = None,
    district: str | None = None,
    subdistrict: str | None = None,
    block: str | None = None,
    village: str | None = None,
    locality: str | None = None,
) -> dict[str, Any]:
    db = get_db()
    clean_source = str(source or "lgd").strip() or "lgd"
    clean_ref = str(source_ref or "").strip() or None

    if clean_ref:
        rows = db.execute(
            """
            SELECT * FROM geography_nodes
            WHERE source=? AND source_ref=?
            ORDER BY id ASC
            """,
            (clean_source, clean_ref),
        ).fetchall()
        return _resolution_from_rows(
            rows,
            requested_level="source_ref",
            resolution_method="EXACT_SOURCE_REF",
            source=clean_source,
            source_ref=clean_ref,
        )

    requested = {
        "state": state,
        "district": district,
        "subdistrict": subdistrict,
        "block": block,
        "village": village,
        "locality": locality,
    }
    provided = [
        (level, node_types, normalize_geography_name(requested[level]))
        for level, node_types in LEVELS
        if normalize_geography_name(requested[level])
    ]
    if not provided:
        return {
            "status": "NOT_REQUESTED",
            "geography_node_id": None,
            "matched_level": None,
            "resolution_method": None,
            "candidate_count": 0,
        }

    matched_ids: dict[str, int] = {}
    deepest_result = None

    for level, node_types, normalized in provided:
        placeholders = ",".join("?" for _ in node_types)
        rows = db.execute(
            f"""
            SELECT * FROM geography_nodes
            WHERE source=?
              AND node_type IN ({placeholders})
              AND normalized_name=?
            ORDER BY id ASC
            """,
            (clean_source, *node_types, normalized),
        ).fetchall()

        candidates = []
        for row in rows:
            if not _matches_hierarchy_context(int(row["id"]), level, matched_ids):
                continue
            candidates.append(row)

        if len(candidates) == 1:
            node_id = int(candidates[0]["id"])
            matched_ids[level] = node_id
            deepest_result = {
                "status": "MATCHED",
                "geography_node_id": node_id,
                "matched_level": level,
                "resolution_method": "EXACT_HIERARCHICAL_NAME",
                "candidate_count": 1,
                "source": clean_source,
                "source_ref": candidates[0]["source_ref"],
                "path": geography_path(node_id),
            }
            continue

        if len(candidates) > 1:
            return {
                "status": "AMBIGUOUS",
                "geography_node_id": None,
                "matched_level": level,
                "resolution_method": "EXACT_HIERARCHICAL_NAME",
                "candidate_count": len(candidates),
                "source": clean_source,
                "candidate_ids": [int(row["id"]) for row in candidates[:25]],
            }

        return {
            "status": "NOT_FOUND",
            "geography_node_id": None,
            "matched_level": level,
            "resolution_method": "EXACT_HIERARCHICAL_NAME",
            "candidate_count": 0,
            "source": clean_source,
        }

    return deepest_result or {
        "status": "NOT_FOUND",
        "geography_node_id": None,
        "matched_level": None,
        "resolution_method": "EXACT_HIERARCHICAL_NAME",
        "candidate_count": 0,
        "source": clean_source,
    }



def _matches_hierarchy_context(candidate_id: int, candidate_level: str, matched_ids: dict[str, int]) -> bool:
    if not matched_ids:
        return True

    db = get_db()
    path_ids = {int(item["id"]) for item in geography_path(candidate_id)}

    for level in ("state", "district", "subdistrict", "village"):
        matched_id = matched_ids.get(level)
        if matched_id is not None and matched_id not in path_ids:
            return False

    block_id = matched_ids.get("block")
    if block_id is not None and candidate_level in {"village", "locality"}:
        if block_id in path_ids:
            return True
        relationship = db.execute(
            """
            SELECT 1 FROM geography_relationships
            WHERE (
                from_node_id=? AND to_node_id=?
                OR from_node_id=? AND to_node_id=?
            )
              AND relationship_type='BLOCK_MEMBERSHIP'
            LIMIT 1
            """,
            (candidate_id, block_id, block_id, candidate_id),
        ).fetchone()
        if relationship:
            return True

        # A locality may descend from a village that carries the block
        # membership relationship.
        if candidate_level == "locality":
            for ancestor_id in path_ids:
                relationship = db.execute(
                    """
                    SELECT 1 FROM geography_relationships
                    WHERE (
                        from_node_id=? AND to_node_id=?
                        OR from_node_id=? AND to_node_id=?
                    )
                      AND relationship_type='BLOCK_MEMBERSHIP'
                    LIMIT 1
                    """,
                    (ancestor_id, block_id, block_id, ancestor_id),
                ).fetchone()
                if relationship:
                    return True
        return False

    block_id = matched_ids.get("block")
    if block_id is not None and candidate_level == "block" and candidate_id != block_id:
        return False

    return True

def _resolution_from_rows(
    rows,
    *,
    requested_level: str,
    resolution_method: str,
    source: str,
    source_ref: str,
) -> dict[str, Any]:
    if not rows:
        return {
            "status": "NOT_FOUND",
            "geography_node_id": None,
            "matched_level": requested_level,
            "resolution_method": resolution_method,
            "candidate_count": 0,
            "source": source,
            "source_ref": source_ref,
        }
    if len(rows) > 1:
        return {
            "status": "AMBIGUOUS",
            "geography_node_id": None,
            "matched_level": requested_level,
            "resolution_method": resolution_method,
            "candidate_count": len(rows),
            "source": source,
            "source_ref": source_ref,
            "candidate_ids": [int(row["id"]) for row in rows[:25]],
        }

    node_id = int(rows[0]["id"])
    return {
        "status": "MATCHED",
        "geography_node_id": node_id,
        "matched_level": rows[0]["node_type"],
        "resolution_method": resolution_method,
        "candidate_count": 1,
        "source": source,
        "source_ref": rows[0]["source_ref"],
        "path": geography_path(node_id),
    }
