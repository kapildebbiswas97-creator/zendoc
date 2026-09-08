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


def record_product_activity(user: Any, *, event_type: str) -> int:
    """Record a privacy-safe non-clinical product activity event."""
    user_id = int(user["id"])
    clean_event = str(event_type or "").strip().lower()
    allowed = {
        "session_login",
        "healthcare_search",
        "provider_profile_update",
        "appointment_requested",
        "finder_feedback",
    }
    if clean_event not in allowed:
        raise ValueError("Unsupported product activity event type.")
    cursor = get_db().execute(
        """
        INSERT INTO product_analytics_events
        (user_id,event_type,category,geography_node_id,location_hash,result_count,useful_result,source_tiers_json,metadata_json,created_at)
        VALUES (?,?,NULL,NULL,NULL,0,0,'{}','{}',?)
        """,
        (user_id, clean_event, now_iso()),
    )
    return int(cursor.lastrowid)


def record_finder_search(
    user: Any,
    *,
    category: str,
    location: str | None,
    result_count: int,
    source_tiers: dict[str, Any] | None = None,
) -> int:
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
    cursor = get_db().execute(
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
    return int(cursor.lastrowid)


def submit_finder_feedback(
    user: Any,
    *,
    analytics_event_id: int,
    helpful: bool,
    reason_code: str | None = None,
) -> dict:
    user_id = int(user["id"])
    db = get_db()
    event = db.execute(
        """
        SELECT id,user_id,event_type FROM product_analytics_events
        WHERE id=? AND event_type='healthcare_search'
        """,
        (int(analytics_event_id),),
    ).fetchone()
    if not event:
        raise LookupError("Healthcare search event not found.")
    if event["user_id"] is not None and int(event["user_id"]) != user_id:
        raise PermissionError("You may only rate your own healthcare search.")

    clean_reason = str(reason_code or "").strip().lower()[:80] or None
    now = now_iso()
    existing = db.execute(
        "SELECT id FROM product_feedback WHERE analytics_event_id=? AND user_id=?",
        (int(analytics_event_id), user_id),
    ).fetchone()
    if existing:
        db.execute(
            "UPDATE product_feedback SET helpful=?,reason_code=?,created_at=? WHERE id=?",
            (1 if helpful else 0, clean_reason, now, int(existing["id"])),
        )
        feedback_id = int(existing["id"])
    else:
        cursor = db.execute(
            """
            INSERT INTO product_feedback
            (analytics_event_id,user_id,helpful,reason_code,created_at)
            VALUES (?,?,?,?,?)
            """,
            (int(analytics_event_id), user_id, 1 if helpful else 0, clean_reason, now),
        )
        feedback_id = int(cursor.lastrowid)
    db.commit()
    row = db.execute("SELECT * FROM product_feedback WHERE id=?", (feedback_id,)).fetchone()
    return dict(row)


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

    feedback_rows = db.execute(
        """
        SELECT f.helpful,f.reason_code
        FROM product_feedback f
        JOIN product_analytics_events e ON e.id=f.analytics_event_id
        WHERE e.event_type='healthcare_search' AND f.created_at>=?
        """,
        (cutoff,),
    ).fetchall()
    feedback_total = len(feedback_rows)
    helpful_feedback = sum(int(row["helpful"] or 0) for row in feedback_rows)
    reason_counts = Counter(
        str(row["reason_code"])
        for row in feedback_rows
        if row["reason_code"]
    )

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
        "feedback_response_count": feedback_total,
        "helpful_feedback_count": helpful_feedback,
        "not_helpful_feedback_count": feedback_total - helpful_feedback,
        "helpful_feedback_rate": round(helpful_feedback / feedback_total, 4) if feedback_total else None,
        "feedback_reason_counts": dict(reason_counts),
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


def retention_metrics(actor: Any, *, as_of: str | None = None) -> dict:
    """Return exact-day D7/D30 retention for patient product activity.

    Cohort date is the date of a patient's first recorded privacy-safe product
    activity. D7 means activity on cohort_date + 7 days; D30 means activity on
    cohort_date + 30 days. Users too young for a window are excluded from that
    denominator instead of being counted as churned.
    """
    assert_owner(actor)
    db = get_db()
    now = _parse_timestamp(as_of) if as_of else datetime.now(timezone.utc)

    rows = db.execute(
        """
        SELECT e.user_id,e.created_at
        FROM product_analytics_events e
        JOIN users u ON u.id=e.user_id
        WHERE e.user_id IS NOT NULL AND u.role='patient' AND u.active=1
          AND e.event_type IN ('session_login','healthcare_search','appointment_requested','finder_feedback')
        ORDER BY e.user_id,e.created_at
        """
    ).fetchall()

    activity_dates: dict[int, set] = defaultdict(set)
    for row in rows:
        try:
            activity_dates[int(row["user_id"])].add(_parse_timestamp(row["created_at"]).date())
        except (TypeError, ValueError):
            continue

    def _window(day_offset: int) -> dict:
        eligible = retained = 0
        cohorts = []
        for user_id, dates in activity_dates.items():
            if not dates:
                continue
            first_date = min(dates)
            target_date = first_date + timedelta(days=day_offset)
            if target_date > now.date():
                continue
            eligible += 1
            did_return = target_date in dates
            retained += 1 if did_return else 0
            cohorts.append({
                "user_id": user_id,
                "cohort_date": first_date.isoformat(),
                "target_date": target_date.isoformat(),
                "retained": did_return,
            })
        return {
            "eligible_users": eligible,
            "retained_users": retained,
            "retention_rate": round(retained / eligible, 4) if eligible else None,
            "definition": f"Exact-day D{day_offset}: activity on first activity date + {day_offset} days.",
            "cohort_rows": cohorts[:200],
        }

    return {
        "patient_users_with_recorded_activity": len(activity_dates),
        "d7": _window(7),
        "d30": _window(30),
        "truth_notice": (
            "Retention is calculated only from privacy-safe product activity currently recorded by ZENDOC. "
            "Users without recorded product activity are not included in the cohort denominator."
        ),
    }


def care_journey_conversion(actor: Any, *, days: int = 30) -> dict:
    assert_owner(actor)
    days = max(1, min(int(days or 30), 365))
    cutoff = _cutoff_iso(days)
    db = get_db()

    journeys = db.execute(
        """
        SELECT id,state,status,created_at
        FROM care_journeys
        WHERE created_at>=?
        ORDER BY created_at
        """,
        (cutoff,),
    ).fetchall()
    journey_ids = [int(row["id"]) for row in journeys]
    states_by_journey: dict[int, set[str]] = defaultdict(set)
    for row in journeys:
        states_by_journey[int(row["id"])].add(str(row["state"]))

    if journey_ids:
        placeholders = ",".join("?" for _ in journey_ids)
        events = db.execute(
            f"SELECT journey_id,state FROM care_journey_events WHERE journey_id IN ({placeholders})",
            journey_ids,
        ).fetchall()
        for row in events:
            states_by_journey[int(row["journey_id"])].add(str(row["state"]))

    stages = [
        ("started", {"NEW", "CONTEXT_READY", "WAITING_INFORMATION", "PROVIDER_SEARCH", "WAITING_USER_SELECTION",
                     "APPOINTMENT_STAGED", "WAITING_PROVIDER", "CONSULTATION", "PRESCRIPTION_RECEIVED",
                     "DIAGNOSTICS_REQUIRED", "CAREFIN_CHECK", "FULFILMENT", "FOLLOW_UP", "COMPLETED", "BLOCKED", "WAITING_HUMAN"}),
        ("context_ready", {"CONTEXT_READY", "PROVIDER_SEARCH", "WAITING_USER_SELECTION", "APPOINTMENT_STAGED",
                           "WAITING_PROVIDER", "CONSULTATION", "PRESCRIPTION_RECEIVED", "DIAGNOSTICS_REQUIRED",
                           "CAREFIN_CHECK", "FULFILMENT", "FOLLOW_UP", "COMPLETED"}),
        ("provider_search", {"PROVIDER_SEARCH", "WAITING_USER_SELECTION", "APPOINTMENT_STAGED", "WAITING_PROVIDER",
                             "CONSULTATION", "PRESCRIPTION_RECEIVED", "DIAGNOSTICS_REQUIRED", "CAREFIN_CHECK",
                             "FULFILMENT", "FOLLOW_UP", "COMPLETED"}),
        ("appointment_staged", {"APPOINTMENT_STAGED", "WAITING_PROVIDER", "CONSULTATION", "PRESCRIPTION_RECEIVED",
                                "DIAGNOSTICS_REQUIRED", "CAREFIN_CHECK", "FULFILMENT", "FOLLOW_UP", "COMPLETED"}),
        ("consultation", {"CONSULTATION", "PRESCRIPTION_RECEIVED", "DIAGNOSTICS_REQUIRED", "CAREFIN_CHECK",
                          "FULFILMENT", "FOLLOW_UP", "COMPLETED"}),
        ("follow_up", {"FOLLOW_UP", "COMPLETED"}),
        ("completed", {"COMPLETED"}),
    ]

    total = len(journeys)
    stage_rows = []
    for name, qualifying in stages:
        count = sum(1 for jid in journey_ids if states_by_journey[jid] & qualifying)
        stage_rows.append({
            "stage": name,
            "journey_count": count,
            "conversion_from_started": round(count / total, 4) if total else None,
        })

    blocked = sum(1 for jid in journey_ids if "BLOCKED" in states_by_journey[jid])
    waiting_human = sum(1 for jid in journey_ids if "WAITING_HUMAN" in states_by_journey[jid])

    return {
        "window_days": days,
        "started_journeys": total,
        "stages": stage_rows,
        "blocked_journeys": blocked,
        "waiting_human_journeys": waiting_human,
        "truth_notice": (
            "This funnel measures workflow states actually persisted in ZENDOC. A staged appointment is not a completed "
            "appointment, and COMPLETED means the care-journey workflow reached its terminal completed state."
        ),
    }


def provider_onboarding_funnel(actor: Any, *, days: int = 90) -> dict:
    assert_owner(actor)
    days = max(1, min(int(days or 90), 3650))
    cutoff = _cutoff_iso(days)
    db = get_db()

    profiles = db.execute(
        """
        SELECT p.*,u.role,u.active
        FROM provider_profiles p
        JOIN users u ON u.id=p.user_id
        WHERE p.created_at>=? AND u.active=1
        ORDER BY p.created_at
        """,
        (cutoff,),
    ).fetchall()
    profile_ids = [int(row["id"]) for row in profiles]
    total = len(profiles)

    evidence_submitted = set()
    evidence_verified = set()
    schedule_profiles = set()
    claim_submitted = set()
    claim_approved = set()
    patient_interaction = set()

    if profile_ids:
        placeholders = ",".join("?" for _ in profile_ids)
        for row in db.execute(
            f"SELECT provider_profile_id,status FROM provider_verification_evidence WHERE provider_profile_id IN ({placeholders})",
            profile_ids,
        ).fetchall():
            pid = int(row["provider_profile_id"])
            evidence_submitted.add(pid)
            if row["status"] == "verified":
                evidence_verified.add(pid)

        for row in db.execute(
            f"SELECT DISTINCT provider_profile_id FROM provider_schedules WHERE provider_profile_id IN ({placeholders}) AND active=1",
            profile_ids,
        ).fetchall():
            schedule_profiles.add(int(row["provider_profile_id"]))

        for row in db.execute(
            f"SELECT provider_profile_id,status FROM public_entity_claims WHERE provider_profile_id IN ({placeholders})",
            profile_ids,
        ).fetchall():
            pid = int(row["provider_profile_id"])
            claim_submitted.add(pid)
            if row["status"] == "approved":
                claim_approved.add(pid)

        for row in db.execute(
            f"SELECT DISTINCT provider_profile_id FROM appointments WHERE provider_profile_id IN ({placeholders})",
            profile_ids,
        ).fetchall():
            if row["provider_profile_id"] is not None:
                patient_interaction.add(int(row["provider_profile_id"]))

    complete_profiles = set()
    verified_profiles = set()
    for row in profiles:
        pid = int(row["id"])
        role = str(row["role"])
        required = {
            "doctor": ("specialty", "qualifications", "license_identifier", "address", "city", "state", "public_phone"),
            "hospital": ("organization", "license_identifier", "address", "city", "state", "public_phone"),
            "pharmacy": ("organization", "license_identifier", "address", "city", "state", "public_phone"),
        }.get(role, ("address", "city", "state", "public_phone"))
        if all(str(row[field] or "").strip() for field in required):
            complete_profiles.add(pid)
        if row["verification_status"] == "verified":
            verified_profiles.add(pid)

    stages = [
        ("profile_created", set(profile_ids)),
        ("profile_complete", complete_profiles),
        ("evidence_submitted", evidence_submitted),
        ("evidence_verified", evidence_verified),
        ("provider_verified", verified_profiles),
        ("schedule_published", schedule_profiles),
        ("listing_claim_submitted", claim_submitted),
        ("listing_claim_approved", claim_approved),
        ("patient_interaction", patient_interaction),
    ]

    return {
        "window_days": days,
        "provider_profiles_created": total,
        "stages": [
            {
                "stage": name,
                "provider_count": len(ids),
                "conversion_from_created": round(len(ids) / total, 4) if total else None,
            }
            for name, ids in stages
        ],
        "truth_notice": (
            "Stages are independent observed milestones, not a forced linear sequence for every provider type. "
            "For example, pharmacies may not use appointment schedules."
        ),
    }


def _parse_timestamp(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("timestamp required")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
