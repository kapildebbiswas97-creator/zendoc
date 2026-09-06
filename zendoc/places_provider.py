import json
import os
import time
import urllib.error
import urllib.request


GOOGLE_NEARBY_SEARCH_URL = "https://places.googleapis.com/v1/places:searchNearby"
GOOGLE_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
GOOGLE_FIELD_MASK = ",".join(
    (
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.primaryType",
        "places.types",
        "places.googleMapsUri",
        "places.businessStatus",
    )
)

GOOGLE_CATEGORY_TYPES = {
    "hospital": ("hospital", "general_hospital", "medical_center"),
    "clinic": ("medical_clinic", "medical_center", "doctor"),
    "doctor": ("doctor", "medical_clinic"),
    "pharmacy": ("pharmacy", "drugstore"),
    "diagnostic_centre": ("medical_lab",),
    "laboratory": ("medical_lab",),
    "emergency": ("hospital", "general_hospital"),
}

GOOGLE_TEXT_CATEGORY = {
    "hospital": "hospital",
    "clinic": "medical_clinic",
    "doctor": "doctor",
    "pharmacy": "pharmacy",
    "diagnostic_centre": "medical_lab",
    "laboratory": "medical_lab",
    "emergency": "hospital",
}


class PlacesResult:
    def __init__(self, available, results=None, message=None, source="none"):
        self.available = available
        self.results = results or []
        self.message = message
        self.source = source

    def to_dict(self):
        return {
            "available": self.available,
            "results": self.results,
            "message": self.message,
            "source": self.source,
        }


class PlacesProvider:
    source = "base"

    def search(self, query):
        raise NotImplementedError


class UnconfiguredPlacesProvider(PlacesProvider):
    source = "unconfigured"

    def search(self, query):
        return PlacesResult(
            available=False,
            results=[],
            message="Nearby healthcare search is unavailable because no maps/places provider is configured. Enter a location manually or configure ZENDOC_PLACES_PROVIDER and its API key.",
            source=self.source,
        )


