"""ZENDOC Geographic Healthcare Graph v1.

No location is fabricated or preloaded here. Nodes and links must carry source
provenance. The graph is designed for official datasets, verified ZENDOC
providers, configured external place providers, and future partner feeds.
"""
from __future__ import annotations

import json
import re
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from .db import get_db, now_iso


NODE_TYPES = {
    "country",
    "state",
    "district",
    "subdivision",
    "block",
    "municipality",
    "panchayat",
    "city",
    "town",
    "village",
    "locality",
}

ENTITY_TYPES = {
    "provider",
    "hospital",
    "clinic",
    "pharmacy",
    "diagnostic_lab",
    "scheme",
    "insurance_network",
    "ngo",
    "trust",
    "csr_program",
    "device_service",
    "home_care",
    "transport",
}

VERIFICATION_STATES = {
    "ZENDOC_VERIFIED",
    "EXTERNAL_UNVERIFIED",
    "PARTNER_CONNECTED",
    "INTEGRATION_REQUIRED",
}

ALLOWED_PARENTS = {
    "country": {None},
    "state": {"country"},
    "district": {"state"},
    "subdivision": {"district"},
    "block": {"district", "subdivision"},
    "municipality": {"district", "subdivision"},
    "panchayat": {"block", "district"},
    "city": {"district", "subdivision", "municipality"},
    "town": {"district", "subdivision", "block", "municipality"},
    "village": {"district", "subdivision", "block", "panchayat"},
    "locality": {"city", "town", "village", "municipality", "panchayat"},
}


_DEFER_GEOGRAPHY_COMMIT = ContextVar("zendoc_defer_geography_commit", default=False)


@contextmanager
def geography_write_transaction():
    """Make a group of geography writes atomic on SQLite and PostgreSQL.

    Geography write helpers historically committed every row. During an import
    this context defers those inner commits, commits once on success, and rolls
    the whole batch back on failure. Nested use delegates commit/rollback to
    the outer transaction.
    """
    db = get_db()
    already_deferred = _DEFER_GEOGRAPHY_COMMIT.get()
    token = _DEFER_GEOGRAPHY_COMMIT.set(True)
    try:
        yield db
        if not already_deferred:
            db.commit()
    except Exception:
        if not already_deferred:
            db.rollback()
        raise
    finally:
        _DEFER_GEOGRAPHY_COMMIT.reset(token)


def _commit_geography_write(db) -> None:
    if not _DEFER_GEOGRAPHY_COMMIT.get():
        db.commit()


