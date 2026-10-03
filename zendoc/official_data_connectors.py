"""Bounded live connectors for reviewed official/public datasets.

The connector layer fetches only allowlisted public resources, normalizes a
minimal non-personal record shape, and hands data to the existing provenance-
aware ingestion pipeline. Fetching never makes a listing ZENDOC-verified,
bookable, available, or clinically authoritative.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .public_data_ingestion import ingest_public_records


DATA_GOV_API_BASE = "https://api.data.gov.in/resource"
DATA_GOV_HOSPITAL_RESOURCE_ID = "98fa254e-c5f8-4910-a19b-4828939b477d"
DATA_GOV_HOSPITAL_SOURCE_ID = "data_gov_hospitals"
DATA_GOV_HOSPITAL_CATALOG_UPDATED_ON = "2018-01-12"
USER_AGENT = "ZENDOC-OfficialDataConnector/1.0 (+https://github.com/kapildebbiswas97-creator/zendoc)"


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or text in {"0", "-", "NA", "N/A", "null", "None"}:
        return None
    return text


def _coordinates(value: Any) -> tuple[float | None, float | None]:
    text = _clean(value)
    if not text or "," not in text:
        return None, None
    left, right = text.split(",", 1)
    try:
        lat = float(left.strip())
        lng = float(right.strip())
    except (TypeError, ValueError):
        return None, None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None, None
    return lat, lng


def _stable_record_id(record: dict[str, Any]) -> str:
    explicit = _clean(record.get("sr_no"))
    if explicit:
        return explicit[:160]
    parts = [
        _clean(record.get("hospital_name")) or "",
        _clean(record.get("address_original_first_line")) or "",
        _clean(record.get("state")) or "",
        _clean(record.get("district")) or "",
        _clean(record.get("pincode")) or "",
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def normalize_data_gov_hospital(record: dict[str, Any]) -> dict[str, Any] | None:
    """Map one OGD hospital row into ZENDOC's reviewed public-entity contract."""
    if not isinstance(record, dict):
        return None
    name = _clean(record.get("hospital_name"))
    if not name:
        return None

    latitude, longitude = _coordinates(record.get("location_coordinates"))
    address = _clean(record.get("address_original_first_line")) or _clean(record.get("location"))
    public_phone = (
        _clean(record.get("telephone"))
        or _clean(record.get("mobile_number"))
        or _clean(record.get("helpline"))
        or _clean(record.get("tollfree"))
    )

    metadata = {
        key: value
        for key, value in {
            "resource_id": DATA_GOV_HOSPITAL_RESOURCE_ID,
            "source_catalog_updated_on": DATA_GOV_HOSPITAL_CATALOG_UPDATED_ON,
            "hospital_category": _clean(record.get("hospital_category")),
            "hospital_care_type": _clean(record.get("hospital_care_type")),
            "systems_of_medicine": _clean(record.get("discipline_systems_of_medicine")),
            "facilities": _clean(record.get("facilities")),
            "accreditation": _clean(record.get("accreditation")),
            "established_year": _clean(record.get("establised_year")),
            "emergency_services": _clean(record.get("emergency_services")),
            "ambulance_phone_no": _clean(record.get("ambulance_phone_no")),
            "bloodbank_phone_no": _clean(record.get("bloodbank_phone_no")),
        }.items()
        if value is not None
    }

    return {
        "source_record_id": _stable_record_id(record),
        "name": name,
        "category": "hospital",
        "specialty": _clean(record.get("specialties")),
        "address": address,
        "city": _clean(record.get("town")) or _clean(record.get("location")),
        "district": _clean(record.get("district")),
        "state": _clean(record.get("state")),
        "subdistrict": _clean(record.get("subdistrict")),
        "village": _clean(record.get("village")),
        "locality": _clean(record.get("subtown")),
        "postal_code": _clean(record.get("pincode")),
        "latitude": latitude,
        "longitude": longitude,
        "public_phone": public_phone,
        "public_email": _clean(record.get("hospital_primary_email_id")),
        "website": _clean(record.get("website")),
        "freshness_at": None,
        "metadata": metadata,
    }


