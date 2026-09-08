"""Pilot-grade official/public data ingestion.

Design rules:
- owner-only caller enforced at API boundary/service entry;
- dry-run is the default;
- every batch is checksum-addressed and auditable;
- invalid rows are rejected with row-level reasons;
- official/public facility records are not automatically ZENDOC_VERIFIED;
- ingestion never creates patient/beneficiary/claims data.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from .db import get_db, now_iso
from .geography_graph import geography_write_transaction, link_entity_to_geography, normalize_geography_name, upsert_geography_node
from .geography_resolution import resolve_canonical_geography
from .public_source_registry import get_public_ingestion_source
from .security import assert_owner


ALLOWED_ENTITY_CATEGORIES = {
    "hospital", "clinic", "doctor", "pharmacy", "diagnostic_centre", "laboratory",
    "health_centre", "nursing_home", "blood_bank",
}

ENTITY_CATEGORY_ALIASES = {
    "medical_shop": "pharmacy",
    "medical_store": "pharmacy",
    "chemist": "pharmacy",
    "chemist_shop": "pharmacy",
    "drug_store": "pharmacy",
    "retail_pharmacy": "pharmacy",
    "diagnostic_center": "diagnostic_centre",
    "diagnostic_lab": "diagnostic_centre",
    "pathology_lab": "laboratory",
    "pathology_laboratory": "laboratory",
    "lab": "laboratory",
    "nursinghome": "nursing_home",
    "health_center": "health_centre",
    "phc": "health_centre",
    "primary_health_centre": "health_centre",
    "primary_health_center": "health_centre",
    "chc": "health_centre",
    "community_health_centre": "health_centre",
    "community_health_center": "health_centre",
    "fhc": "health_centre",
    "family_health_centre": "health_centre",
    "family_health_center": "health_centre",
    "sub_centre": "health_centre",
    "sub_center": "health_centre",
    "health_sub_centre": "health_centre",
    "health_sub_center": "health_centre",
}


def ingest_public_records(
    actor: Any,
    *,
    source_id: str,
    ingestion_type: str,
    records: list[dict[str, Any]],
    dry_run: bool = True,
) -> dict:
    assert_owner(actor)
    source = get_public_ingestion_source(source_id)
    if not source:
        raise LookupError(f"Unknown public ingestion source '{source_id}'.")
    ingestion_type = str(ingestion_type or "").strip()
    if ingestion_type not in source["ingestion_types"]:
        raise ValueError(f"Source '{source_id}' does not support ingestion type '{ingestion_type}'.")
    if not isinstance(records, list):
        raise ValueError("records must be a list.")
    if len(records) > 5000:
        raise ValueError("A single ingestion batch may contain at most 5000 records.")

    canonical = json.dumps(records, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    checksum = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    existing = get_db().execute(
        "SELECT * FROM data_ingestion_batches WHERE source_id=? AND ingestion_type=? AND checksum_sha256=? AND dry_run=? ORDER BY id DESC LIMIT 1",
        (source_id, ingestion_type, checksum, 1 if dry_run else 0),
    ).fetchone()
    if existing:
        return _batch_result(dict(existing), duplicate=True)

    if ingestion_type == "geography_nodes":
        preview = _prepare_geography_records(source, records)
        apply_fn = _apply_geography_records
    elif ingestion_type == "public_healthcare_entities":
        preview = _prepare_healthcare_entities(source, records)
        apply_fn = _apply_healthcare_entities
    else:
        raise ValueError("Unsupported ingestion type.")

    batch = _create_batch(
        actor=actor,
        source_id=source_id,
        ingestion_type=ingestion_type,
        checksum=checksum,
        dry_run=dry_run,
        preview=preview,
    )
    if dry_run:
        return _batch_result(batch, preview=preview)

    applied = apply_fn(source, preview["accepted"])
    completed = _complete_batch(batch["id"], preview, applied)
    return _batch_result(completed, preview=preview, applied=applied)


def list_ingestion_batches(actor: Any, limit: int = 50) -> list[dict]:
    assert_owner(actor)
    limit = max(1, min(int(limit or 50), 200))
    rows = get_db().execute(
        "SELECT * FROM data_ingestion_batches ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_batch_result(dict(row)) for row in rows]


def search_public_healthcare_entities(
    *,
    category: str | None = None,
    specialty: str | None = None,
    location: str | None = None,
    limit: int = 25,
) -> list[dict]:
    db = get_db()
    limit = max(1, min(int(limit or 25), 100))
    clauses = ["active=1"]
    params: list[Any] = []
    if category:
        category = str(category).strip().lower()
        if category == "diagnostic_centre":
            clauses.append("category IN ('diagnostic_centre','laboratory')")
        else:
            clauses.append("category=?")
            params.append(category)
    if specialty:
        clauses.append("LOWER(COALESCE(specialty,'')) LIKE LOWER(?)")
        params.append(f"%{str(specialty).strip()}%")
    if location:
        value = f"%{str(location).strip()}%"
        clauses.append(
            "(LOWER(COALESCE(city,'')) LIKE LOWER(?) OR LOWER(COALESCE(district,'')) LIKE LOWER(?) "
            "OR LOWER(COALESCE(state,'')) LIKE LOWER(?) OR LOWER(COALESCE(address,'')) LIKE LOWER(?))"
        )
        params.extend([value, value, value, value])
    params.append(limit)
    rows = db.execute(
        f"""
        SELECT * FROM public_healthcare_entities
        WHERE {' AND '.join(clauses)}
        ORDER BY CASE source_trust WHEN 'AUTHORITATIVE_REGISTRY' THEN 0 ELSE 1 END,
                 updated_at DESC, name ASC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [_public_entity(dict(row)) for row in rows]


