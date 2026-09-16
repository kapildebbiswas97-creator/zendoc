"""Bounded OpenStreetMap healthcare POI discovery for interactive searches.

Nominatim is useful for geocoding and named-place search, but it is not a
nearby POI enumeration service.  This module uses Nominatim only to resolve a
user-supplied location to a centre point, then asks Overpass for healthcare
features around that point.

External OSM records are discovery references only.  They are never promoted
to ZENDOC verification or connected booking.
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "ZENDOC/1.0 (+https://github.com/kapildebbiswas97-creator/zendoc)"

_CATEGORY_FILTERS = {
    "doctor": (("amenity", "doctors"), ("healthcare", "doctor")),
    "hospital": (("amenity", "hospital"), ("healthcare", "hospital")),
    "clinic": (("amenity", "clinic"), ("healthcare", "clinic")),
    "pharmacy": (("amenity", "pharmacy"), ("healthcare", "pharmacy")),
    "diagnostic_centre": (("healthcare", "laboratory"), ("amenity", "laboratory")),
    "laboratory": (("healthcare", "laboratory"), ("amenity", "laboratory")),
    "health_centre": (("healthcare", "centre"), ("healthcare", "health_centre")),
    "nursing_home": (("healthcare", "nursing_home"), ("amenity", "nursing_home")),
    "blood_bank": (("healthcare", "blood_bank"), ("amenity", "blood_bank")),
    "emergency": (("amenity", "hospital"), ("healthcare", "hospital")),
}

_CACHE = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL_SECONDS = 3600
_GEOCODE_LOCK = threading.Lock()
_LAST_GEOCODE_AT = 0.0


def _cache_get(key):
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if entry and time.time() - entry[0] < _CACHE_TTL_SECONDS:
            return entry[1]
        _CACHE.pop(key, None)
        return None


def _cache_set(key, value):
    with _CACHE_LOCK:
        if len(_CACHE) >= 128:
            oldest = min(_CACHE, key=lambda item: _CACHE[item][0])
            _CACHE.pop(oldest, None)
        _CACHE[key] = (time.time(), value)


def _number(value, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < minimum or number > maximum:
        return None
    return number


def _radius_km(value):
    try:
        value = int(value or 10)
    except (TypeError, ValueError):
        value = 10
    # Public Overpass is a shared service. Keep interactive queries bounded.
    return max(1, min(value, 25))


def _clean_category(value):
    value = str(value or "all").strip().lower().replace(" ", "_")
    return value if value in _CATEGORY_FILTERS else "all"


def _filters_for(category):
    if category == "all":
        seen = set()
        filters = []
        for key in ("doctor", "hospital", "clinic", "pharmacy", "diagnostic_centre", "health_centre", "nursing_home", "blood_bank"):
            for item in _CATEGORY_FILTERS[key]:
                if item not in seen:
                    seen.add(item)
                    filters.append(item)
        return filters
    return list(_CATEGORY_FILTERS.get(category, ()))


def _overpass_query(category, latitude, longitude, radius_metres):
    clauses = []
    for key, value in _filters_for(category):
        clauses.append(
            f'nwr(around:{radius_metres},{latitude:.6f},{longitude:.6f})["{key}"="{value}"];'
        )
    return "[out:json][timeout:20];(" + "".join(clauses) + ");out center tags 80;"


def _infer_category(tags, requested):
    if requested != "all" and requested != "emergency":
        return requested
    amenity = str(tags.get("amenity") or "").lower()
    healthcare = str(tags.get("healthcare") or "").lower()
    if amenity == "pharmacy" or healthcare == "pharmacy":
        return "pharmacy"
    if amenity == "hospital" or healthcare == "hospital":
        return "hospital"
    if amenity == "clinic" or healthcare == "clinic":
        return "clinic"
    if amenity == "doctors" or healthcare == "doctor":
        return "doctor"
    if healthcare == "laboratory" or amenity == "laboratory":
        return "diagnostic_centre"
    if healthcare in {"centre", "health_centre"}:
        return "health_centre"
    if healthcare == "nursing_home" or amenity == "nursing_home":
        return "nursing_home"
    if healthcare == "blood_bank" or amenity == "blood_bank":
        return "blood_bank"
    return "hospital" if requested == "emergency" else "healthcare"


def _address_from_tags(tags):
    direct = str(tags.get("addr:full") or "").strip()
    if direct:
        return direct
    parts = []
    street = " ".join(
        part for part in (
            str(tags.get("addr:housenumber") or "").strip(),
            str(tags.get("addr:street") or "").strip(),
        ) if part
    ).strip()
    if street:
        parts.append(street)
    for key in ("addr:suburb", "addr:city", "addr:district", "addr:state", "addr:postcode"):
        value = str(tags.get(key) or "").strip()
        if value and value not in parts:
            parts.append(value)
    return ", ".join(parts)


def _public_element(element, requested_category):
    if not isinstance(element, dict):
        return None
    tags = element.get("tags") if isinstance(element.get("tags"), dict) else {}
    center = element.get("center") if isinstance(element.get("center"), dict) else {}
    latitude = _number(element.get("lat", center.get("lat")), -90, 90)
    longitude = _number(element.get("lon", center.get("lon")), -180, 180)
    name = str(tags.get("name") or tags.get("name:en") or tags.get("operator") or "").strip()
    if not name or latitude is None or longitude is None:
        return None
    category = _infer_category(tags, requested_category)
    return {
        "id": f"osm:{element.get('type', 'element')}:{element.get('id', '')}",
        "name": name[:240],
        "provider_name": name[:240] if category == "doctor" else None,
        "category": category,
        "specialty": str(tags.get("healthcare:speciality") or tags.get("healthcare:specialty") or "")[:160],
        "address": _address_from_tags(tags),
        "city": str(tags.get("addr:city") or "")[:120],
        "district": str(tags.get("addr:district") or "")[:120],
        "state": str(tags.get("addr:state") or "")[:120],
        "postal_code": str(tags.get("addr:postcode") or "")[:40],
        "latitude": latitude,
        "longitude": longitude,
        "phone": str(tags.get("contact:phone") or tags.get("phone") or "")[:80],
        "website": str(tags.get("contact:website") or tags.get("website") or "")[:500],
        "opening_hours": str(tags.get("opening_hours") or "")[:240],
        "source": "openstreetmap_overpass",
        "source_id": "openstreetmap",
        "verification_status": "external_unverified",
        "bookable_in_zendoc": False,
        "map_url": f"https://www.openstreetmap.org/?mlat={latitude:.6f}&mlon={longitude:.6f}#map=17/{latitude:.6f}/{longitude:.6f}",
        "attribution": "OpenStreetMap contributors",
    }


class OverpassHealthcareProvider:
    source = "openstreetmap_overpass"

    def __init__(self, timeout_seconds=12):
        try:
            timeout = int(timeout_seconds or 12)
        except (TypeError, ValueError):
            timeout = 12
        self.timeout_seconds = max(3, min(timeout, 25))
        self.nominatim_url = os.environ.get("ZENDOC_NOMINATIM_URL", DEFAULT_NOMINATIM_URL).strip() or DEFAULT_NOMINATIM_URL
        self.overpass_url = os.environ.get("ZENDOC_OVERPASS_URL", DEFAULT_OVERPASS_URL).strip() or DEFAULT_OVERPASS_URL

    def search(self, query):
        query = dict(query or {})
        category = _clean_category(query.get("category"))
        latitude = _number(query.get("latitude"), -90, 90)
        longitude = _number(query.get("longitude"), -180, 180)
        location = str(query.get("location") or "").strip()[:160]
        radius = _radius_km(query.get("radius_km"))
        country_code = str(query.get("country_code") or "").strip().lower()[:2]

        if latitude is None or longitude is None:
            if not location:
                return {"available": True, "results": [], "message": "A location is required for broad OpenStreetMap healthcare discovery.", "source": self.source}
            center = self._geocode(location, country_code)
            if not center:
                return {"available": True, "results": [], "message": "OpenStreetMap could not resolve that location for nearby healthcare discovery.", "source": self.source}
            latitude, longitude = center

        cache_key = (category, round(latitude, 4), round(longitude, 4), radius)
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            payload = self._post_overpass(_overpass_query(category, latitude, longitude, radius * 1000))
            elements = payload.get("elements", []) if isinstance(payload, dict) else []
            results = []
            seen = set()
            for element in elements:
                item = _public_element(element, category)
                if not item:
                    continue
                key = (item["category"], item["name"].lower(), round(item["latitude"], 5), round(item["longitude"], 5))
                if key in seen:
                    continue
                seen.add(key)
                results.append(item)
            result = {
                "available": True,
                "results": results[:80],
                "message": None if results else "OpenStreetMap returned no tagged healthcare POIs near this location.",
                "source": self.source,
                "center": {"latitude": latitude, "longitude": longitude},
            }
            _cache_set(cache_key, result)
            return result
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
            return {
                "available": False,
                "results": [],
                "message": "OpenStreetMap nearby healthcare discovery is temporarily unavailable. No listings were fabricated.",
                "source": self.source,
            }

    def _geocode(self, location, country_code=""):
        global _LAST_GEOCODE_AT
        params = {"q": location, "format": "jsonv2", "limit": "1"}
        if country_code:
            params["countrycodes"] = country_code
        url = f"{self.nominatim_url}?{urllib.parse.urlencode(params)}"
        with _GEOCODE_LOCK:
            elapsed = time.monotonic() - _LAST_GEOCODE_AT
            if elapsed < 1.0:
                time.sleep(1.0 - elapsed)
            request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = response.read(262145)
            finally:
                _LAST_GEOCODE_AT = time.monotonic()
        if len(raw) > 262144:
            raise ValueError("Nominatim geocoding response exceeded the safe limit.")
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, list) or not payload:
            return None
        latitude = _number(payload[0].get("lat"), -90, 90)
        longitude = _number(payload[0].get("lon"), -180, 180)
        return (latitude, longitude) if latitude is not None and longitude is not None else None

    def _post_overpass(self, query_text):
        data = urllib.parse.urlencode({"data": query_text}).encode("utf-8")
        request = urllib.request.Request(
            self.overpass_url,
            data=data,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            raw = response.read(4_194_305)
        if len(raw) > 4_194_304:
            raise ValueError("Overpass response exceeded the safe limit.")
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Overpass returned an invalid response.")
        return payload