def fetch_data_gov_hospitals(
    *,
    api_key: str | None = None,
    state: str | None = None,
    district: str | None = None,
    limit: int = 100,
    offset: int = 0,
    timeout_seconds: int = 15,
) -> dict[str, Any]:
    """Fetch one bounded page of India's OGD National Hospital Directory.

    A server-side data.gov.in API key is required. The key is never returned,
    logged, or included in raised error messages.
    """
    key = str(api_key or os.environ.get("ZENDOC_DATA_GOV_IN_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("India OGD connector requires ZENDOC_DATA_GOV_IN_API_KEY.")

    limit = max(1, min(int(limit or 100), 500))
    offset = max(0, int(offset or 0))
    timeout_seconds = max(2, min(int(timeout_seconds or 15), 30))

    params: dict[str, str | int] = {
        "api-key": key,
        "format": "json",
        "limit": limit,
        "offset": offset,
    }
    if _clean(state):
        params["filters[state]"] = str(state).strip()
    if _clean(district):
        params["filters[district]"] = str(district).strip()

    url = (
        f"{DATA_GOV_API_BASE}/{DATA_GOV_HOSPITAL_RESOURCE_ID}?"
        f"{urllib.parse.urlencode(params)}"
    )
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read(4_194_305)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(
            f"India OGD hospital directory is temporarily unavailable ({type(exc).__name__})."
        ) from exc

    if len(raw) > 4_194_304:
        raise RuntimeError("India OGD hospital directory response exceeded the safe response limit.")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("India OGD hospital directory returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("India OGD hospital directory returned an invalid response.")

    rows = payload.get("records") or []
    if not isinstance(rows, list):
        raise RuntimeError("India OGD hospital directory response did not contain a record list.")

    normalized = []
    for row in rows:
        item = normalize_data_gov_hospital(row)
        if item:
            normalized.append(item)

    try:
        upstream_total = int(payload.get("total")) if payload.get("total") is not None else None
    except (TypeError, ValueError):
        upstream_total = None

    return {
        "source_id": DATA_GOV_HOSPITAL_SOURCE_ID,
        "resource_id": DATA_GOV_HOSPITAL_RESOURCE_ID,
        "source_catalog_updated_on": DATA_GOV_HOSPITAL_CATALOG_UPDATED_ON,
        "records": normalized,
        "record_count": len(normalized),
        "upstream_count": len(rows),
        "upstream_total": upstream_total,
        "offset": offset,
        "limit": limit,
        "filters": {
            "state": _clean(state),
            "district": _clean(district),
        },
        "truth_notice": (
            "Official public directory data is discovery evidence only. "
            "It does not prove current provider verification, availability, booking connectivity, "
            "bed capacity, medicine stock, emergency dispatch, or scheme eligibility."
        ),
    }


def ingest_data_gov_hospitals(
    actor: Any,
    *,
    api_key: str | None = None,
    state: str | None = None,
    district: str | None = None,
    limit: int = 100,
    offset: int = 0,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Fetch a bounded OGD page and pass it through reviewed ingestion.

    Dry-run remains the default. Applying data still requires the existing
    owner authorization in ingest_public_records.
    """
    fetched = fetch_data_gov_hospitals(
        api_key=api_key,
        state=state,
        district=district,
        limit=limit,
        offset=offset,
    )
    result = ingest_public_records(
        actor,
        source_id=DATA_GOV_HOSPITAL_SOURCE_ID,
        ingestion_type="public_healthcare_entities",
        records=fetched["records"],
        dry_run=dry_run,
    )
    return {
        "fetch": {key: value for key, value in fetched.items() if key != "records"},
        "ingestion": result,
    }
