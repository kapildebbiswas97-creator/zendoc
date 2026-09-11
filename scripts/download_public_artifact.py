"""Download one exact public artifact into the ZENDOC immutable data workspace.

This is deliberately NOT a general web scraper. The caller must name an
existing source_id from ZENDOC's public registry. The requested URL and final
redirect URL must remain on the registered official host (or its parent/subdomain
variant), URLs with credential-like query keys are rejected by the acquisition
layer, and downloads are bounded to the existing 50 MiB acquisition limit.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from zendoc.data_acquisition import (
    MAX_ARTIFACT_BYTES,
    AcquisitionError,
    acquire_source_bytes,
    canonical_source_url,
)
from zendoc.public_source_registry import get_public_ingestion_source


_FILENAME_RE = re.compile(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';]+)', re.IGNORECASE)


def _host_allowed(candidate: str, official: str) -> bool:
    candidate = (candidate or "").lower().strip(".")
    official = (official or "").lower().strip(".")
    if not candidate or not official:
        return False
    return (
        candidate == official
        or candidate.endswith("." + official)
        or official.endswith("." + candidate)
    )


def _filename_from_response(response, requested_url: str, override: str | None) -> str:
    if override:
        return Path(override).name
    disposition = response.headers.get("Content-Disposition") or ""
    match = _FILENAME_RE.search(disposition)
    if match:
        return Path(match.group(1).strip()).name
    name = Path(urlsplit(requested_url).path).name
    if not name or "." not in name:
        raise AcquisitionError("Could not determine artifact filename; pass --file-name with CSV/JSON/XLS/XLSX/ZIP extension.")
    return name


def download_public_artifact(
    source_id: str,
    artifact_url: str,
    *,
    storage_root: str | Path,
    usage_basis: str,
    license_or_terms: str,
    license_url: str | None = None,
    dataset_version: str | None = None,
    published_at: str | None = None,
    file_name: str | None = None,
    timeout_seconds: int = 45,
) -> dict:
    source = get_public_ingestion_source(source_id)
    if not source:
        raise AcquisitionError("Unknown public ingestion source.")
    if "AUTHORIZED" in str(source.get("live_fetch_status") or "").upper() or "ONBOARDING" in str(source.get("live_fetch_status") or "").upper():
        raise AcquisitionError("This source requires onboarding/authorized access and cannot use the public downloader.")

    safe_url = canonical_source_url(artifact_url)
    requested_host = (urlsplit(safe_url).hostname or "").lower()
    official_host = (urlsplit(source["official_url"]).hostname or "").lower()
    if not _host_allowed(requested_host, official_host):
        raise AcquisitionError("Artifact URL host does not match the registered official source host.")

    request = Request(
        safe_url,
        headers={"User-Agent": "ZENDOC-PublicDataAcquisition/1.0 (+official-public-data-only)"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=max(5, min(int(timeout_seconds), 120))) as response:
            final_url = canonical_source_url(response.geturl())
            final_host = (urlsplit(final_url).hostname or "").lower()
            if not _host_allowed(final_host, official_host):
                raise AcquisitionError("Download redirected outside the registered official source host.")
            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > MAX_ARTIFACT_BYTES:
                        raise AcquisitionError("Artifact exceeds the safe 50 MiB download limit.")
                except ValueError:
                    pass
            payload = response.read(MAX_ARTIFACT_BYTES + 1)
    except AcquisitionError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise AcquisitionError("Official artifact download failed.") from exc

    if len(payload) > MAX_ARTIFACT_BYTES:
        raise AcquisitionError("Artifact exceeds the safe 50 MiB download limit.")
    resolved_name = _filename_from_response(response, final_url, file_name)
    result = acquire_source_bytes(
        source_id,
        final_url,
        payload,
        storage_root=storage_root,
        usage_basis=usage_basis,
        license_or_terms=license_or_terms,
        license_url=license_url,
        dataset_version=dataset_version,
        published_at=published_at,
        file_name=resolved_name,
    )
    result.pop("stored_path", None)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Download one registered official/public artifact safely.")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--artifact-url", required=True)
    parser.add_argument("--storage-root", required=True)
    parser.add_argument("--usage-basis", default="official_public_download")
    parser.add_argument("--license-or-terms", required=True)
    parser.add_argument("--license-url")
    parser.add_argument("--dataset-version")
    parser.add_argument("--published-at")
    parser.add_argument("--file-name")
    parser.add_argument("--timeout-seconds", type=int, default=45)
    args = parser.parse_args()
    try:
        result = download_public_artifact(
            args.source_id,
            args.artifact_url,
            storage_root=args.storage_root,
            usage_basis=args.usage_basis,
            license_or_terms=args.license_or_terms,
            license_url=args.license_url,
            dataset_version=args.dataset_version,
            published_at=args.published_at,
            file_name=args.file_name,
            timeout_seconds=args.timeout_seconds,
        )
    except AcquisitionError as exc:
        print(f"Public artifact download failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
