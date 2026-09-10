"""Controlled acquisition of exact public/official dataset artifacts.

Acquisition is intentionally separate from ingestion.  It reads one operator-
selected artifact, verifies its size and format, stores an immutable raw copy
under a caller-controlled root, and returns a non-secret snapshot manifest for
the existing preview/apply ingestion contract.

This module never fetches arbitrary web pages and never accepts credentials.
Operators should download an artifact through an approved/public channel, then
pass the exact local file to :func:`acquire_source_file`.
"""
from __future__ import annotations

import csv
import hashlib
import json
import mimetypes
import os
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

from .public_source_registry import get_public_ingestion_source


MAX_ARTIFACT_BYTES = 50 * 1024 * 1024
SUPPORTED_FORMATS = {"csv", "json", "xlsx", "xls", "zip"}
INSPECTABLE_FORMATS = {"csv", "json", "xlsx", "zip"}
USAGE_BASES = {
    "official_public_download",
    "open_data_license",
    "authorized_export",
    "manual_public_snapshot",
}
SENSITIVE_QUERY_MARKERS = ("key", "token", "secret", "signature", "credential", "password")
_FORMAT_BY_SUFFIX = {
    ".csv": "csv",
    ".json": "json",
    ".xlsx": "xlsx",
    ".xls": "xls",
    ".zip": "zip",
}
_SAFE_FILENAME = re.compile(r"^[^/\\\x00]+$")


class AcquisitionError(ValueError):
    """An artifact cannot be safely acquired or inspected."""


def acquire_source_file(
    source_id: str,
    source_url: str,
    input_path: str | Path,
    *,
    storage_root: str | Path,
    usage_basis: str,
    license_or_terms: str,
    license_url: str | None = None,
    dataset_version: str | None = None,
    published_at: str | None = None,
    retrieved_at: str | None = None,
    file_name: str | None = None,
    max_bytes: int = MAX_ARTIFACT_BYTES,
) -> dict[str, Any]:
    """Acquire one exact local artifact and return its safe snapshot manifest."""
    path = Path(input_path)
    if not path.is_file():
        raise AcquisitionError("input_path must point to a regular file.")
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise AcquisitionError("The source artifact could not be read.") from exc
    return acquire_source_bytes(
        source_id,
        source_url,
        content,
        storage_root=storage_root,
        usage_basis=usage_basis,
        license_or_terms=license_or_terms,
        license_url=license_url,
        dataset_version=dataset_version,
        published_at=published_at,
        retrieved_at=retrieved_at,
        file_name=file_name or path.name,
        max_bytes=max_bytes,
    )


