"""Universal healthcare discovery across ZENDOC, public directories and map listings.

The service is deliberately discovery-only. External/public records are never
promoted to ZENDOC verification or connected booking merely because they match
free text.
"""
from __future__ import annotations

import os
import re
from collections import OrderedDict
from urllib.parse import quote_plus

from .db import get_db
from .geospatial import nearby_records
from .places_provider import configured_places_provider
from .provider_service import public_provider


SEARCH_CATEGORIES = (
    "doctor",
    "hospital",
    "clinic",
    "pharmacy",
    "diagnostic_centre",
    "laboratory",
    "health_centre",
    "nursing_home",
    "blood_bank",
    "emergency",
)

EXTERNAL_CATEGORIES = (
    "doctor",
    "hospital",
    "clinic",
    "pharmacy",
    "diagnostic_centre",
    "emergency",
)

CATEGORY_ALIASES = {
    "doctors": "doctor",
    "doctor": "doctor",
    "physician": "doctor",
    "physicians": "doctor",
    "cardiologist": "doctor",
    "dermatologist": "doctor",
    "neurologist": "doctor",
    "pediatrician": "doctor",
    "gynaecologist": "doctor",
    "gynecologist": "doctor",
    "psychiatrist": "doctor",
    "hospital": "hospital",
    "hospitals": "hospital",
    "clinic": "clinic",
    "clinics": "clinic",
    "pharmacy": "pharmacy",
    "pharmacies": "pharmacy",
    "chemist": "pharmacy",
    "medical shop": "pharmacy",
    "medical store": "pharmacy",
    "diagnostic": "diagnostic_centre",
    "diagnostics": "diagnostic_centre",
    "diagnostic centre": "diagnostic_centre",
    "diagnostic center": "diagnostic_centre",
    "laboratory": "laboratory",
    "laboratories": "laboratory",
    "lab": "laboratory",
    "labs": "laboratory",
    "health centre": "health_centre",
    "health center": "health_centre",
    "phc": "health_centre",
    "chc": "health_centre",
    "nursing home": "nursing_home",
    "blood bank": "blood_bank",
    "emergency": "emergency",
}

GROUP_LABELS = OrderedDict((
    ("doctor", "Doctors"),
    ("hospital", "Hospitals"),
    ("clinic", "Clinics"),
    ("pharmacy", "Pharmacies"),
    ("diagnostic_centre", "Diagnostics"),
    ("laboratory", "Laboratories"),
    ("health_centre", "Health centres"),
    ("nursing_home", "Nursing homes"),
    ("blood_bank", "Blood banks"),
    ("emergency", "Emergency care"),
))


def normalize_universal_query(text=None, category=None, latitude=None, longitude=None, radius_km=10):
    text = " ".join(str(text or "").strip().split())[:160]
    category = str(category or "all").strip().lower().replace(" ", "_")
    if category not in set(SEARCH_CATEGORIES) | {"all"}:
        category = "all"
    try:
        radius = max(1, min(50, int(radius_km or 10)))
    except (TypeError, ValueError, OverflowError):
        radius = 10
    try:
        lat = float(latitude) if latitude not in (None, "") else None
        lng = float(longitude) if longitude not in (None, "") else None
        if lat is not None and not -90 <= lat <= 90:
            lat = None
        if lng is not None and not -180 <= lng <= 180:
            lng = None
    except (TypeError, ValueError):
        lat = lng = None
    if lat is None or lng is None:
        lat = lng = None
    return {"text": text, "category": category, "latitude": lat, "longitude": lng, "radius_km": radius}


