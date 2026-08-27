import os
import time


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
    source = "google_places"

    def __init__(self, api_key):
        self.api_key = api_key

    def search(self, query):
        # Network integration is intentionally not live in this milestone. Credentials stay server-side.
        return PlacesResult(
            available=False,
            results=[],
            message="Google Places is configured for future integration, but live external calls are disabled in this MVP environment.",
            source=self.source,
        )


def configured_places_provider():
    provider = os.environ.get("ZENDOC_PLACES_PROVIDER", "none").lower()
    if provider == "google" and os.environ.get("ZENDOC_GOOGLE_PLACES_API_KEY"):
        return GooglePlacesProvider(os.environ["ZENDOC_GOOGLE_PLACES_API_KEY"])
    return UnconfiguredPlacesProvider()


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
