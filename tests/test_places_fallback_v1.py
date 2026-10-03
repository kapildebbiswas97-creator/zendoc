import os

from zendoc.places_provider import (
    FallbackPlacesProvider,
    GooglePlacesProvider,
    HealthsitesPlacesProvider,
    NominatimPlacesProvider,
    PlacesProvider,
    PlacesResult,
    configured_places_provider,
)


class FakePrimary(PlacesProvider):
    source = "fake-primary"

    def __init__(self, result):
        self.result = result

    def search(self, query):
        return self.result


class FakeFallback(PlacesProvider):
    source = "fake-fallback"

    def __init__(self, result):
        self.result = result
        self.calls = 0

    def search(self, query):
        self.calls += 1
        return self.result


def test_configured_google_without_key_uses_nominatim_fallback(monkeypatch):
    monkeypatch.setenv("ZENDOC_PLACES_PROVIDER", "google")
    monkeypatch.delenv("ZENDOC_GOOGLE_PLACES_API_KEY", raising=False)

    provider = configured_places_provider()

    assert isinstance(provider, NominatimPlacesProvider)


def test_configured_google_with_key_uses_google_then_nominatim(monkeypatch):
    monkeypatch.setenv("ZENDOC_PLACES_PROVIDER", "google")
    monkeypatch.setenv("ZENDOC_GOOGLE_PLACES_API_KEY", "test-key")

    provider = configured_places_provider()

    assert isinstance(provider, FallbackPlacesProvider)
    assert isinstance(provider.primary, GooglePlacesProvider)
    assert isinstance(provider.fallback, NominatimPlacesProvider)


def test_fallback_provider_prefers_primary_results():
    primary = FakePrimary(
        PlacesResult(
            available=True,
            results=[{"id": "google:1", "name": "Primary Hospital"}],
            source="google_places",
        )
    )
    fallback = FakeFallback(
        PlacesResult(
            available=True,
            results=[{"id": "osm:1", "name": "Fallback Hospital"}],
            source="openstreetmap_nominatim",
        )
    )

    result = FallbackPlacesProvider(primary, fallback).search({"location": "Kalyani"})

    assert result.results[0]["name"] == "Primary Hospital"
    assert fallback.calls == 0


def test_fallback_provider_uses_secondary_when_primary_empty():
    primary = FakePrimary(
        PlacesResult(
            available=True,
            results=[],
            message="No Google matches.",
            source="google_places",
        )
    )
    fallback = FakeFallback(
        PlacesResult(
            available=True,
            results=[{"id": "osm:1", "name": "Fallback Hospital"}],
            source="openstreetmap_nominatim",
        )
    )

    result = FallbackPlacesProvider(primary, fallback).search({"location": "Kalyani"})

    assert result.results[0]["name"] == "Fallback Hospital"
    assert fallback.calls == 1


def test_nominatim_search_returns_external_unverified_non_bookable_results(monkeypatch):
    provider = NominatimPlacesProvider(timeout_seconds=1)

    monkeypatch.setattr(
        provider,
        "_get_json",
        lambda _url: [
            {
                "place_id": 101,
                "osm_type": "node",
                "osm_id": 202,
                "display_name": "Kalyani General Hospital, Kalyani, Nadia, West Bengal, India",
                "lat": "22.9750",
                "lon": "88.4345",
                "type": "hospital",
                "category": "amenity",
                "address": {
                    "amenity": "Kalyani General Hospital",
                    "city": "Kalyani",
                    "state": "West Bengal",
                    "postcode": "741235",
                },
                "extratags": {"phone": "+91 12345 67890"},
                "namedetails": {"name": "Kalyani General Hospital"},
            }
        ],
    )

    result = provider.search(
        {
            "category": "hospital",
            "specialty": "",
            "location": "Kalyani",
            "latitude": None,
            "longitude": None,
            "radius_km": 10,
        }
    )

    assert result.available is True
    assert len(result.results) == 1
    item = result.results[0]
    assert item["name"] == "Kalyani General Hospital"
    assert item["source"] == "openstreetmap_nominatim"
    assert item["verification_status"] == "external_unverified"
    assert item["bookable_in_zendoc"] is False
    assert item["claimable_public_listing"] is False
    assert item["map_url"] == "https://www.openstreetmap.org/node/202"
    assert item["attribution"] == "© OpenStreetMap contributors"