def upsert_geography_node(
    *,
    node_type: str,
    name: str,
    source: str,
    source_ref: str | None = None,
    parent_id: int | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    verified: bool = False,
    freshness_at: str | None = None,
) -> dict[str, Any]:
    node_type = str(node_type or "").strip().lower()
    if node_type not in NODE_TYPES:
        raise ValueError("Unsupported geography node_type.")
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("Geography name is required.")
    clean_source = str(source or "").strip()
    if not clean_source:
        raise ValueError("Geography provenance source is required.")
    clean_source_ref = str(source_ref or "").strip() or None

    lat = _coordinate(latitude, -90, 90, "latitude")
    lng = _coordinate(longitude, -180, 180, "longitude")
    db = get_db()

    parent_type = None
    if parent_id is not None:
        parent = db.execute("SELECT * FROM geography_nodes WHERE id=?", (int(parent_id),)).fetchone()
        if not parent:
            raise LookupError(f"Parent geography node #{parent_id} not found.")
        parent_type = parent["node_type"]
    if parent_type not in ALLOWED_PARENTS[node_type]:
        raise ValueError(f"{node_type} cannot have parent type {parent_type or 'none'}.")

    normalized = normalize_geography_name(clean_name)

    # Official/provider source references are the stable identity when present.
    # This lets a renamed official place update the same node instead of
    # creating a duplicate or leaving normalized_name stale.
    existing = None
    if clean_source_ref:
        existing = db.execute(
            "SELECT * FROM geography_nodes WHERE node_type=? AND source_ref=? ORDER BY id ASC LIMIT 1",
            (node_type, clean_source_ref),
        ).fetchone()

    # Backward-compatible adoption path for legacy rows created before stable
    # source references were used as identity. Never merge into a row that
    # already belongs to a different source_ref.
    if existing is None:
        if parent_id is None:
            existing = db.execute(
                """
                SELECT * FROM geography_nodes
                WHERE node_type=? AND normalized_name=? AND parent_id IS NULL
                  AND (source_ref IS NULL OR source_ref='')
                LIMIT 1
                """,
                (node_type, normalized),
            ).fetchone()
        else:
            existing = db.execute(
                """
                SELECT * FROM geography_nodes
                WHERE node_type=? AND normalized_name=? AND parent_id=?
                  AND (source_ref IS NULL OR source_ref='')
                LIMIT 1
                """,
                (node_type, normalized, int(parent_id)),
            ).fetchone()

    now = now_iso()
    if existing:
        db.execute(
            """
            UPDATE geography_nodes
            SET name=?, normalized_name=?, parent_id=?,
                latitude=COALESCE(?, latitude), longitude=COALESCE(?, longitude),
                source=?, source_ref=?, verified=?, freshness_at=?, updated_at=?
            WHERE id=?
            """,
            (
                clean_name,
                normalized,
                int(parent_id) if parent_id is not None else None,
                lat,
                lng,
                clean_source,
                clean_source_ref,
                1 if verified else 0,
                freshness_at,
                now,
                existing["id"],
            ),
        )
        node_id = existing["id"]
    else:
        node_uid = f"geo_{node_type}_{uuid.uuid4().hex[:16]}"
        cursor = db.execute(
            """
            INSERT INTO geography_nodes
            (node_uid,node_type,name,normalized_name,parent_id,latitude,longitude,source,source_ref,verified,freshness_at,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                node_uid,
                node_type,
                clean_name,
                normalized,
                int(parent_id) if parent_id is not None else None,
                lat,
                lng,
                clean_source,
                clean_source_ref,
                1 if verified else 0,
                freshness_at,
                now,
                now,
            ),
        )
        node_id = cursor.lastrowid
    _commit_geography_write(db)
    return get_geography_node(node_id)


def get_geography_node(node_id: int) -> dict[str, Any]:
    row = get_db().execute("SELECT * FROM geography_nodes WHERE id=?", (int(node_id),)).fetchone()
    if not row:
        raise LookupError(f"Geography node #{node_id} not found.")
    result = dict(row)
    result["path"] = geography_path(node_id)
    return result


def geography_path(node_id: int) -> list[dict[str, Any]]:
    db = get_db()
    path = []
    current_id = int(node_id)
    visited = set()
    while current_id:
        if current_id in visited:
            raise RuntimeError("Geography graph cycle detected.")
        visited.add(current_id)
        row = db.execute(
            "SELECT id,node_type,name,parent_id,source,verified FROM geography_nodes WHERE id=?",
            (current_id,),
        ).fetchone()
        if not row:
            break
        path.append(dict(row))
        current_id = int(row["parent_id"] or 0)
        if len(path) > 20:
            raise RuntimeError("Geography hierarchy exceeds safe depth.")
    path.reverse()
    return path


def search_geography_nodes(
    query: str,
    *,
    node_type: str | None = None,
    limit: int = 25,
) -> list[dict[str, Any]]:
    normalized = normalize_geography_name(query)
    if not normalized:
        return []
    limit = max(1, min(int(limit or 25), 100))
    db = get_db()
    params: list[Any] = [f"%{normalized}%"]
    where = ["normalized_name LIKE ?"]
    if node_type:
        clean_type = str(node_type).strip().lower()
        if clean_type not in NODE_TYPES:
            raise ValueError("Unsupported geography node_type.")
        where.append("node_type=?")
        params.append(clean_type)
    params.append(limit)
    rows = db.execute(
        f"""
        SELECT * FROM geography_nodes
        WHERE {' AND '.join(where)}
        ORDER BY verified DESC, node_type ASC, name ASC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [{**dict(row), "path": geography_path(row["id"])} for row in rows]


def link_entity_to_geography(
    *,
    geography_node_id: int,
    entity_type: str,
    entity_id: str | int,
    source: str,
    verification_state: str,
    freshness_at: str | None = None,
    metadata: dict | None = None,
) -> dict[str, Any]:
    entity_type = str(entity_type or "").strip().lower()
    if entity_type not in ENTITY_TYPES:
        raise ValueError("Unsupported geography entity_type.")
    verification = str(verification_state or "").strip().upper()
    if verification not in VERIFICATION_STATES:
        raise ValueError("Unsupported verification_state.")
    source = str(source or "").strip()
    if not source:
        raise ValueError("Entity link provenance source is required.")
    entity_id_text = str(entity_id or "").strip()
    if not entity_id_text:
        raise ValueError("entity_id is required.")

    db = get_db()
    if not db.execute("SELECT 1 FROM geography_nodes WHERE id=?", (int(geography_node_id),)).fetchone():
        raise LookupError(f"Geography node #{geography_node_id} not found.")

    now = now_iso()
    metadata_json = json.dumps(metadata or {}, sort_keys=True, separators=(",", ":"))
    existing = db.execute(
        """
        SELECT * FROM geography_entity_links
        WHERE geography_node_id=? AND entity_type=? AND entity_id=? AND source=?
        LIMIT 1
        """,
        (int(geography_node_id), entity_type, entity_id_text, source),
    ).fetchone()
    if existing:
        db.execute(
            """
            UPDATE geography_entity_links
            SET verification_state=?, freshness_at=?, metadata_json=?, updated_at=?
            WHERE id=?
            """,
            (verification, freshness_at, metadata_json, now, existing["id"]),
        )
        link_id = existing["id"]
    else:
        cursor = db.execute(
            """
            INSERT INTO geography_entity_links
            (geography_node_id,entity_type,entity_id,source,verification_state,freshness_at,metadata_json,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                int(geography_node_id),
                entity_type,
                entity_id_text,
                source,
                verification,
                freshness_at,
                metadata_json,
                now,
                now,
            ),
        )
        link_id = cursor.lastrowid
    _commit_geography_write(db)
    return get_entity_link(link_id)


def get_entity_link(link_id: int) -> dict[str, Any]:
    row = get_db().execute(
        "SELECT * FROM geography_entity_links WHERE id=?",
        (int(link_id),),
    ).fetchone()
    if not row:
        raise LookupError(f"Geography entity link #{link_id} not found.")
    result = dict(row)
    try:
        result["metadata"] = json.loads(result.pop("metadata_json") or "{}")
    except json.JSONDecodeError:
        result["metadata"] = {}
    return result


def list_entities_for_geography(
    geography_node_id: int,
    *,
    entity_type: str | None = None,
) -> list[dict[str, Any]]:
    db = get_db()
    params: list[Any] = [int(geography_node_id)]
    where = ["geography_node_id=?"]
    if entity_type:
        clean_type = str(entity_type).strip().lower()
        if clean_type not in ENTITY_TYPES:
            raise ValueError("Unsupported geography entity_type.")
        where.append("entity_type=?")
        params.append(clean_type)
    rows = db.execute(
        f"SELECT * FROM geography_entity_links WHERE {' AND '.join(where)} ORDER BY updated_at DESC",
        params,
    ).fetchall()
    return [get_entity_link(row["id"]) for row in rows]



RELATIONSHIP_TYPES = {
    "ADMIN_PARENT",
    "BLOCK_MEMBERSHIP",
    "PANCHAYAT_MEMBERSHIP",
    "URBAN_LOCAL_BODY_MEMBERSHIP",
    "VILLAGE_TO_PANCHAYAT",
    "SOURCE_EQUIVALENT",
}


def link_geography_nodes(
    *,
    from_node_id: int,
    to_node_id: int,
    relationship_type: str,
    source: str,
    source_ref: str | None = None,
    freshness_at: str | None = None,
    metadata: dict | None = None,
) -> dict[str, Any]:
    relationship_type = str(relationship_type or "").strip().upper()
    if relationship_type not in RELATIONSHIP_TYPES:
        raise ValueError("Unsupported geography relationship_type.")
    source = str(source or "").strip()
    if not source:
        raise ValueError("Geography relationship provenance source is required.")
    clean_source_ref = str(source_ref or "").strip() or None

    db = get_db()
    for node_id in (int(from_node_id), int(to_node_id)):
        if not db.execute("SELECT 1 FROM geography_nodes WHERE id=?", (node_id,)).fetchone():
            raise LookupError(f"Geography node #{node_id} not found.")

    now = now_iso()
    metadata_json = json.dumps(metadata or {}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    existing = db.execute(
        """
        SELECT * FROM geography_relationships
        WHERE from_node_id=? AND to_node_id=? AND relationship_type=? AND source=?
        LIMIT 1
        """,
        (int(from_node_id), int(to_node_id), relationship_type, source),
    ).fetchone()
    if existing:
        db.execute(
            """
            UPDATE geography_relationships
            SET source_ref=?, freshness_at=?, metadata_json=?, updated_at=?
            WHERE id=?
            """,
            (clean_source_ref, freshness_at, metadata_json, now, existing["id"]),
        )
        relationship_id = existing["id"]
    else:
        cursor = db.execute(
            """
            INSERT INTO geography_relationships
            (from_node_id,to_node_id,relationship_type,source,source_ref,freshness_at,metadata_json,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                int(from_node_id), int(to_node_id), relationship_type, source,
                clean_source_ref, freshness_at, metadata_json, now, now,
            ),
        )
        relationship_id = cursor.lastrowid
    _commit_geography_write(db)
    return get_geography_relationship(relationship_id)


def get_geography_relationship(relationship_id: int) -> dict[str, Any]:
    row = get_db().execute(
        "SELECT * FROM geography_relationships WHERE id=?",
        (int(relationship_id),),
    ).fetchone()
    if not row:
        raise LookupError(f"Geography relationship #{relationship_id} not found.")
    result = dict(row)
    try:
        result["metadata"] = json.loads(result.pop("metadata_json") or "{}")
    except json.JSONDecodeError:
        result["metadata"] = {}
    return result


def list_geography_relationships(node_id: int, *, relationship_type: str | None = None) -> list[dict[str, Any]]:
    params: list[Any] = [int(node_id), int(node_id)]
    where = ["(from_node_id=? OR to_node_id=?)"]
    if relationship_type:
        clean = str(relationship_type).strip().upper()
        if clean not in RELATIONSHIP_TYPES:
            raise ValueError("Unsupported geography relationship_type.")
        where.append("relationship_type=?")
        params.append(clean)
    rows = get_db().execute(
        f"SELECT id FROM geography_relationships WHERE {' AND '.join(where)} ORDER BY updated_at DESC",
        params,
    ).fetchall()
    return [get_geography_relationship(row["id"]) for row in rows]

def normalize_geography_name(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9ऀ-ॿঀ-৿]+", " ", text)
    return " ".join(text.split())


def _coordinate(value: Any, minimum: float, maximum: float, label: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric.") from exc
    if number < minimum or number > maximum:
        raise ValueError(f"{label} is out of range.")
    return number