def acquire_source_bytes(
    source_id: str,
    source_url: str,
    content: bytes,
    *,
    storage_root: str | Path,
    usage_basis: str,
    license_or_terms: str,
    license_url: str | None = None,
    dataset_version: str | None = None,
    published_at: str | None = None,
    retrieved_at: str | None = None,
    file_name: str,
    max_bytes: int = MAX_ARTIFACT_BYTES,
) -> dict[str, Any]:
    """Store bytes by content hash and build a non-secret snapshot manifest.

    The generated storage reference is relative to ``storage_root`` and is
    content-addressed, so an existing artifact is never overwritten.
    """
    source = get_public_ingestion_source(str(source_id or "").strip())
    if not source:
        raise AcquisitionError(f"Unknown public ingestion source '{source_id}'.")
    if not isinstance(content, (bytes, bytearray, memoryview)):
        raise AcquisitionError("content must be bytes from an exact downloaded artifact.")
    payload = bytes(content)
    try:
        limit = int(max_bytes)
    except (TypeError, ValueError) as exc:
        raise AcquisitionError("max_bytes must be a positive integer.") from exc
    if limit <= 0:
        raise AcquisitionError("max_bytes must be a positive integer.")
    if len(payload) > limit:
        raise AcquisitionError(f"The source artifact exceeds the safe {limit} byte limit.")

    safe_name = _safe_filename(file_name)
    file_format = detect_file_format(safe_name)
    if file_format not in SUPPORTED_FORMATS:
        raise AcquisitionError("Unsupported source artifact format. Use CSV, JSON, XLS/XLSX, or ZIP.")

    canonical_url = canonical_source_url(source_url)
    retrieved = _aware_iso(retrieved_at or datetime.now(timezone.utc).isoformat(), "retrieved_at")
    published = _optional_iso(published_at, "published_at")
    version = _clean_optional(dataset_version, "dataset_version", 200)
    if not version and not published:
        raise AcquisitionError("dataset_version or published_at is required for an immutable snapshot.")
    basis = str(usage_basis or "").strip().lower()
    if basis not in USAGE_BASES:
        raise AcquisitionError("usage_basis must identify the permitted public/authorized use basis.")
    terms = _clean_required(license_or_terms, "license_or_terms", 500)
    safe_license_url = canonical_source_url(license_url) if license_url else None

    digest = hashlib.sha256(payload).hexdigest()
    relative_ref = Path("raw") / str(source["source_id"]) / digest / safe_name
    root = Path(storage_root).expanduser().resolve()
    target = (root / relative_ref).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise AcquisitionError("storage_root produced an unsafe storage reference.") from exc
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        try:
            existing_digest = _sha256_file(target)
        except OSError as exc:
            raise AcquisitionError("The existing raw snapshot could not be read.") from exc
        if existing_digest != digest:
            raise AcquisitionError("Refusing to overwrite a different artifact at the content-addressed path.")
        acquisition_status = "ALREADY_PRESENT"
    else:
        _atomic_write(target, payload)
        acquisition_status = "ACQUIRED"

    storage_ref = relative_ref.as_posix()
    snapshot = {
        "source_id": source["source_id"],
        "source_url": canonical_url,
        "retrieved_at": retrieved,
        "published_at": published,
        "dataset_version": version,
        "file_name": safe_name,
        "file_format": file_format,
        "mime_type": mimetypes.guess_type(safe_name)[0] or "application/octet-stream",
        "file_size_bytes": len(payload),
        "file_sha256": digest,
        "usage_basis": basis,
        "license_or_terms": terms,
        "license_url": safe_license_url,
        "storage_ref": storage_ref,
    }
    manifest_sha256 = _manifest_sha256(snapshot)
    snapshot["manifest_sha256"] = manifest_sha256
    snapshot["snapshot_uid"] = f"snapshot_{manifest_sha256[:20]}"
    return {
        "acquisition_status": acquisition_status,
        "source_id": source["source_id"],
        "source_name": source["name"],
        "source_url": canonical_url,
        "retrieved_at": retrieved,
        "published_at": published,
        "dataset_version": version,
        "original_filename": safe_name,
        "file_format": file_format,
        "mime_type": snapshot["mime_type"],
        "file_size_bytes": len(payload),
        "file_sha256": digest,
        "usage_basis": basis,
        "license_or_terms": terms,
        "license_url": safe_license_url,
        "storage_ref": storage_ref,
        "snapshot_uid": snapshot["snapshot_uid"],
        "manifest_sha256": manifest_sha256,
        "dataset_snapshot": snapshot,
        "stored_path": str(target),
    }


def inspect_artifact(
    input_path: str | Path,
    *,
    file_name: str | None = None,
    max_bytes: int = MAX_ARTIFACT_BYTES,
) -> dict[str, Any]:
    """Inspect schema shape without returning row values or private content."""
    path = Path(input_path)
    if not path.is_file():
        raise AcquisitionError("input_path must point to a regular file.")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise AcquisitionError("The source artifact could not be read.") from exc
    return inspect_bytes(payload, file_name=file_name or path.name, max_bytes=max_bytes)


def inspect_bytes(
    content: bytes,
    *,
    file_name: str,
    max_bytes: int = MAX_ARTIFACT_BYTES,
) -> dict[str, Any]:
    """Return bounded schema metadata for a supported artifact."""
    if not isinstance(content, (bytes, bytearray, memoryview)):
        raise AcquisitionError("content must be bytes from an exact downloaded artifact.")
    payload = bytes(content)
    if len(payload) > int(max_bytes):
        raise AcquisitionError("The source artifact exceeds the safe inspection limit.")
    safe_name = _safe_filename(file_name)
    file_format = detect_file_format(safe_name)
    if file_format not in SUPPORTED_FORMATS:
        raise AcquisitionError("Unsupported source artifact format.")
    if file_format == "csv":
        return _inspect_csv(payload)
    if file_format == "json":
        return _inspect_json(payload)
    if file_format == "xlsx":
        return _inspect_xlsx(payload)
    if file_format == "zip":
        return _inspect_zip(payload)
    return {
        "file_format": "xls",
        "schema_status": "UNSUPPORTED_REQUIRES_XLS_PARSER",
        "columns": [],
        "row_count": None,
        "message": "Legacy XLS inspection requires an approved parser; retain the exact artifact and map it manually.",
    }