def test_nominatim_retries_broader_category_when_specialty_query_is_empty(monkeypatch):
    provider = NominatimPlacesProvider(timeout_seconds=1)
    requested = []

    def fake_get_json(url):
        requested.append(url)
        if len(requested) == 1:
            return []
        return [{
            "place_id": 301,
            "osm_type": "node",
            "osm_id": 302,
            "display_name": "Kalyani Heart Clinic, Kalyani, West Bengal, India",
            "lat": "22.9750",
            "lon": "88.4345",
            "type": "clinic",
            "category": "amenity",
            "address": {
                "amenity": "Kalyani Heart Clinic",
                "city": "Kalyani",
                "state": "West Bengal",
            },
            "namedetails": {"name": "Kalyani Heart Clinic"},
        }]

    monkeypatch.setattr(provider, "_get_json", fake_get_json)

    result = provider.search(
        {
            "category": "doctor",
            "specialty": "Cardiology",
            "location": "Kalyani",
            "latitude": None,
            "longitude": None,
            "radius_km": 10,
        }
    )

    assert result.available is True
    assert len(result.results) == 1
    assert result.results[0]["name"] == "Kalyani Heart Clinic"
    assert len(requested) == 2
    assert "Cardiology+doctor+in+Kalyani" in requested[0]
    assert "doctor+in+Kalyani" in requested[1]


def test_nominatim_accepts_gps_only_search_for_beta_fallback(monkeypatch):
    provider = NominatimPlacesProvider(timeout_seconds=1)
    requested = []

    def fake_get_json(url):
        requested.append(url)
        return [{
            "place_id": 101,
            "osm_type": "node",
            "osm_id": 202,
            "display_name": "Nearby Clinic, India",
            "lat": "22.9001",
            "lon": "88.4001",
            "type": "clinic",
            "address": {"city": "Kalyani"},
        }]

    monkeypatch.setattr(provider, "_get_json", fake_get_json)

    result = provider.search(
        {
            "category": "doctor",
            "specialty": "",
            "location": "",
            "latitude": 22.9,
            "longitude": 88.4,
            "radius_km": 10,
        }
    )

    assert result.available is True
    assert result.results[0]["source"] == "openstreetmap_nominatim"
    assert requested and "near+22.900000%2C+88.400000" in requested[0]



def test_configured_healthsites_with_key_uses_healthsites_then_nominatim(monkeypatch):
    monkeypatch.setenv("ZENDOC_PLACES_PROVIDER", "healthsites")
    monkeypatch.setenv("ZENDOC_HEALTHSITES_API_KEY", "healthsites-test-key")

    provider = configured_places_provider()

    assert isinstance(provider, FallbackPlacesProvider)
    assert isinstance(provider.primary, HealthsitesPlacesProvider)
    assert isinstance(provider.fallback, NominatimPlacesProvider)


def test_google_chain_uses_healthsites_before_nominatim_when_both_keys_exist(monkeypatch):
    monkeypatch.setenv("ZENDOC_PLACES_PROVIDER", "google")
    monkeypatch.setenv("ZENDOC_GOOGLE_PLACES_API_KEY", "google-test-key")
    monkeypatch.setenv("ZENDOC_HEALTHSITES_API_KEY", "healthsites-test-key")

    provider = configured_places_provider()

    assert isinstance(provider, FallbackPlacesProvider)
    assert isinstance(provider.primary, GooglePlacesProvider)
    assert isinstance(provider.fallback, FallbackPlacesProvider)
    assert isinstance(provider.fallback.primary, HealthsitesPlacesProvider)
    assert isinstance(provider.fallback.fallback, NominatimPlacesProvider)


def test_healthsites_gps_search_is_external_unverified_and_bounded(monkeypatch):
    provider = HealthsitesPlacesProvider("healthsites-test-key", timeout_seconds=1)
    seen = []

    def fake_get_json(url):
        seen.append(url)
        return {
            "type": "FeatureCollection",
            "features": [{
                "id": "node-123",
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [88.4347, 22.9752]},
                "properties": {
                    "name": "Global Test Hospital",
                    "amenity": "hospital",
                    "osm_type": "node",
                    "osm_id": 123,
                    "addr_city": "Kalyani",
                    "addr_state": "West Bengal",
                },
            }],
        }

    monkeypatch.setattr(provider, "_get_json", fake_get_json)
    result = provider.search({
        "category": "hospital",
        "location": "",
        "latitude": 22.975,
        "longitude": 88.434,
        "radius_km": 10,
    })

    assert result.available is True
    assert len(result.results) == 1
    item = result.results[0]
    assert item["name"] == "Global Test Hospital"
    assert item["source"] == "healthsites_api"
    assert item["verification_status"] == "external_unverified"
    assert item["bookable_in_zendoc"] is False
    assert item["map_url"] == "https://www.openstreetmap.org/node/123"
    assert seen and "extent=" in seen[0]
    assert "api-key=healthsites-test-key" in seen[0]
