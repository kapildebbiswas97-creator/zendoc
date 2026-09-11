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

from .dataset_snapshot_ingestion import normalize_dataset_snapshot
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
_SAFE_FILENAME = re.compile(r'^[^/\\\x00-\x1f\x7f<>:"|?*]+$')
_WINDOWS_DEVICE_NAME = re.compile(r"^(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])$", re.IGNORECASE)


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
    content = _read_bounded_file(path, max_bytes)
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
        raise AcquisitionError("Unknown public ingestion source.")
    if not isinstance(content, (bytes, bytearray, memoryview)):
        raise AcquisitionError("content must be bytes from an exact downloaded artifact.")
    limit = _byte_limit(max_bytes)
    size = content.nbytes if isinstance(content, memoryview) else len(content)
    if size > limit:
        raise AcquisitionError(f"The source artifact exceeds the safe {limit} byte limit.")
    payload = bytes(content)

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
    storage_ref = relative_ref.as_posix()
    snapshot_draft = {
        "source_id": source["source_id"],
        "source_url": canonical_url,
        "retrieved_at": retrieved,
        "published_at": published,
        "dataset_version": version,
        "file_name": safe_name,
        "file_format": file_format,
        "file_size_bytes": len(payload),
        "file_sha256": digest,
        "usage_basis": basis,
        "license_or_terms": terms,
        "license_url": safe_license_url,
        "storage_ref": storage_ref,
    }
    # Use the exact same canonicalizer as the owner-only preview/apply path.
    # This prevents an acquisition manifest from silently changing identity
    # when it is handed to ingestion (for example by adding MIME metadata).
    try:
        snapshot = normalize_dataset_snapshot(source["source_id"], snapshot_draft)
    except (LookupError, ValueError) as exc:
        raise AcquisitionError("The source snapshot manifest is invalid.") from exc
    manifest_sha256 = snapshot["manifest_sha256"]

    # Validate all provenance before creating directories or writing artifacts.
    try:
        root = Path(storage_root).expanduser().resolve()
        target = (root / relative_ref).resolve()
        target.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if _sha256_file(target) != digest:
                raise AcquisitionError("Refusing to overwrite a different artifact at the content-addressed path.")
            acquisition_status = "ALREADY_PRESENT"
        else:
            _atomic_write(target, payload)
            acquisition_status = "ACQUIRED"
    except AcquisitionError:
        raise
    except (OSError, ValueError) as exc:
        raise AcquisitionError("The raw snapshot could not be stored safely.") from exc
    return {
        "acquisition_status": acquisition_status,
        "source_id": source["source_id"],
        "source_name": snapshot["source_name"],
        "source_url": canonical_url,
        "retrieved_at": retrieved,
        "published_at": published,
        "dataset_version": version,
        "original_filename": safe_name,
        "file_format": file_format,
        "mime_type": mimetypes.guess_type(safe_name)[0] or "application/octet-stream",
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
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Inspect schema shape without returning row values or private content."""
    path = Path(input_path)
    payload = _read_bounded_file(path, max_bytes)
    if expected_sha256 is not None and hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise AcquisitionError("The stored artifact does not match its acquired SHA-256 digest.")
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
    limit = _byte_limit(max_bytes)
    size = content.nbytes if isinstance(content, memoryview) else len(content)
    if size > limit:
        raise AcquisitionError("The source artifact exceeds the safe inspection limit.")
    payload = bytes(content)
    safe_name = _safe_filename(file_name)
    file_format = detect_file_format(safe_name)
    if file_format not in SUPPORTED_FORMATS:
        raise AcquisitionError("Unsupported source artifact format.")
    if file_format == "csv":
        return _inspect_csv(payload)
    if file_format == "json":
        return _inspect_json(payload)
    if file_format == "xlsx":
        return _inspect_xlsx(payload, max_bytes=limit)
    if file_format == "zip":
        return _inspect_zip(payload, max_bytes=limit)
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
    try:
        parsed = urlsplit(text)
        hostname = (parsed.hostname or "").casefold()
        port = parsed.port
    except ValueError as exc:
        raise AcquisitionError("source_url must be a valid public HTTP(S) URL.") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise AcquisitionError("source_url must be an absolute HTTP(S) URL.")
    if parsed.username or parsed.password:
        raise AcquisitionError("source_url must not contain embedded credentials.")
    for key, _value in parse_qsl(parsed.query, keep_blank_values=True):
        folded = key.casefold().replace("-", "_")
        if any(marker in folded for marker in SENSITIVE_QUERY_MARKERS):
            raise AcquisitionError("source_url must not contain API keys, tokens, signatures, or credentials.")
    netloc = f"[{hostname}]" if ":" in hostname else hostname
    if port:
        netloc = f"{netloc}:{port}"
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


def _inspect_zip(payload: bytes, *, max_bytes: int) -> dict[str, Any]:
    try:
        with _bytes_file(payload) as handle, zipfile.ZipFile(handle) as archive:
            members = []
            supported = []
            infos = archive.infolist()
            _assert_archive_expansion_safe(infos, max_bytes=max_bytes)
            for info in infos:
                name = info.filename.replace("\\", "/")
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


def _inspect_xlsx(payload: bytes, *, max_bytes: int) -> dict[str, Any]:
    try:
        with _bytes_file(payload) as handle, zipfile.ZipFile(handle) as archive:
            infos = archive.infolist()
            _assert_archive_expansion_safe(infos, max_bytes=max_bytes)
            names = {info.filename for info in infos}
            if "xl/worksheets/sheet1.xml" not in names:
                raise AcquisitionError("XLSX artifact does not contain a first worksheet.")
            shared_strings = _xlsx_shared_strings(archive.read("xl/sharedStrings.xml")) if "xl/sharedStrings.xml" in names else []
            root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError, RuntimeError, NotImplementedError) as exc:
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
    try:
        handle.write(payload)
        handle.seek(0)
    except Exception:
        handle.close()
        raise
    return handle


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
    text = str(value or "")
    if (
        not text
        or not _SAFE_FILENAME.fullmatch(text)
        or text in {".", ".."}
        or len(text) > 255
        or text[-1] in {".", " "}
        or _WINDOWS_DEVICE_NAME.fullmatch(text.split(".", 1)[0].rstrip(" "))
    ):
        raise AcquisitionError("file_name must be a safe base filename without path separators.")
    return text


def _read_bounded_file(path: Path, max_bytes: int) -> bytes:
    """Read one local artifact without allowing an unbounded allocation."""
    limit = _byte_limit(max_bytes)
    try:
        if not path.is_file():
            raise AcquisitionError("input_path must point to a regular file.")
        if path.stat().st_size > limit:
            raise AcquisitionError(f"The source artifact exceeds the safe {limit} byte limit.")
        with path.open("rb") as handle:
            payload = handle.read(limit + 1)
    except AcquisitionError:
        raise
    except OSError as exc:
        raise AcquisitionError("The source artifact could not be read.") from exc
    if len(payload) > limit:
        raise AcquisitionError(f"The source artifact exceeds the safe {limit} byte limit.")
    return payload


def _byte_limit(value: int) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AcquisitionError("max_bytes must be a positive integer.") from exc
    if limit <= 0:
        raise AcquisitionError("max_bytes must be a positive integer.")
    return limit


def _assert_archive_expansion_safe(infos: list[zipfile.ZipInfo], *, max_bytes: int) -> None:
    # Check metadata for every member before opening any compressed content.
    if len(infos) > 5000:
        raise AcquisitionError("ZIP archive contains too many members for safe inspection.")
    total = 0
    for info in infos:
        name = info.filename.replace("\\", "/")
        components = name[:-1].split("/") if info.is_dir() else name.split("/")
        try:
            for component in components:
                _safe_filename(component)
        except AcquisitionError as exc:
            raise AcquisitionError("ZIP archive contains an unsafe member path.") from exc
        if info.flag_bits & 0x1:
            raise AcquisitionError("Encrypted ZIP archives are not supported.")
        total += int(info.file_size or 0)
        limit = min(max_bytes, MAX_ARTIFACT_BYTES)
        if total > limit * 4 or int(info.file_size or 0) > limit * 2:
            raise AcquisitionError("ZIP archive expands beyond the safe inspection limit.")


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