def detect_file_format(file_name: str) -> str:
    """Return a conservative format label based on the original filename."""
    safe_name = _safe_filename(file_name)
    return _FORMAT_BY_SUFFIX.get(Path(safe_name).suffix.casefold(), "")


def canonical_source_url(value: str) -> str:
    """Canonicalize a public URL while rejecting credentials and secret query keys."""
    text = _clean_required(value, "source_url", 2000)
    parsed = urlsplit(text)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise AcquisitionError("source_url must be an absolute HTTP(S) URL.")
    if parsed.username or parsed.password:
        raise AcquisitionError("source_url must not contain embedded credentials.")
    for key, _value in parse_qsl(parsed.query, keep_blank_values=True):
        folded = key.casefold().replace("-", "_")
        if any(marker in folded for marker in SENSITIVE_QUERY_MARKERS):
            raise AcquisitionError("source_url must not contain API keys, tokens, signatures, or credentials.")
    hostname = (parsed.hostname or "").casefold()
    netloc = hostname
    if parsed.port:
        netloc = f"{hostname}:{parsed.port}"
    query_items = sorted(parse_qsl(parsed.query, keep_blank_values=True))
    query = urlencode(query_items, doseq=True)
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.casefold(), netloc, path, query, ""))


def _inspect_csv(payload: bytes) -> dict[str, Any]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AcquisitionError("CSV artifact must be UTF-8 or UTF-8 with BOM for safe inspection.") from exc
    try:
        reader = csv.reader(text.splitlines())
        rows = list(reader)
    except csv.Error as exc:
        raise AcquisitionError("CSV artifact could not be parsed safely.") from exc
    if not rows:
        return {"file_format": "csv", "schema_status": "EMPTY", "columns": [], "row_count": 0}
    columns = _normalize_columns(rows[0])
    return {
        "file_format": "csv",
        "schema_status": "VALID",
        "columns": columns,
        "row_count": max(0, len(rows) - 1),
    }


def _inspect_json(payload: bytes) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcquisitionError("JSON artifact could not be parsed safely.") from exc
    rows: Any = value
    if isinstance(value, dict):
        for key in ("records", "data", "items", "results"):
            if isinstance(value.get(key), list):
                rows = value[key]
                break
    if not isinstance(rows, list):
        raise AcquisitionError("JSON artifact must contain a top-level list or a records/data/items/results list.")
    columns = sorted({str(key) for row in rows[:100] if isinstance(row, dict) for key in row.keys()})
    return {
        "file_format": "json",
        "schema_status": "VALID",
        "columns": columns,
        "row_count": len(rows),
    }


def _inspect_zip(payload: bytes) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(_bytes_file(payload)) as archive:
            members = []
            supported = []
            total_uncompressed = 0
            for info in archive.infolist():
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or any(part == ".." for part in Path(name).parts):
                    raise AcquisitionError("ZIP archive contains an unsafe member path.")
                if info.flag_bits & 0x1:
                    raise AcquisitionError("Encrypted ZIP archives are not supported.")
                total_uncompressed += int(info.file_size or 0)
                if total_uncompressed > MAX_ARTIFACT_BYTES * 4:
                    raise AcquisitionError("ZIP archive expands beyond the safe inspection limit.")
                if not info.is_dir():
                    members.append({"name": name, "size_bytes": int(info.file_size or 0)})
                    if _FORMAT_BY_SUFFIX.get(Path(name).suffix.casefold(), "") in INSPECTABLE_FORMATS:
                        supported.append(name)
    except zipfile.BadZipFile as exc:
        raise AcquisitionError("ZIP artifact could not be parsed safely.") from exc
    return {
        "file_format": "zip",
        "schema_status": "VALID",
        "columns": [],
        "row_count": None,
        "members": members[:500],
        "supported_members": supported[:500],
    }


