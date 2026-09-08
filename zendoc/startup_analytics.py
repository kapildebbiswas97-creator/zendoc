"""Privacy-safe startup product analytics and India data-quality summaries.

No clinical text, medical record content, symptom text, or raw free-text
location query is stored here. Exact canonical geography may be recorded by
node id; otherwise only a one-way hash of a location search is retained.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from .db import get_db, now_iso
from .geography_graph import geography_path, normalize_geography_name
from .india_regions import india_region_catalog
from .security import assert_owner


def _cutoff_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))).isoformat(timespec="seconds")


def _canonical_search_geography(location: str | None) -> int | None:
    normalized = normalize_geography_name(location)
    if not normalized:
        return None
    rows = get_db().execute(
        """
        SELECT id FROM geography_nodes
        WHERE normalized_name=?
          AND node_type IN ('state','district','subdivision','block','municipality','panchayat','city','town','village','locality')
        ORDER BY id ASC
        """,
        (normalized,),
    ).fetchall()
    if len(rows) != 1:
        return None
    return int(rows[0]["id"])


def record_finder_search(
    user: Any,
    *,
    category: str,
    location: str | None,
    result_count: int,
    source_tiers: dict[str, Any] | None = None,
) -> None:
    user_id = None
    try:
        user_id = int(user["id"])
    except Exception:
        pass

    clean_location = str(location or "").strip()
    geography_node_id = _canonical_search_geography(clean_location)
    location_hash = (
        hashlib.sha256(clean_location.casefold().encode("utf-8")).hexdigest()[:32]
        if clean_location and geography_node_id is None
        else None
    )
    get_db().execute(
        """
        INSERT INTO product_analytics_events
        (user_id,event_type,category,geography_node_id,location_hash,result_count,useful_result,source_tiers_json,metadata_json,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            user_id,
            "healthcare_search",
            str(category or "").strip().lower() or None,
            geography_node_id,
            location_hash,
            max(0, int(result_count or 0)),
            1 if int(result_count or 0) > 0 else 0,
            json.dumps(source_tiers or {}, sort_keys=True, separators=(",", ":")),
            "{}",
            now_iso(),
        ),
    )