def _prepare_geography_records(source: dict, records: list[dict]) -> dict:
    accepted = []
    rejected = []
    seen_ids = set()
    for index, raw in enumerate(records):
        row = dict(raw or {})
        try:
            source_record_id = _required(row, "source_record_id")
            node_type = _required(row, "node_type").lower()
            name = _required(row, "name")
            if source_record_id in seen_ids:
                raise ValueError("duplicate source_record_id inside batch")
            seen_ids.add(source_record_id)
            if node_type not in {
                "country","state","district","subdivision","block","municipality",
                "panchayat","city","town","village","locality",
            }:
                raise ValueError("unsupported node_type")
            accepted.append({
                "row_number": index + 1,
                "source_record_id": source_record_id,
                "parent_source_record_id": _optional(row, "parent_source_record_id"),
                "node_type": node_type,
                "name": name,
                "latitude": _coordinate(row.get("latitude"), -90, 90, "latitude"),
                "longitude": _coordinate(row.get("longitude"), -180, 180, "longitude"),
                "freshness_at": _optional(row, "freshness_at"),
                "verified": bool(row.get("verified", True)),
                "source": source["source_id"],
            })
        except (TypeError, ValueError) as exc:
            rejected.append({"row_number": index + 1, "reason": str(exc), "record": row})
    return {"accepted": accepted, "rejected": rejected, "record_count": len(records)}


def _apply_geography_records(source: dict, records: list[dict]) -> dict:
    with geography_write_transaction():
        pending = list(records)
        resolved: dict[str, int] = {}
        applied = []
        rejected = []
        db = get_db()

        # Existing source refs may satisfy parents across multiple batches.
        for row in db.execute(
            "SELECT id, source_ref FROM geography_nodes WHERE source=? AND source_ref IS NOT NULL",
            (source["source_id"],),
        ).fetchall():
            resolved[str(row["source_ref"])] = int(row["id"])

        for _pass in range(20):
            if not pending:
                break
            progress = False
            remaining = []
            for row in pending:
                parent_ref = row.get("parent_source_record_id")
                if parent_ref and parent_ref not in resolved:
                    remaining.append(row)
                    continue
                try:
                    node = upsert_geography_node(
                        node_type=row["node_type"],
                        name=row["name"],
                        source=source["source_id"],
                        source_ref=row["source_record_id"],
                        parent_id=resolved.get(parent_ref) if parent_ref else None,
                        latitude=row.get("latitude"),
                        longitude=row.get("longitude"),
                        verified=row.get("verified", True),
                        freshness_at=row.get("freshness_at"),
                    )
                    resolved[row["source_record_id"]] = int(node["id"])
                    applied.append({"row_number": row["row_number"], "node_id": node["id"], "source_record_id": row["source_record_id"]})
                    progress = True
                except (LookupError, TypeError, ValueError) as exc:
                    rejected.append({"row_number": row["row_number"], "reason": str(exc), "source_record_id": row["source_record_id"]})
            pending = remaining
            if not progress:
                break

        for row in pending:
            rejected.append({
                "row_number": row["row_number"],
                "reason": f"unresolved parent_source_record_id '{row.get('parent_source_record_id')}'",
                "source_record_id": row["source_record_id"],
            })
        return {"applied": applied, "rejected_during_apply": rejected}


