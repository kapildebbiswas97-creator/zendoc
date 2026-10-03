"""Bounded scheduled refresh for machine-readable official/public directories.

Only non-personal, allowlisted public-healthcare directory connectors with a
configured data.gov.in resource are eligible for unattended refresh. The
worker advances through one bounded page per source/cycle, persists a cursor,
respects each source cadence, and uses the existing provenance-aware upsert.

Automatic apply is an explicit deployment opt-in. Without it the worker only
previews/validates data and records refresh evidence.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .db import get_db, now_iso
from .official_connectors import connector_readiness, fetch_data_gov_resource, list_connector_profiles
from .public_data_ingestion import ingest_public_records
from .public_source_registry import get_public_ingestion_source
from .security import assert_owner


def ensure_public_refresh_schema() -> None:
    get_db().executescript(
        """
        CREATE TABLE IF NOT EXISTS public_data_refresh_state (
            source_id TEXT PRIMARY KEY,
            next_offset INTEGER NOT NULL DEFAULT 0,
            upstream_total INTEGER,
            last_mode TEXT NOT NULL DEFAULT 'preview',
            cycle_started_at TEXT,
            last_attempt_at TEXT,
            last_success_at TEXT,
            last_error_category TEXT,
            last_result TEXT
        );
        """
    )


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _cadence_hours(value: str | None) -> int:
    cadence = str(value or "").strip().upper()
    if cadence.startswith("WEEKLY") or "_WEEKLY" in cadence:
        return 24 * 7
    if cadence.startswith("ANNUAL"):
        return 24 * 330
    if cadence.startswith("MONTHLY") or "_MONTHLY" in cadence:
        return 24 * 28
    if cadence in {"SOURCE_UPDATE", "SOURCE_DEFINED", "PARTNER_DEFINED", "STATE_SOURCE_DEFINED"}:
        return 24 * 28
    return 24 * 7


def _eligible_profiles() -> list[dict]:
    profiles = []
    for profile in list_connector_profiles():
        if profile.get("connector_type") != "DATA_GOV_RESOURCE_API_OR_DOWNLOAD":
            continue
        # Geography snapshots can have parent-before-child ordering constraints;
        # keep those owner-reviewed rather than silently applying partial pages.
        if profile.get("ingestion_type") != "public_healthcare_entities":
            continue
        source = get_public_ingestion_source(profile.get("source_id"))
        if not source or bool(source.get("personal_data_allowed")):
            continue
        profiles.append(profile)
    return profiles


def _state(source_id: str) -> dict:
    ensure_public_refresh_schema()
    row = get_db().execute(
        "SELECT * FROM public_data_refresh_state WHERE source_id=?",
        (source_id,),
    ).fetchone()
    if row:
        return dict(row)
    get_db().execute(
        "INSERT INTO public_data_refresh_state (source_id,last_mode) VALUES (?,'preview')",
        (source_id,),
    )
    get_db().commit()
    return dict(
        get_db().execute(
            "SELECT * FROM public_data_refresh_state WHERE source_id=?",
            (source_id,),
        ).fetchone()
    )


def _due(profile: dict, state: dict, mode: str, now: datetime) -> bool:
    if str(state.get("last_mode") or "preview") != mode:
        return True
    if int(state.get("next_offset") or 0) > 0:
        return True
    last_success = _parse_time(state.get("last_success_at"))
    if last_success is None:
        return True
    return now - last_success >= timedelta(hours=_cadence_hours(profile.get("refresh_cadence")))


def _record_failure(source_id: str, mode: str, error: Exception) -> None:
    get_db().execute(
        """
        INSERT INTO public_data_refresh_state
        (source_id,last_mode,last_attempt_at,last_error_category,last_result)
        VALUES (?,?,?,?,?)
        ON CONFLICT(source_id) DO UPDATE SET
          last_mode=excluded.last_mode,
          last_attempt_at=excluded.last_attempt_at,
          last_error_category=excluded.last_error_category,
          last_result=excluded.last_result
        """,
        (
            source_id,
            mode,
            now_iso(),
            type(error).__name__[:120],
            "failed",
        ),
    )
    get_db().commit()


def refresh_official_public_data(
    actor: Any,
    *,
    apply: bool = False,
    page_limit: int = 200,
    max_sources: int = 1,
) -> dict:
    """Refresh at most one bounded page for each selected due source."""
    assert_owner(actor)
    ensure_public_refresh_schema()
    page_limit = max(1, min(int(page_limit or 200), 500))
    max_sources = max(1, min(int(max_sources or 1), 3))
    mode = "apply" if apply else "preview"
    now = datetime.now(timezone.utc)

    outcomes = []
    configured = 0
    due_count = 0
    for profile in _eligible_profiles():
        source_id = str(profile["source_id"])
        readiness = connector_readiness(source_id)
        if not readiness.get("ready_for_fetch"):
            continue
        configured += 1

        state = _state(source_id)
        if not _due(profile, state, mode, now):
            continue
        due_count += 1
        if len(outcomes) >= max_sources:
            continue

        # Changing preview/apply mode starts a fresh pass so a previous preview
        # cursor can never cause records to be skipped when apply is enabled.
        offset = int(state.get("next_offset") or 0)
        if str(state.get("last_mode") or "preview") != mode:
            offset = 0

        try:
            fetched = fetch_data_gov_resource(
                source_id,
                limit=page_limit,
                offset=offset,
            )
            records = fetched.get("records") or []
            ingestion = ingest_public_records(
                actor,
                source_id=source_id,
                ingestion_type=str(profile["ingestion_type"]),
                records=records,
                dry_run=not apply,
            )
            upstream_count = max(0, int(fetched.get("upstream_count") or 0))
            upstream_total = fetched.get("upstream_total")
            next_offset = offset + upstream_count
            complete = upstream_count < page_limit
            if upstream_total is not None:
                try:
                    complete = complete or next_offset >= int(upstream_total)
                except (TypeError, ValueError):
                    pass

            checked_at = now_iso()
            get_db().execute(
                """
                INSERT INTO public_data_refresh_state
                (source_id,next_offset,upstream_total,last_mode,cycle_started_at,
                 last_attempt_at,last_success_at,last_error_category,last_result)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(source_id) DO UPDATE SET
                  next_offset=excluded.next_offset,
                  upstream_total=excluded.upstream_total,
                  last_mode=excluded.last_mode,
                  cycle_started_at=excluded.cycle_started_at,
                  last_attempt_at=excluded.last_attempt_at,
                  last_success_at=excluded.last_success_at,
                  last_error_category=NULL,
                  last_result=excluded.last_result
                """,
                (
                    source_id,
                    0 if complete else next_offset,
                    int(upstream_total) if upstream_total is not None else None,
                    mode,
                    checked_at if offset == 0 else state.get("cycle_started_at"),
                    checked_at,
                    checked_at if complete else state.get("last_success_at"),
                    None,
                    "completed" if complete else "page_processed",
                ),
            )
            get_db().commit()
            outcomes.append(
                {
                    "source_id": source_id,
                    "mode": mode,
                    "offset": offset,
                    "next_offset": 0 if complete else next_offset,
                    "page_limit": page_limit,
                    "upstream_count": upstream_count,
                    "upstream_total": upstream_total,
                    "canonical_record_count": int(fetched.get("record_count") or 0),
                    "rejected_count": int(fetched.get("rejected_count") or 0),
                    "complete": bool(complete),
                    "duplicate_batch": bool(ingestion.get("duplicate_batch")),
                    "ingestion_status": ingestion.get("status"),
                }
            )
        except Exception as exc:
            _record_failure(source_id, mode, exc)
            outcomes.append(
                {
                    "source_id": source_id,
                    "mode": mode,
                    "status": "failed",
                    "error_category": type(exc).__name__,
                }
            )

    return {
        "mode": mode,
        "configured_source_count": configured,
        "due_source_count": due_count,
        "processed_count": len(outcomes),
        "outcomes": outcomes,
        "truth_notice": (
            "Automatic public-data refresh handles non-personal directory evidence only. "
            "Applied rows remain external/unverified and non-bookable until separate "
            "provider verification and connectivity evidence exist."
        ),
    }


def public_refresh_snapshot() -> dict:
    ensure_public_refresh_schema()
    rows = get_db().execute(
        "SELECT * FROM public_data_refresh_state ORDER BY source_id"
    ).fetchall()
    states = [dict(row) for row in rows]
    return {
        "states": states,
        "source_count": len(states),
        "failed_count": sum(1 for row in states if row.get("last_result") == "failed"),
        "in_progress_count": sum(1 for row in states if int(row.get("next_offset") or 0) > 0),
    }