def _inspect_xlsx(payload: bytes) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(_bytes_file(payload)) as archive:
            names = {info.filename for info in archive.infolist()}
            if "xl/worksheets/sheet1.xml" not in names:
                raise AcquisitionError("XLSX artifact does not contain a first worksheet.")
            shared_strings = _xlsx_shared_strings(archive.read("xl/sharedStrings.xml")) if "xl/sharedStrings.xml" in names else []
            root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise AcquisitionError("XLSX artifact could not be parsed safely.") from exc
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rows = root.findall(".//main:sheetData/main:row", ns)
    if not rows:
        return {"file_format": "xlsx", "schema_status": "EMPTY", "columns": [], "row_count": 0}
    first = {}
    for cell in rows[0].findall("main:c", ns):
        ref = cell.attrib.get("r", "")
        index = _xlsx_column_index(ref)
        if index is None:
            continue
        first[index] = _xlsx_cell_value(cell, shared_strings, ns)
    columns = _normalize_columns([first[index] for index in sorted(first)])
    return {
        "file_format": "xlsx",
        "schema_status": "VALID",
        "columns": columns,
        "row_count": max(0, len(rows) - 1),
    }


def _xlsx_shared_strings(payload: bytes) -> list[str]:
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ET.fromstring(payload)
    return ["".join(node.itertext()) for node in root.findall(".//main:si", ns)]


def _xlsx_cell_value(cell: ET.Element, shared_strings: list[str], ns: dict[str, str]) -> str:
    value = cell.find("main:v", ns)
    raw = "" if value is None else str(value.text or "")
    if cell.attrib.get("t") == "s":
        try:
            return shared_strings[int(raw)]
        except (ValueError, IndexError):
            return ""
    if cell.attrib.get("t") == "inlineStr":
        inline = cell.find("main:is", ns)
        return "" if inline is None else "".join(inline.itertext())
    return raw


def _xlsx_column_index(ref: str) -> int | None:
    letters = "".join(char for char in ref if char.isalpha()).upper()
    if not letters:
        return None
    value = 0
    for char in letters:
        value = value * 26 + ord(char) - ord("A") + 1
    return value


def _normalize_columns(values: list[Any]) -> list[str]:
    result = []
    seen: dict[str, int] = {}
    for index, value in enumerate(values, start=1):
        label = str(value or "").strip() or f"column_{index}"
        count = seen.get(label, 0) + 1
        seen[label] = count
        result.append(label if count == 1 else f"{label}_{count}")
    return result


def _bytes_file(payload: bytes):
    """Return a seekable temporary file-like object for ZipFile."""
    handle = tempfile.SpooledTemporaryFile(max_size=2 * 1024 * 1024)
    handle.write(payload)
    handle.seek(0)
    return handle


def _manifest_sha256(snapshot: dict[str, Any]) -> str:
    canonical = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(target: Path, payload: bytes) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".partial-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except OSError as exc:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise AcquisitionError("The raw artifact could not be stored atomically.") from exc


def _safe_filename(value: Any) -> str:
    text = str(value or "").strip()
    if not text or not _SAFE_FILENAME.fullmatch(text) or text in {".", ".."}:
        raise AcquisitionError("file_name must be a safe base filename without path separators.")
    return text


def _clean_required(value: Any, label: str, max_length: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise AcquisitionError(f"{label} is required.")
    if len(text) > max_length:
        raise AcquisitionError(f"{label} is too long.")
    return text


def _clean_optional(value: Any, label: str, max_length: int) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) > max_length:
        raise AcquisitionError(f"{label} is too long.")
    return text


def _aware_iso(value: Any, label: str) -> str:
    text = _clean_required(value, label, 100)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AcquisitionError(f"{label} must be an ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None:
        raise AcquisitionError(f"{label} must include a timezone offset or Z.")
    return parsed.isoformat()


def _optional_iso(value: Any, label: str) -> str | None:
    if value in (None, ""):
        return None
    return _aware_iso(value, label)