def _prepare_healthcare_entities(source: dict, records: list[dict]) -> dict:
    accepted = []
    rejected = []
    seen_ids = set()
    for index, raw in enumerate(records):
        row = dict(raw or {})
        try:
            source_record_id = _required(row, "source_record_id")
            name = _required(row, "name")
            source_category = _required(row, "category")
            normalized_category = source_category.lower().replace("-", "_").replace(" ", "_")
            category = ENTITY_CATEGORY_ALIASES.get(normalized_category, normalized_category)
            if category not in ALLOWED_ENTITY_CATEGORIES:
                raise ValueError("unsupported healthcare category")
            if source_record_id in seen_ids:
                raise ValueError("duplicate source_record_id inside batch")
            seen_ids.add(source_record_id)
            accepted.append({
                "row_number": index + 1,
                "source_record_id": source_record_id,
                "name": name,
                "category": category,
                "specialty": _optional(row, "specialty"),
                "address": _optional(row, "address"),
                "city": _optional(row, "city"),
                "district": _optional(row, "district"),
                "state": _optional(row, "state"),
                "subdistrict": _optional(row, "subdistrict"),
                "block": _optional(row, "block"),
                "village": _optional(row, "village"),
                "locality": _optional(row, "locality"),
                "postal_code": _optional(row, "postal_code"),
                "latitude": _coordinate(row.get("latitude"), -90, 90, "latitude"),
                "longitude": _coordinate(row.get("longitude"), -180, 180, "longitude"),
                "public_phone": _optional(row, "public_phone"),
                "public_email": _optional(row, "public_email"),
                "website": _optional(row, "website"),
                "freshness_at": _optional(row, "freshness_at"),
                "geography_source": _optional(row, "geography_source"),
                "geography_source_record_id": _optional(row, "geography_source_record_id"),
                "metadata": {
                    **(row.get("metadata") if isinstance(row.get("metadata"), dict) else {}),
                    **({"source_facility_category": source_category} if category != normalized_category else {}),
                },
            })
        except (TypeError, ValueError) as exc:
            rejected.append({"row_number": index + 1, "reason": str(exc), "record": row})
    return {"accepted": accepted, "rejected": rejected, "record_count": len(records)}


