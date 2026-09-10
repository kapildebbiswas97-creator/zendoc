"""Bind public-data imports to exact downloaded source snapshots.

This module is additive to the existing pilot-grade importer.  It gives ZENDOC
an auditable path for the workflow recommended for production data loading:

download exact public/official artifact -> hash it -> record provenance ->
preview normalized rows -> explicitly apply the exact same snapshot.

The raw dataset itself is intentionally not stored in Git by this module.
Operators should retain permitted source artifacts in controlled raw/object
storage and record a non-secret ``storage_ref`` in the manifest when useful.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlparse

from .db import get_db
from .public_data_ingestion import ingest_public_records
from .public_source_registry import get_public_ingestion_source
from .security import assert_owner


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FORMAT_RE = re.compile(r"^[a-z0-9][a-z0-9.+_-]{0,31}$")
SENSITIVE_QUERY_MARKERS = ("key", "token", "secret", "signature", "credential", "password")
USAGE_BASES = {
    "official_public_download",
    "open_data_license",
    "authorized_export",
    "manual_public_snapshot",
}


def normalize_dataset_snapshot(source_id: str, manifest: dict[str, Any]) -> dict:
    """Validate and canonicalize immutable public-dataset provenance metadata."""
    source = get_public_ingestion_source(str(source_id or "").strip())
    if not source:
        raise LookupError(f"Unknown public ingestion source '{source_id}'.")
    if not isinstance(manifest, dict):
        raise ValueError("dataset_snapshot must be an object.")

    declared_source = str(manifest.get("source_id") or source["source_id"]).strip()
    if declared_source != source["source_id"]:
        raise ValueError("dataset_snapshot.source_id must match the ingestion source_id.")

    source_url = _public_url(manifest.get("source_url"), "dataset_snapshot.source_url")
    retrieved_at = _aware_iso(manifest.get("retrieved_at"), "dataset_snapshot.retrieved_at")
    published_at = _optional_iso(manifest.get("published_at"), "dataset_snapshot.published_at")
    dataset_version = _clean_optional(manifest.get("dataset_version"), 200)
    if not dataset_version and not published_at:
        raise ValueError("dataset_snapshot requires dataset_version or published_at.")

    file_sha256 = str(manifest.get("file_sha256") or "").strip().lower()
    if not SHA256_RE.fullmatch(file_sha256):
        raise ValueError("dataset_snapshot.file_sha256 must be exactly 64 hexadecimal characters.")

    file_name = _clean_optional(manifest.get("file_name"), 255)
    file_format = str(manifest.get("file_format") or "").strip().lower()
    if not file_format or not FORMAT_RE.fullmatch(file_format):
        raise ValueError("dataset_snapshot.file_format is required and must be a simple format label such as csv, json, xlsx, zip, or pdf.")

    file_size = manifest.get("file_size_bytes")
    if file_size in (None, ""):
        file_size_bytes = None
    else:
        try:
            file_size_bytes = int(file_size)
        except (TypeError, ValueError) as exc:
            raise ValueError("dataset_snapshot.file_size_bytes must be an integer.") from exc
        if file_size_bytes < 0:
            raise ValueError("dataset_snapshot.file_size_bytes cannot be negative.")

    usage_basis = str(manifest.get("usage_basis") or "").strip().lower()
    if usage_basis not in USAGE_BASES:
        raise ValueError(
            "dataset_snapshot.usage_basis must be one of: " + ", ".join(sorted(USAGE_BASES))
        )
    license_or_terms = _clean_required(manifest.get("license_or_terms"), "dataset_snapshot.license_or_terms", 500)
    license_url = None
    if manifest.get("license_url") not in (None, ""):
        license_url = _public_url(manifest.get("license_url"), "dataset_snapshot.license_url")

    storage_ref = _clean_optional(manifest.get("storage_ref"), 500)
    if storage_ref and any(marker in storage_ref.casefold() for marker in ("password=", "token=", "secret=", "api_key=", "apikey=")):
        raise ValueError("dataset_snapshot.storage_ref must not contain credentials or secret tokens.")

    normalized = {
        "source_id": source["source_id"],
        "source_name": source["name"],
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "published_at": published_at,
        "dataset_version": dataset_version,
        "file_name": file_name,
        "file_format": file_format,
        "file_size_bytes": file_size_bytes,
        "file_sha256": file_sha256,
        "usage_basis": usage_basis,
        "license_or_terms": license_or_terms,
        "license_url": license_url,
        "storage_ref": storage_ref,
    }
    canonical = json.dumps(normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    manifest_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    normalized["manifest_sha256"] = manifest_sha256
    normalized["snapshot_uid"] = f"snapshot_{manifest_sha256[:20]}"
    return normalized


def ingest_public_snapshot(
    actor: Any,
    *,
    source_id: str,
    ingestion_type: str,
    records: list[dict[str, Any]],
    dataset_snapshot: dict[str, Any],
    dry_run: bool = True,
    preview_batch_uid: str | None = None,
) -> dict:
    """Preview/apply records while binding the batch to one immutable snapshot.

    An apply requires a prior preview of the same source, ingestion type,
    normalized records, and exact snapshot manifest.  Existing non-snapshot
    importer callers remain untouched.
    """
    assert_owner(actor)
    manifest = normalize_dataset_snapshot(source_id, dataset_snapshot)
    if not isinstance(records, list):
        raise ValueError("records must be a list.")

    bound_records = _bind_records(records, ingestion_type=ingestion_type, manifest=manifest)
    checksum = _records_checksum(bound_records)

    if not dry_run:
        preview_uid = str(preview_batch_uid or "").strip()
        if not preview_uid:
            raise ValueError("preview_batch_uid is required before applying a dataset snapshot.")
        _assert_matching_preview(
            preview_uid,
            source_id=source_id,
            ingestion_type=ingestion_type,
            checksum=checksum,
            manifest=manifest,
        )

    result = ingest_public_records(
        actor,
        source_id=source_id,
        ingestion_type=ingestion_type,
        records=bound_records,
        dry_run=dry_run,
    )
    _persist_snapshot_on_batch(
        int(result["id"]),
        manifest=manifest,
        preview_batch_uid=None if dry_run else str(preview_batch_uid),
    )
    result.setdefault("summary", {})["dataset_snapshot"] = manifest
    if not dry_run:
        result["summary"]["source_snapshot_preview_batch_uid"] = str(preview_batch_uid)
    result["dataset_snapshot"] = manifest
    result["snapshot_bound"] = True
    return result


def _bind_records(records: list[Any], *, ingestion_type: str, manifest: dict) -> list[dict]:
    binding = manifest["manifest_sha256"]
    bound: list[dict] = []
    for raw in records:
        if isinstance(raw, dict):
            item = dict(raw)
        else:
            # Keep malformed rows visible to the normal validation path while
            # still binding their batch identity to the source snapshot.
            item = {"_zendoc_invalid_source_record": raw}
        item["_zendoc_snapshot_binding"] = binding
        if str(ingestion_type or "").strip() == "public_healthcare_entities":
            original_metadata = item.get("metadata")
            if isinstance(original_metadata, dict):
                metadata = dict(original_metadata)
            elif original_metadata in (None, ""):
                metadata = {}
            else:
                metadata = {"source_metadata": original_metadata}
            metadata["_zendoc_source_snapshot"] = {
                "snapshot_uid": manifest["snapshot_uid"],
                "manifest_sha256": manifest["manifest_sha256"],
                "file_sha256": manifest["file_sha256"],
                "dataset_version": manifest.get("dataset_version"),
                "published_at": manifest.get("published_at"),
                "retrieved_at": manifest["retrieved_at"],
            }
            item["metadata"] = metadata
        bound.append(item)
    return bound


def _records_checksum(records: list[dict]) -> str:
    canonical = json.dumps(records, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _assert_matching_preview(
    preview_batch_uid: str,
    *,
    source_id: str,
    ingestion_type: str,
    checksum: str,
    manifest: dict,
) -> None:
    row = get_db().execute(
        """
        SELECT * FROM data_ingestion_batches
        WHERE batch_uid=? AND source_id=? AND ingestion_type=? AND checksum_sha256=? AND dry_run=1
        LIMIT 1
        """,
        (preview_batch_uid, source_id, str(ingestion_type or "").strip(), checksum),
    ).fetchone()
    if not row:
        raise ValueError("preview_batch_uid does not match this exact dataset snapshot and record payload.")
    try:
        summary = json.loads(row["summary_json"] or "{}")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("The referenced preview batch has invalid provenance metadata.") from exc
    preview_manifest = summary.get("dataset_snapshot") or {}
    if preview_manifest.get("manifest_sha256") != manifest["manifest_sha256"]:
        raise ValueError("preview_batch_uid was created from a different dataset snapshot manifest.")


def _persist_snapshot_on_batch(batch_id: int, *, manifest: dict, preview_batch_uid: str | None) -> None:
    db = get_db()
    row = db.execute("SELECT summary_json FROM data_ingestion_batches WHERE id=?", (int(batch_id),)).fetchone()
    if not row:
        raise RuntimeError("Ingestion batch disappeared before snapshot provenance could be persisted.")
    try:
        summary = json.loads(row["summary_json"] or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        summary = {}
    existing = summary.get("dataset_snapshot")
    if existing and existing.get("manifest_sha256") != manifest["manifest_sha256"]:
        raise RuntimeError("Refusing to replace existing ingestion snapshot provenance with a different manifest.")
    summary["dataset_snapshot"] = manifest
    if preview_batch_uid:
        summary["source_snapshot_preview_batch_uid"] = preview_batch_uid
    db.execute(
        "UPDATE data_ingestion_batches SET summary_json=? WHERE id=?",
        (json.dumps(summary, sort_keys=True, ensure_ascii=False, separators=(",", ":")), int(batch_id)),
    )
    db.commit()


def _public_url(value: Any, label: str) -> str:
    text = _clean_required(value, label, 2000)
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{label} must be an absolute HTTP(S) URL.")
    if parsed.username or parsed.password:
        raise ValueError(f"{label} must not contain embedded credentials.")
    for key, _value in parse_qsl(parsed.query, keep_blank_values=True):
        key_folded = key.casefold().replace("-", "_")
        if any(marker in key_folded for marker in SENSITIVE_QUERY_MARKERS):
            raise ValueError(f"{label} must not persist API keys, tokens, signatures, or other credentials.")
    return text


def _aware_iso(value: Any, label: str) -> str:
    text = _clean_required(value, label, 100)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone offset or Z.")
    return parsed.isoformat()


def _optional_iso(value: Any, label: str) -> str | None:
    if value in (None, ""):
        return None
    text = _clean_required(value, label, 100)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601 when supplied.") from exc
    return parsed.isoformat()


def _clean_required(value: Any, label: str, max_length: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required.")
    if len(text) > max_length:
        raise ValueError(f"{label} is too long.")
    return text


def _clean_optional(value: Any, max_length: int) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) > max_length:
        raise ValueError("dataset_snapshot text field is too long.")
    return text
