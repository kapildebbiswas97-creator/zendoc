"""Observed public-data freshness and ingestion quality for ZENDOC."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .db import get_db
from .public_source_registry import list_public_ingestion_sources
from .security import assert_owner


RECENT_DAYS = 30
AGING_DAYS = 90


def ingestion_freshness_report(actor: Any, *, recent_batch_limit: int = 50) -> dict:
    assert_owner(actor)
    db = get_db()
    sources = list_public_ingestion_sources()
    now = datetime.now(timezone.utc)

    rows = db.execute(
        """
        SELECT * FROM data_ingestion_batches
        WHERE dry_run=0 AND status='completed'
        ORDER BY completed_at DESC,id DESC
        """
    ).fetchall()
    latest_by_source: dict[str, dict] = {}
    for row in rows:
        item = dict(row)
        latest_by_source.setdefault(str(item["source_id"]), item)

    entity_rows = db.execute(
        """
        SELECT source_id,
               COUNT(*) entity_count,
               SUM(CASE WHEN freshness_at IS NULL OR freshness_at='' THEN 1 ELSE 0 END) missing_freshness_count,
               MAX(freshness_at) newest_entity_freshness
        FROM public_healthcare_entities
        WHERE active=1
        GROUP BY source_id
        """
    ).fetchall()
    entities_by_source = {str(row["source_id"]): dict(row) for row in entity_rows}

    source_rows = []
    counts = {
        "recent": 0,
        "aging": 0,
        "stale": 0,
        "never_ingested": 0,
        "reference_only": 0,
    }

    for source in sources:
        source_id = source["source_id"]
        supported_types = list(source.get("ingestion_types") or [])
        latest = latest_by_source.get(source_id)
        entity_stats = entities_by_source.get(source_id, {})
        status = "reference_only"
        age_days = None
        last_completed_at = None
        summary = {}

        if supported_types:
            if latest:
                last_completed_at = latest.get("completed_at") or latest.get("created_at")
                age_days = _age_days(last_completed_at, now)
                if age_days is None:
                    status = "stale"
                elif age_days <= RECENT_DAYS:
                    status = "recent"
                elif age_days <= AGING_DAYS:
                    status = "aging"
                else:
                    status = "stale"
                summary = _json_dict(latest.get("summary_json"))
            else:
                status = "never_ingested"

        counts[status] += 1
        unresolved = int(summary.get("geography_unresolved_count", 0) or 0)
        ambiguous = int(summary.get("geography_ambiguous_count", 0) or 0)
        linked = int(summary.get("geography_linked_count", 0) or 0)
        rejected = int(latest.get("rejected_count", 0) or 0) if latest else 0

        priority = _refresh_priority(
            status=status,
            unresolved=unresolved,
            ambiguous=ambiguous,
            rejected=rejected,
        )

        source_rows.append({
            "source_id": source_id,
            "name": source.get("name"),
            "owner": source.get("owner"),
            "geography": source.get("geography"),
            "trust_level": source.get("trust_level"),
            "live_fetch_status": source.get("live_fetch_status"),
            "ingestion_types": supported_types,
            "freshness_status": status,
            "age_days": age_days,
            "last_completed_at": last_completed_at,
            "last_record_count": int(latest.get("record_count", 0) or 0) if latest else 0,
            "last_accepted_count": int(latest.get("accepted_count", 0) or 0) if latest else 0,
            "last_rejected_count": rejected,
            "latest_geography_linked_count": linked,
            "latest_geography_unresolved_count": unresolved,
            "latest_geography_ambiguous_count": ambiguous,
            "active_entity_count": int(entity_stats.get("entity_count", 0) or 0),
            "entities_missing_freshness": int(entity_stats.get("missing_freshness_count", 0) or 0),
            "newest_entity_freshness": entity_stats.get("newest_entity_freshness"),
            "refresh_priority": priority,
            "official_url": source.get("official_url"),
            "notes": source.get("notes"),
        })

    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    source_rows.sort(key=lambda item: (order.get(item["refresh_priority"], 9), item["source_id"]))

    recent_batches = []
    for row in rows[: max(1, min(int(recent_batch_limit or 50), 200))]:
        item = dict(row)
        item["summary"] = _json_dict(item.pop("summary_json", "{}"))
        recent_batches.append(item)

    return {
        "source_count": len(sources),
        "status_counts": counts,
        "sources": source_rows,
        "recent_completed_batches": recent_batches,
        "thresholds": {
            "recent_days": RECENT_DAYS,
            "aging_days": AGING_DAYS,
        },
        "truth_notice": (
            "Freshness status is based on ZENDOC's observed completed ingestion history. "
            "It is not a claim that an external registry itself is complete or current. "
            "Reference-only sources are intentionally not treated as failed ingestion."
        ),
    }


def _refresh_priority(*, status: str, unresolved: int, ambiguous: int, rejected: int) -> str:
    if status in {"never_ingested", "stale"}:
        return "P0"
    if status == "aging":
        return "P1"
    if unresolved > 0 or ambiguous > 0 or rejected > 0:
        return "P1"
    if status == "recent":
        return "P2"
    return "P3"


def _age_days(value: Any, now: datetime) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    delta = now - parsed.astimezone(timezone.utc)
    return max(0, int(delta.total_seconds() // 86400))


def _json_dict(value: Any) -> dict:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