def _apply_healthcare_entities(source: dict, records: list[dict]) -> dict:
    db = get_db()
    now = now_iso()
    applied = []
    rejected = []
    inserted = updated = unchanged = linked = unresolved = ambiguous = 0

    with geography_write_transaction():
        for row in records:
            geography_node_id = None
            geography_source = row.get("geography_source") or "lgd"
            geography_source_record_id = row.get("geography_source_record_id")
            resolution = resolve_canonical_geography(
                source=geography_source,
                source_ref=geography_source_record_id,
                state=row.get("state"),
                district=row.get("district"),
                subdistrict=row.get("subdistrict"),
                block=row.get("block"),
                village=row.get("village"),
                locality=row.get("locality"),
            )
            if geography_source_record_id and resolution["status"] != "MATCHED":
                rejected.append({
                    "row_number": row["row_number"],
                    "reason": (
                        f"canonical geography not found for source={geography_source} "
                        f"source_ref={geography_source_record_id}"
                    ),
                    "source_record_id": row["source_record_id"],
                })
                continue
            if resolution["status"] == "MATCHED":
                geography_node_id = int(resolution["geography_node_id"])
            elif resolution["status"] == "AMBIGUOUS":
                ambiguous += 1
            elif resolution["status"] == "NOT_FOUND":
                unresolved += 1

            metadata_json = json.dumps(row["metadata"], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            existing = db.execute(
                "SELECT * FROM public_healthcare_entities WHERE source_id=? AND source_record_id=?",
                (source["source_id"], row["source_record_id"]),
            ).fetchone()
            values = (
                row["category"], row["name"], row["specialty"], row["address"], row["city"],
                row["district"], row["state"], row["postal_code"], row["latitude"], row["longitude"],
                row["public_phone"], row["public_email"], row["website"], source["trust_level"],
                row["freshness_at"], metadata_json,
            )
            if existing:
                current = (
                    existing["category"], existing["name"], existing["specialty"], existing["address"],
                    existing["city"], existing["district"], existing["state"], existing["postal_code"],
                    existing["latitude"], existing["longitude"], existing["public_phone"], existing["public_email"],
                    existing["website"], existing["source_trust"], existing["freshness_at"], existing["metadata_json"],
                )
                if current == values and int(existing["active"] or 0) == 1:
                    entity_id = existing["id"]
                    disposition = "unchanged"
                    unchanged += 1
                else:
                    db.execute(
                        """
                        UPDATE public_healthcare_entities
                        SET category=?,name=?,specialty=?,address=?,city=?,district=?,state=?,postal_code=?,
                            latitude=?,longitude=?,public_phone=?,public_email=?,website=?,source_trust=?,
                            freshness_at=?,metadata_json=?,active=1,updated_at=?
                        WHERE id=?
                        """,
                        (*values, now, existing["id"]),
                    )
                    entity_id = existing["id"]
                    disposition = "updated"
                    updated += 1
            else:
                cursor = db.execute(
                    """
                    INSERT INTO public_healthcare_entities
                    (source_id,source_record_id,category,name,specialty,address,city,district,state,postal_code,
                     latitude,longitude,public_phone,public_email,website,source_trust,zendoc_verification_status,
                     booking_connectivity,freshness_at,metadata_json,active,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'not_verified','not_connected',?,?,1,?,?)
                    """,
                    (
                        source["source_id"], row["source_record_id"], row["category"], row["name"], row["specialty"],
                        row["address"], row["city"], row["district"], row["state"], row["postal_code"],
                        row["latitude"], row["longitude"], row["public_phone"], row["public_email"], row["website"],
                        source["trust_level"], row["freshness_at"], metadata_json, now, now,
                    ),
                )
                entity_id = cursor.lastrowid
                disposition = "inserted"
                inserted += 1

            if geography_node_id is not None:
                link_entity_to_geography(
                    geography_node_id=geography_node_id,
                    entity_type=row["category"],
                    entity_id=entity_id,
                    source=source["source_id"],
                    verification_state="EXTERNAL_UNVERIFIED",
                    freshness_at=row.get("freshness_at"),
                    metadata={
                        "source_record_id": row["source_record_id"],
                        "canonical_geography_source": geography_source,
                        "canonical_geography_source_record_id": geography_source_record_id,
                        "resolution_method": resolution.get("resolution_method"),
                        "matched_level": resolution.get("matched_level"),
                    },
                )
                linked += 1

            applied.append({
                "row_number": row["row_number"],
                "entity_id": entity_id,
                "source_record_id": row["source_record_id"],
                "disposition": disposition,
            })

    return {
        "applied": applied,
        "rejected_during_apply": rejected,
        "inserted_count": inserted,
        "updated_count": updated,
        "unchanged_count": unchanged,
        "geography_linked_count": linked,
        "geography_unresolved_count": unresolved,
        "geography_ambiguous_count": ambiguous,
    }


def _create_batch(*, actor: Any, source_id: str, ingestion_type: str, checksum: str, dry_run: bool, preview: dict) -> dict:
    db = get_db()
    uid = f"ingest_{uuid.uuid4().hex[:20]}"
    summary = {
        "preview_rejected": preview["rejected"][:100],
        "accepted_preview_count": len(preview["accepted"]),
    }
    cursor = db.execute(
        """
        INSERT INTO data_ingestion_batches
        (batch_uid,source_id,ingestion_type,checksum_sha256,record_count,accepted_count,rejected_count,
         dry_run,status,requested_by,summary_json,created_at,completed_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            uid, source_id, ingestion_type, checksum, preview["record_count"],
            len(preview["accepted"]), len(preview["rejected"]), 1 if dry_run else 0,
            "previewed" if dry_run else "running", _user_id(actor),
            json.dumps(summary, sort_keys=True, ensure_ascii=False, separators=(",", ":")),
            now_iso(), now_iso() if dry_run else None,
        ),
    )
    db.commit()
    return dict(db.execute("SELECT * FROM data_ingestion_batches WHERE id=?", (cursor.lastrowid,)).fetchone())


def _complete_batch(batch_id: int, preview: dict, applied: dict) -> dict:
    apply_rejected = applied.get("rejected_during_apply", [])
    accepted_count = len(applied.get("applied", []))
    rejected_count = len(preview["rejected"]) + len(apply_rejected)
    summary = {
        "preview_rejected": preview["rejected"][:100],
        "apply_rejected": apply_rejected[:100],
        "applied": applied.get("applied", [])[:100],
        "inserted_count": int(applied.get("inserted_count", 0) or 0),
        "updated_count": int(applied.get("updated_count", 0) or 0),
        "unchanged_count": int(applied.get("unchanged_count", 0) or 0),
        "geography_linked_count": int(applied.get("geography_linked_count", 0) or 0),
        "geography_unresolved_count": int(applied.get("geography_unresolved_count", 0) or 0),
        "geography_ambiguous_count": int(applied.get("geography_ambiguous_count", 0) or 0),
    }
    db = get_db()
    db.execute(
        """
        UPDATE data_ingestion_batches
        SET accepted_count=?,rejected_count=?,status='completed',summary_json=?,completed_at=?
        WHERE id=?
        """,
        (
            accepted_count, rejected_count,
            json.dumps(summary, sort_keys=True, ensure_ascii=False, separators=(",", ":")),
            now_iso(), int(batch_id),
        ),
    )
    db.commit()
    return dict(db.execute("SELECT * FROM data_ingestion_batches WHERE id=?", (int(batch_id),)).fetchone())


def _batch_result(batch: dict, *, duplicate: bool = False, preview: dict | None = None, applied: dict | None = None) -> dict:
    result = dict(batch)
    try:
        result["summary"] = json.loads(result.pop("summary_json") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        result["summary"] = {}
    result["duplicate_batch"] = duplicate
    result["dry_run"] = bool(result["dry_run"])
    if preview is not None:
        result["preview"] = {
            "record_count": preview["record_count"],
            "accepted_count": len(preview["accepted"]),
            "rejected_count": len(preview["rejected"]),
            "rejected": preview["rejected"][:100],
        }
    if applied is not None:
        result["applied"] = applied
    return result


def _public_entity(row: dict) -> dict:
    try:
        metadata = json.loads(row.pop("metadata_json") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        metadata = {}
    row["metadata"] = metadata
    row["source"] = row["source_id"]
    row["verification_status"] = row["zendoc_verification_status"]
    row["bookable_in_zendoc"] = row["booking_connectivity"] == "connected"
    row["source_disclaimer"] = (
        "Official/public directory record. This does not mean ZENDOC verified the provider, "
        "that a live slot exists, or that booking is connected."
    )
    return row


def _required(row: dict, key: str) -> str:
    value = str(row.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    if len(value) > 500:
        raise ValueError(f"{key} is too long")
    return value


def _optional(row: dict, key: str) -> str | None:
    value = str(row.get(key) or "").strip()
    return value[:1000] or None


def _coordinate(value: Any, minimum: float, maximum: float, label: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not minimum <= number <= maximum:
        raise ValueError(f"{label} is out of range")
    return number


def _user_id(actor: Any) -> int | None:
    try:
        return int(actor["id"])
    except Exception:
        return None