def startup_metrics(actor: Any, *, days: int = 30) -> dict:
    assert_owner(actor)
    days = max(1, min(int(days or 30), 365))
    cutoff = _cutoff_iso(days)
    db = get_db()

    rows = db.execute(
        """
        SELECT user_id,category,geography_node_id,result_count,useful_result,source_tiers_json,created_at
        FROM product_analytics_events
        WHERE event_type='healthcare_search' AND created_at>=?
        ORDER BY created_at ASC
        """,
        (cutoff,),
    ).fetchall()

    total = len(rows)
    useful = sum(int(row["useful_result"] or 0) for row in rows)
    user_events: dict[int, int] = defaultdict(int)
    category_counts = Counter()
    geography_counts = Counter()
    source_totals = Counter()

    for row in rows:
        if row["user_id"] is not None:
            user_events[int(row["user_id"])] += 1
        if row["category"]:
            category_counts[str(row["category"])] += 1
        if row["geography_node_id"] is not None:
            geography_counts[int(row["geography_node_id"])] += 1
        try:
            tiers = json.loads(row["source_tiers_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            tiers = {}
        for key, value in tiers.items():
            try:
                source_totals[str(key)] += int(value or 0)
            except (TypeError, ValueError):
                continue

    top_geographies = []
    for node_id, count in geography_counts.most_common(10):
        node = db.execute(
            "SELECT id,node_type,name,source,source_ref FROM geography_nodes WHERE id=?",
            (node_id,),
        ).fetchone()
        if node:
            top_geographies.append({**dict(node), "search_count": count})

    active_users = len(user_events)
    repeat_users = sum(1 for count in user_events.values() if count >= 2)
    return {
        "window_days": days,
        "healthcare_searches": total,
        "useful_searches": useful,
        "no_result_searches": total - useful,
        "useful_result_rate": round(useful / total, 4) if total else None,
        "no_result_rate": round((total - useful) / total, 4) if total else None,
        "active_search_users": active_users,
        "repeat_search_users": repeat_users,
        "repeat_search_user_rate": round(repeat_users / active_users, 4) if active_users else None,
        "top_categories": [
            {"category": category, "search_count": count}
            for category, count in category_counts.most_common(10)
        ],
        "top_canonical_geographies": top_geographies,
        "source_result_totals": dict(source_totals),
        "privacy_notice": (
            "Metrics exclude clinical text and raw free-text location queries. Canonical geography is stored only "
            "when an exact unique geography node is resolved; otherwise only a one-way location hash is retained."
        ),
        "metric_notice": (
            "repeat_search_user_rate is a product-usage signal, not cohort D7/D30 retention. True retention should "
            "be added after enough real-user history exists."
        ),
    }


def india_coverage_quality(actor: Any) -> dict:
    assert_owner(actor)
    db = get_db()
    regions = india_region_catalog()

    all_nodes = db.execute(
        """
        SELECT id,node_type,name,normalized_name,parent_id,source,source_ref,verified,freshness_at
        FROM geography_nodes
        ORDER BY id
        """
    ).fetchall()
    state_nodes = {
        normalize_geography_name(row["name"]): dict(row)
        for row in all_nodes
        if row["node_type"] == "state"
    }

    counts_by_state: dict[int, Counter] = defaultdict(Counter)
    for row in all_nodes:
        try:
            path = geography_path(int(row["id"]))
        except (LookupError, RuntimeError):
            continue
        state = next((item for item in path if item["node_type"] == "state"), None)
        if state:
            counts_by_state[int(state["id"])][str(row["node_type"])] += 1

    public_entities = db.execute(
        "SELECT id,category,source_id,active FROM public_healthcare_entities WHERE active=1"
    ).fetchall()
    linked_rows = db.execute(
        """
        SELECT entity_id,entity_type,geography_node_id
        FROM geography_entity_links
        WHERE entity_type IN ('hospital','clinic','doctor','pharmacy','diagnostic_lab','diagnostic_centre',
                              'laboratory','nursing_home','health_centre','blood_bank')
        """
    ).fetchall()

    linked_public_ids = set()
    facilities_by_state: dict[int, Counter] = defaultdict(Counter)
    entity_category_by_id = {str(row["id"]): str(row["category"]) for row in public_entities}
    for link in linked_rows:
        entity_id = str(link["entity_id"])
        if entity_id not in entity_category_by_id:
            continue
        linked_public_ids.add(entity_id)
        try:
            path = geography_path(int(link["geography_node_id"]))
        except (LookupError, RuntimeError):
            continue
        state = next((item for item in path if item["node_type"] == "state"), None)
        if state:
            facilities_by_state[int(state["id"])][entity_category_by_id[entity_id]] += 1

    region_rows = []
    for region in regions:
        state = state_nodes.get(normalize_geography_name(region["name"]))
        if not state:
            region_rows.append({
                **region,
                "canonical_state_loaded": False,
                "geography_counts": {},
                "linked_public_facility_counts": {},
                "status": "OFFICIAL_GEOGRAPHY_NOT_IMPORTED",
            })
            continue

        state_id = int(state["id"])
        geo_counts = dict(counts_by_state[state_id])
        facility_counts = dict(facilities_by_state[state_id])
        deeper_nodes = sum(
            geo_counts.get(key, 0)
            for key in ("district","subdivision","block","municipality","panchayat","city","town","village","locality")
        )
        region_rows.append({
            **region,
            "canonical_state_loaded": True,
            "state_node_id": state_id,
            "state_source": state["source"],
            "state_source_ref": state["source_ref"],
            "geography_counts": geo_counts,
            "linked_public_facility_counts": facility_counts,
            "status": "DATA_PRESENT" if deeper_nodes or facility_counts else "STATE_ONLY",
        })

    ingestion_rows = db.execute(
        """
        SELECT summary_json FROM data_ingestion_batches
        WHERE ingestion_type='public_healthcare_entities' AND dry_run=0 AND status='completed'
        """
    ).fetchall()
    unresolved = ambiguous = 0
    for row in ingestion_rows:
        try:
            summary = json.loads(row["summary_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            summary = {}
        unresolved += int(summary.get("geography_unresolved_count", 0) or 0)
        ambiguous += int(summary.get("geography_ambiguous_count", 0) or 0)

    return {
        "country": "India",
        "region_target_count": len(regions),
        "canonical_state_nodes_loaded": sum(1 for item in region_rows if item["canonical_state_loaded"]),
        "geography_node_count": len(all_nodes),
        "public_healthcare_entity_count": len(public_entities),
        "public_healthcare_entities_linked_to_canonical_geography": len(linked_public_ids),
        "public_healthcare_entities_unlinked": len(public_entities) - len(linked_public_ids),
        "historical_unresolved_geography_imports": unresolved,
        "historical_ambiguous_geography_imports": ambiguous,
        "regions": region_rows,
        "truth_notice": (
            "Counts describe data actually present in this database. ZENDOC does not report a percentage of national "
            "coverage unless an official denominator for the relevant geography/facility class has been imported."
        ),
    }
