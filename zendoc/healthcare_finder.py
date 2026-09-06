from .places_provider import ShortLivedCache, configured_places_provider
from .provider_service import search_registered_providers
from .public_data_ingestion import search_public_healthcare_entities


CATEGORIES = {"hospital", "clinic", "doctor", "pharmacy", "diagnostic_centre", "laboratory", "emergency"}
_CACHE = ShortLivedCache(ttl_seconds=300)


def normalize_query(category=None, specialty=None, location=None, latitude=None, longitude=None, radius_km=10):
    category = (category or "doctor").strip().lower().replace(" ", "_")
    if category not in CATEGORIES:
        category = "doctor"
    try:
        radius_km = max(1, min(50, int(radius_km or 10)))
    except (TypeError, ValueError):
        radius_km = 10
    lat = parse_coordinate(latitude, -90, 90)
    lng = parse_coordinate(longitude, -180, 180)
    return {
        "category": category,
        "specialty": (specialty or "").strip(),
        "location": (location or "").strip(),
        "latitude": lat,
        "longitude": lng,
        "radius_km": radius_km,
    }


def parse_coordinate(value, minimum, maximum):
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < minimum or number > maximum:
        return None
    return number


class HealthcareFinder:
    def __init__(self, places_provider=None):
        self.places_provider = places_provider or configured_places_provider()

    def search(self, query):
        normalized = normalize_query(**query)
        cache_key = tuple(sorted(normalized.items()))
        cached = _CACHE.get(cache_key)
        if cached:
            return cached

        registered = search_registered_providers(
            category="doctor" if normalized["category"] in {"doctor", "clinic"} else normalized["category"],
            specialty=normalized["specialty"],
            location=normalized["location"],
        )
        public_directory = search_public_healthcare_entities(
            category=normalized["category"],
            specialty=normalized["specialty"],
            location=normalized["location"],
            limit=25,
        )
        places_result = self.places_provider.search(normalized)
        response = {
            "query": normalized,
            "registered_providers": registered,
            "official_public_directory": public_directory,
            "external_places": places_result.to_dict(),
            "results": registered + public_directory + places_result.results,
            "source_tiers": {
                "zendoc_verified": len(registered),
                "official_public_directory_not_zendoc_verified": len(public_directory),
                "external_unverified": len(places_result.results),
            },
            "message": None,
        }
        if not response["results"]:
            response["message"] = places_result.message or "No healthcare providers were found for this search."
        _CACHE.set(cache_key, response)
        return response