def _text_parts(text):
    """Return free-text term, explicit location and inferred category."""
    raw = str(text or "").strip()
    term = raw
    location = ""
    match = re.match(r"^(.*?)\s+(?:in|near|around)\s+(.+)$", raw, flags=re.IGNORECASE)
    if match:
        term = match.group(1).strip()
        location = match.group(2).strip()

    lowered = term.lower()
    inferred = None
    matched_alias = None
    for alias in sorted(CATEGORY_ALIASES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            inferred = CATEGORY_ALIASES[alias]
            matched_alias = alias
            break

    # Make natural shorthand such as "pharmacy Kalyani" useful for nearby
    # discovery without breaking named searches such as "Apollo Hospital".
    if not location and matched_alias and lowered.startswith(matched_alias):
        remainder = term[len(matched_alias):].strip(" ,-:")
        if remainder:
            location = remainder
    return term, location, inferred


def _like(value):
    return f"%{value}%"


def _internal_search_plan(query_text, term, explicit_location, inferred_category, selected_category):
    """Choose a useful DB search term/category from natural healthcare text.

    External providers already understand constructs such as "hospital in Kalyani".
    The local/public DB should not search that entire phrase literally because it
    hides valid directory rows whose location is Kalyani and category is hospital.
    Named searches such as "Apollo Hospital in Kolkata" preserve "Apollo Hospital"
    instead of degrading to a location-only lookup.
    """
    effective_category = selected_category
    if effective_category == "all" and inferred_category:
        effective_category = inferred_category

    raw_term = str(term or "").strip()
    location = str(explicit_location or "").strip()
    if not location:
        return str(query_text or "").strip(), effective_category

    remainder = raw_term
    if inferred_category:
        aliases = [
            alias for alias, category in CATEGORY_ALIASES.items()
            if category == inferred_category
        ]
        for alias in sorted(aliases, key=len, reverse=True):
            remainder = re.sub(
                rf"\b{re.escape(alias)}\b",
                " ",
                remainder,
                flags=re.IGNORECASE,
            )
        remainder = " ".join(remainder.replace(",", " ").split()).strip()

    # "hospital in Kalyani" and "pharmacy Kalyani" should search local/public
    # rows by Kalyani, while "Apollo Hospital in Kolkata" should keep Apollo.
    if not remainder or remainder.casefold() == location.casefold():
        return location, effective_category
    return raw_term or location, effective_category


def _registered_matches(text, category, latitude, longitude, radius_km):
    db = get_db()
    clauses = ["u.active=1", "p.verification_status='verified'"]
    params = []
    if category != "all":
        provider_category = "doctor" if category == "clinic" else category
        if provider_category in {"doctor", "hospital", "pharmacy"}:
            clauses.append("p.provider_type=?")
            params.append(provider_category)
        else:
            return []
    if text:
        value = _like(text)
        clauses.append(
            "(LOWER(COALESCE(u.name,'')) LIKE LOWER(?) OR LOWER(COALESCE(p.organization,'')) LIKE LOWER(?) "
            "OR LOWER(COALESCE(p.specialty,'')) LIKE LOWER(?) OR LOWER(COALESCE(p.address,'')) LIKE LOWER(?) "
            "OR LOWER(COALESCE(p.city,'')) LIKE LOWER(?) OR LOWER(COALESCE(p.state,'')) LIKE LOWER(?) "
            "OR LOWER(COALESCE(p.postal_code,'')) LIKE LOWER(?))"
        )
        params.extend([value] * 7)
    rows = db.execute(
        f"""
        SELECT p.*, u.name AS account_name
        FROM provider_profiles p JOIN users u ON u.id=p.user_id
        WHERE {' AND '.join(clauses)}
        ORDER BY p.updated_at DESC,p.id ASC
        LIMIT 120
        """,
        params,
    ).fetchall()
    records = []
    for row in rows:
        item = dict(row)
        item["name"] = item.get("account_name")
        records.append(public_provider(item))
    if latitude is not None and longitude is not None:
        records = nearby_records(records, latitude, longitude, radius_km)
    return records


def _public_matches(text, category, latitude, longitude, radius_km):
    db = get_db()
    clauses = ["active=1"]
    params = []
    if category != "all":
        if category == "emergency":
            clauses.append("category IN ('hospital','health_centre')")
        elif category == "diagnostic_centre":
            clauses.append("category IN ('diagnostic_centre','laboratory')")
        else:
            clauses.append("category=?")
            params.append(category)
    if text:
        value = _like(text)
        clauses.append(
            "(LOWER(COALESCE(name,'')) LIKE LOWER(?) OR LOWER(COALESCE(specialty,'')) LIKE LOWER(?) "
            "OR LOWER(COALESCE(address,'')) LIKE LOWER(?) OR LOWER(COALESCE(city,'')) LIKE LOWER(?) "
            "OR LOWER(COALESCE(district,'')) LIKE LOWER(?) OR LOWER(COALESCE(state,'')) LIKE LOWER(?) "
            "OR LOWER(COALESCE(postal_code,'')) LIKE LOWER(?))"
        )
        params.extend([value] * 7)
    rows = db.execute(
        f"""
        SELECT * FROM public_healthcare_entities
        WHERE {' AND '.join(clauses)}
        ORDER BY updated_at DESC,name ASC,id ASC
        LIMIT 200
        """,
        params,
    ).fetchall()
    records = []
    for row in rows:
        item = dict(row)
        records.append({
            "id": item.get("id"),
            "name": item.get("name"),
            "provider_name": item.get("name") if item.get("category") == "doctor" else None,
            "category": item.get("category") or "healthcare",
            "specialty": item.get("specialty") or "",
            "address": item.get("address") or "",
            "city": item.get("city") or "",
            "district": item.get("district") or "",
            "state": item.get("state") or "",
            "postal_code": item.get("postal_code") or "",
            "latitude": item.get("latitude"),
            "longitude": item.get("longitude"),
            "phone": item.get("phone") or "",
            "source": "official_public_directory",
            "source_id": item.get("source_id"),
            "verification_status": item.get("zendoc_verification_status") or item.get("verification_status") or "not_verified",
            "bookable_in_zendoc": bool(item.get("bookable_in_zendoc")),
            "claimable_public_listing": True,
        })
    if latitude is not None and longitude is not None:
        records = nearby_records(records, latitude, longitude, radius_km)
    return records


def _google_maps_url(item):
    existing = str(item.get("google_maps_url") or "").strip()
    if existing:
        return existing

    latitude = item.get("latitude")
    longitude = item.get("longitude")
    try:
        if latitude not in (None, "") and longitude not in (None, ""):
            query = f"{float(latitude):.6f},{float(longitude):.6f}"
        else:
            query = " ".join(
                str(item.get(field) or "").strip()
                for field in ("name", "address", "city", "district", "state", "postal_code")
                if str(item.get(field) or "").strip()
            )
    except (TypeError, ValueError):
        query = ""

    if not query:
        return None
    return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(query)


def _google_directions_url(item, origin_latitude=None, origin_longitude=None):
    if origin_latitude is None or origin_longitude is None:
        return None
    latitude = item.get("latitude")
    longitude = item.get("longitude")
    if latitude in (None, "") or longitude in (None, ""):
        return None
    try:
        origin = f"{float(origin_latitude):.6f},{float(origin_longitude):.6f}"
        destination = f"{float(latitude):.6f},{float(longitude):.6f}"
    except (TypeError, ValueError):
        return None
    return (
        "https://www.google.com/maps/dir/?api=1&origin="
        + quote_plus(origin)
        + "&destination="
        + quote_plus(destination)
        + "&travelmode=driving"
    )


def _with_map_handoffs(records, origin_latitude=None, origin_longitude=None):
    enriched = []
    for record in records:
        item = dict(record)
        google_maps_url = _google_maps_url(item)
        if google_maps_url:
            item["google_maps_url"] = google_maps_url
        directions_url = _google_directions_url(
            item,
            origin_latitude=origin_latitude,
            origin_longitude=origin_longitude,
        )
        if directions_url:
            item["google_directions_url"] = directions_url
        enriched.append(item)
    return enriched


def _dedupe(records):
    result = []
    seen = set()
    for item in records:
        key = (
            str(item.get("category") or "").lower(),
            str(item.get("name") or "").strip().lower(),
            str(item.get("address") or item.get("city") or "").strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _rank(item, text):
    needle = str(text or "").lower()
    if not needle:
        return (3, float(item.get("distance_km") or 999999), str(item.get("name") or ""))
    name = str(item.get("name") or "").lower()
    provider_name = str(item.get("provider_name") or "").lower()
    specialty = str(item.get("specialty") or "").lower()
    location = " ".join(str(item.get(field) or "").lower() for field in ("address", "city", "district", "state", "postal_code"))
    if needle == name or needle == provider_name:
        score = 0
    elif needle in name or needle in provider_name:
        score = 1
    elif needle in specialty:
        score = 2
    elif needle in location:
        score = 3
    else:
        score = 4
    source_rank = 0 if item.get("source") == "zendoc_provider_network" else 1 if item.get("source") == "official_public_directory" else 2
    return (score, source_rank, float(item.get("distance_km") or 999999), str(item.get("name") or ""))


def _osm_poi_enabled():
    return str(os.environ.get("ZENDOC_OSM_POI_ENABLED", "true")).strip().lower() in {"1", "true", "yes", "on"}


def _osm_poi_results(location, category, latitude, longitude, radius_km):
    if not _osm_poi_enabled() or (not location and latitude is None):
        return [], None
    try:
        from .osm_healthcare import OverpassHealthcareProvider
        result = OverpassHealthcareProvider().search({
            "category": category,
            "location": location,
            "latitude": latitude,
            "longitude": longitude,
            "radius_km": radius_km,
            "country_code": "in",
        })
    except Exception:
        return [], "OpenStreetMap nearby healthcare discovery is temporarily unavailable."
    return list(result.get("results") or []), result.get("message")


def degraded_search_result(
    text=None,
    category="all",
    latitude=None,
    longitude=None,
    radius_km=10,
    message="Healthcare search is temporarily limited. Please retry in a moment.",
):
    """Return a Finder-compatible failure shape instead of leaking a 500 page."""
    query = normalize_universal_query(text, category, latitude, longitude, radius_km)
    warning = str(message or "Healthcare search is temporarily limited.").strip()
    return {
        "universal": True,
        "query": query,
        "text": query["text"],
        "results": [],
        "grouped_results": OrderedDict(),
        "category_counts": {},
        "search_origin": (
            {
                "latitude": query["latitude"],
                "longitude": query["longitude"],
                "google_maps_url": (
                    "https://www.google.com/maps/search/?api=1&query="
                    + quote_plus(f"{query['latitude']:.6f},{query['longitude']:.6f}")
                ),
            }
            if query["latitude"] is not None and query["longitude"] is not None
            else None
        ),
        "source_tiers": {
            "zendoc_verified": 0,
            "official_public_directory_not_zendoc_verified": 0,
            "external_unverified": 0,
        },
        "search_status": "degraded",
        "warnings": [warning],
        "message": warning,
        "truth_notice": (
            "ZENDOC did not fabricate replacement healthcare listings. "
            "Retry the search or use a manual location while an upstream source recovers."
        ),
    }


def universal_search(text=None, category="all", latitude=None, longitude=None, radius_km=10, places_provider=None):
    query = normalize_universal_query(text, category, latitude, longitude, radius_km)
    term, explicit_location, inferred = _text_parts(query["text"])
    selected_category = query["category"]

    internal_text, internal_category = _internal_search_plan(
        query["text"],
        term,
        explicit_location,
        inferred,
        selected_category,
    )
    records = _registered_matches(
        internal_text,
        internal_category,
        query["latitude"],
        query["longitude"],
        query["radius_km"],
    )
    records += _public_matches(
        internal_text,
        internal_category,
        query["latitude"],
        query["longitude"],
        query["radius_km"],
    )

    provider = places_provider or configured_places_provider()
    external_results = []
    external_messages = []
    warnings = []
    external_location = explicit_location or query["text"]
    external_hint = term if explicit_location else ""

    # One broad provider call for an "all healthcare" search prevents a single
    # user request from serially multiplying external timeouts across every
    # care category. Google/OSM adapters classify broad results back into the
    # supported healthcare groups; explicit category searches remain exact.
    external_categories = [
        selected_category if selected_category != "all" else (inferred or "all")
    ]

    if external_location or query["latitude"] is not None:
        for external_category in external_categories:
            try:
                place_result = provider.search({
                    "category": external_category,
                    "specialty": external_hint,
                    "location": external_location,
                    "latitude": query["latitude"],
                    "longitude": query["longitude"],
                    "radius_km": query["radius_km"],
                    "country_code": "in",
                })
            except Exception:
                place_result = None
                warnings.append(
                    "An external healthcare map source is temporarily unavailable. "
                    "Other available sources are still shown."
                )

            if place_result is not None:
                safe_results = [
                    dict(item)
                    for item in (place_result.results or [])
                    if isinstance(item, dict)
                ]
                external_results.extend(safe_results)
                if place_result.message:
                    external_messages.append(str(place_result.message))
                if not place_result.available:
                    warnings.append(
                        str(place_result.message or "").strip()
                        or "An external healthcare map source is temporarily unavailable."
                    )

        # Overpass is a fallback, not a second mandatory network dependency.
        # Running Nominatim/Google and Overpass serially on every request can
        # stack upstream latency on small/free hosts and surface as a proxy 502.
        # Use Overpass only when the configured places provider responded
        # successfully but returned no usable listings. If the primary source
        # timed out/unavailable, return a degraded page immediately instead of
        # waiting on another remote service.
        primary_available = bool(place_result is not None and place_result.available)
        if places_provider is None and not external_results and primary_available:
            osm_category = selected_category if selected_category != "all" else (inferred or "all")
            osm_results, osm_message = _osm_poi_results(
                explicit_location or query["text"],
                osm_category,
                query["latitude"],
                query["longitude"],
                query["radius_km"],
            )
            external_results.extend(
                dict(item) for item in osm_results if isinstance(item, dict)
            )
            if osm_message:
                external_messages.append(str(osm_message))
                if "unavailable" in str(osm_message).lower() or "could not" in str(osm_message).lower():
                    warnings.append(str(osm_message))

    if query["latitude"] is not None and query["longitude"] is not None and external_results:
        try:
            external_results = nearby_records(
                external_results,
                query["latitude"],
                query["longitude"],
                query["radius_km"],
            )
        except Exception:
            warnings.append(
                "Distance filtering for one external source was unavailable. "
                "The remaining listings are shown without inventing distance."
            )

    records.extend(external_results)
    records = _with_map_handoffs(
        [item for item in records if isinstance(item, dict)],
        origin_latitude=query["latitude"],
        origin_longitude=query["longitude"],
    )
    records = _dedupe(records)
    records.sort(key=lambda item: _rank(item, query["text"]))

    grouped = OrderedDict()
    for key, label in GROUP_LABELS.items():
        items = [item for item in records if str(item.get("category") or "").lower() == key]
        if items:
            grouped[key] = {"label": label, "count": len(items), "results": items[:25]}

    flat = [item for group in grouped.values() for item in group["results"]]
    source_tiers = {
        "zendoc_verified": sum(1 for item in flat if item.get("source") == "zendoc_provider_network"),
        "official_public_directory_not_zendoc_verified": sum(1 for item in flat if item.get("source") == "official_public_directory"),
        "external_unverified": sum(
            1
            for item in flat
            if item.get("source") not in {"zendoc_provider_network", "official_public_directory"}
        ),
    }

    warnings = list(dict.fromkeys(
        warning.strip()
        for warning in warnings
        if str(warning or "").strip()
    ))
    search_status = "partial" if warnings and flat else "degraded" if warnings else "complete"

    message = None
    if not flat:
        message = (
            warnings[0]
            if warnings
            else external_messages[0]
            if external_messages
            else "No healthcare matches were found. Try a broader name, specialty, city, area or PIN code."
        )

    return {
        "universal": True,
        "query": query,
        "text": query["text"],
        "results": flat,
        "grouped_results": grouped,
        "category_counts": {key: value["count"] for key, value in grouped.items()},
        "search_origin": (
            {
                "latitude": query["latitude"],
                "longitude": query["longitude"],
                "google_maps_url": (
                    "https://www.google.com/maps/search/?api=1&query="
                    + quote_plus(f"{query['latitude']:.6f},{query['longitude']:.6f}")
                ),
            }
            if query["latitude"] is not None and query["longitude"] is not None
            else None
        ),
        "source_tiers": source_tiers,
        "search_status": search_status,
        "warnings": warnings,
        "message": message,
        "truth_notice": (
            "Results combine ZENDOC verified profiles, public directories and external map listings. "
            "Only explicitly connected ZENDOC providers are bookable inside ZENDOC."
        ),
    }