class GooglePlacesProvider(PlacesProvider):
    """Server-side adapter for Google Places API (New).

    The provider returns discovery data only. A result from Google Places is not a
    ZENDOC-verified provider, does not imply appointment connectivity, and must
    never be interpreted as live medicine stock, bed availability, or emergency
    dispatch readiness.
    """

    source = "google_places"

    def __init__(self, api_key, timeout_seconds=8):
        self.api_key = str(api_key or "").strip()
        self.timeout_seconds = max(1, min(int(timeout_seconds or 8), 20))

    def search(self, query):
        normalized = dict(query or {})
        latitude = _number(normalized.get("latitude"))
        longitude = _number(normalized.get("longitude"))
        location = str(normalized.get("location") or "").strip()

        if latitude is None or longitude is None:
            if not location:
                return PlacesResult(
                    available=True,
                    results=[],
                    message="Google Places is configured. Share a city/location or allow location access to search nearby healthcare providers.",
                    source=self.source,
                )
            url = GOOGLE_TEXT_SEARCH_URL
            body = self._text_search_body(normalized)
        else:
            url = GOOGLE_NEARBY_SEARCH_URL
            body = self._nearby_search_body(normalized, latitude, longitude)

        try:
            payload = self._post_json(url, body)
            places = payload.get("places", []) if isinstance(payload, dict) else []
            results = [
                _public_place(place, normalized)
                for place in places
                if isinstance(place, dict) and place.get("id")
            ]
            results = [item for item in results if item]
            message = None
            if not results:
                message = "Google Places returned no matching healthcare providers for this search."
            return PlacesResult(
                available=True,
                results=results,
                message=message,
                source=self.source,
            )
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            return PlacesResult(
                available=False,
                results=[],
                message=_safe_google_error_message(exc),
                source=self.source,
            )

    def _nearby_search_body(self, query, latitude, longitude):
        category = str(query.get("category") or "doctor").strip().lower()
        radius_km = _bounded_radius_km(query.get("radius_km"))
        return {
            "includedTypes": list(GOOGLE_CATEGORY_TYPES.get(category, GOOGLE_CATEGORY_TYPES["doctor"])),
            "maxResultCount": 20,
            "rankPreference": "DISTANCE",
            "regionCode": "IN",
            "languageCode": "en",
            "locationRestriction": {
                "circle": {
                    "center": {
                        "latitude": latitude,
                        "longitude": longitude,
                    },
                    "radius": radius_km * 1000.0,
                }
            },
        }

    def _text_search_body(self, query):
        category = str(query.get("category") or "doctor").strip().lower()
        specialty = str(query.get("specialty") or "").strip()
        location = str(query.get("location") or "").strip()
        human_category = category.replace("_", " ")
        terms = [term for term in (specialty, human_category, f"in {location}" if location else "") if term]
        return {
            "textQuery": " ".join(terms),
            "includedType": GOOGLE_TEXT_CATEGORY.get(category, "doctor"),
            "strictTypeFiltering": True,
            "pageSize": 20,
            "regionCode": "IN",
            "languageCode": "en",
        }

    def _post_json(self, url, body):
        if not self.api_key:
            raise ValueError("Google Places API key is missing.")
        request = urllib.request.Request(
            url,
            data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": GOOGLE_FIELD_MASK,
                "User-Agent": "ZENDOC/1.0 HealthcareFinder",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            raw = response.read(2_097_153)
        if len(raw) > 2_097_152:
            raise ValueError("Google Places response exceeded the safe response limit.")
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Google Places returned an invalid response.")
        return payload


def configured_places_provider():
    provider = os.environ.get("ZENDOC_PLACES_PROVIDER", "none").lower()
    if provider == "google" and os.environ.get("ZENDOC_GOOGLE_PLACES_API_KEY"):
        timeout = os.environ.get("ZENDOC_PLACES_TIMEOUT_SECONDS", "8")
        try:
            timeout = int(timeout)
        except (TypeError, ValueError):
            timeout = 8
        return GooglePlacesProvider(os.environ["ZENDOC_GOOGLE_PLACES_API_KEY"], timeout_seconds=timeout)
    return UnconfiguredPlacesProvider()


def _public_place(place, query):
    display_name = place.get("displayName")
    if isinstance(display_name, dict):
        name = str(display_name.get("text") or "").strip()
    else:
        name = str(display_name or "").strip()
    if not name:
        return None

    point = place.get("location") if isinstance(place.get("location"), dict) else {}
    category = str(query.get("category") or "doctor").strip().lower()
    return {
        "id": f"google:{place['id']}",
        "place_id": place["id"],
        "name": name,
        "category": category,
        "provider_type": place.get("primaryType") or category,
        "specialty": None,
        "search_specialty": str(query.get("specialty") or "").strip() or None,
        "address": place.get("formattedAddress") or "",
        "city": str(query.get("location") or "").strip(),
        "latitude": point.get("latitude"),
        "longitude": point.get("longitude"),
        "google_maps_url": place.get("googleMapsUri"),
        "business_status": place.get("businessStatus"),
        "types": list(place.get("types") or []),
        "verification_status": "external_unverified",
        "bookable_in_zendoc": False,
        "source": "google_places",
    }


def _number(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bounded_radius_km(value):
    try:
        radius = float(value or 10)
    except (TypeError, ValueError):
        radius = 10.0
    return max(1.0, min(radius, 50.0))


def _safe_google_error_message(exc):
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in {401, 403}:
            return "Google Places rejected the configured credentials or API permissions. Check the server-side API key and Places API (New) configuration."
        if exc.code == 429:
            return "Google Places rate or quota limit was reached. Try again later or review the configured Google Maps quota."
        return f"Google Places is temporarily unavailable (HTTP {exc.code}). No external provider data was fabricated."
    if isinstance(exc, TimeoutError):
        return "Google Places timed out. No external provider data was fabricated."
    if isinstance(exc, urllib.error.URLError):
        return "Google Places could not be reached. Check network connectivity and try again."
    return "Google Places returned an unusable response. No external provider data was fabricated."


class ShortLivedCache:
    def __init__(self, ttl_seconds=300):
        self.ttl_seconds = ttl_seconds
        self._items = {}

    def get(self, key):
        item = self._items.get(key)
        if not item:
            return None
        if time.time() - item["created"] > self.ttl_seconds:
            self._items.pop(key, None)
            return None
        return item["value"]

    def set(self, key, value):
        self._items[key] = {"created": time.time(), "value": value}
