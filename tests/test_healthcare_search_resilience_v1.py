from zendoc.places_provider import (
    FallbackPlacesProvider,
    GooglePlacesProvider,
    PlacesProvider,
    PlacesResult,
)
from zendoc.healthcare_finder import HealthcareFinder
from zendoc.universal_health_search import universal_search
import zendoc.universal_health_search as universal_health_search
import zendoc.routes as main_routes
import zendoc.universal_search_routes as universal_search_routes
from tests.test_milestone1 import api_token, login_web, make_app, register_web


class ExplodingProvider(PlacesProvider):
    source = "exploding"

    def search(self, query):
        raise RuntimeError("upstream exploded")


class WorkingHospitalProvider(PlacesProvider):
    source = "working"

    def search(self, query):
        return PlacesResult(
            available=True,
            results=[
                {
                    "id": "working:hospital:1",
                    "name": "Resilient Test Hospital",
                    "category": "hospital",
                    "address": "Test Road",
                    "city": "Kalyani",
                    "state": "West Bengal",
                    "latitude": 22.9,
                    "longitude": 88.4,
                    "source": self.source,
                    "verification_status": "external_unverified",
                    "bookable_in_zendoc": False,
                }
            ],
            source=self.source,
        )


class CountingAllProvider(PlacesProvider):
    source = "counting"

    def __init__(self):
        self.calls = []

    def search(self, query):
        self.calls.append(dict(query))
        return PlacesResult(
            available=True,
            results=[
                {
                    "id": "counting:hospital:1",
                    "name": "Single Call Hospital",
                    "category": "hospital",
                    "latitude": 22.9005,
                    "longitude": 88.4005,
                    "source": self.source,
                    "verification_status": "external_unverified",
                    "bookable_in_zendoc": False,
                }
            ],
            source=self.source,
        )


class MalformedProvider(PlacesProvider):
    source = "malformed"

    def search(self, query):
        return PlacesResult(
            available=True,
            results=[
                None,
                "not-a-record",
                {
                    "id": "valid:hospital:1",
                    "name": "Valid Hospital",
                    "category": "hospital",
                    "latitude": 22.901,
                    "longitude": 88.401,
                    "source": self.source,
                    "verification_status": "external_unverified",
                    "bookable_in_zendoc": False,
                },
            ],
            source=self.source,
        )


def test_fallback_places_provider_survives_primary_exception():
    provider = FallbackPlacesProvider(ExplodingProvider(), WorkingHospitalProvider())

    result = provider.search(
        {
            "category": "hospital",
            "location": "Kalyani",
            "latitude": 22.9,
            "longitude": 88.4,
            "radius_km": 10,
        }
    )

    assert result.available is True
    assert result.results[0]["name"] == "Resilient Test Hospital"


def test_fallback_places_provider_survives_both_sources_throwing():
    provider = FallbackPlacesProvider(ExplodingProvider(), ExplodingProvider())

    result = provider.search({"category": "hospital", "location": "Kalyani"})

    assert result.available is False
    assert result.results == []
    assert "temporarily unavailable" in result.message.lower()


def test_all_healthcare_search_uses_one_external_provider_call(tmp_path):
    app = make_app(tmp_path)
    provider = CountingAllProvider()

    with app.app_context():
        result = universal_search(
            "",
            category="all",
            latitude=22.9,
            longitude=88.4,
            radius_km=10,
            places_provider=provider,
        )

    assert len(provider.calls) == 1
    assert provider.calls[0]["category"] == "all"
    assert result["results"]
    assert result["search_status"] == "complete"


def test_universal_search_returns_degraded_result_when_external_provider_throws(tmp_path):
    app = make_app(tmp_path)

    with app.app_context():
        result = universal_search(
            "",
            category="hospital",
            latitude=22.9,
            longitude=88.4,
            radius_km=10,
            places_provider=ExplodingProvider(),
        )

    assert result["search_status"] == "degraded"
    assert result["results"] == []
    assert result["warnings"]
    assert "temporarily unavailable" in result["warnings"][0].lower()
    assert result["search_origin"]["google_maps_url"].startswith(
        "https://www.google.com/maps/search/?api=1&query="
    )


def test_malformed_external_records_do_not_break_healthcare_search(tmp_path):
    app = make_app(tmp_path)

    with app.app_context():
        result = universal_search(
            "",
            category="hospital",
            latitude=22.9,
            longitude=88.4,
            radius_km=10,
            places_provider=MalformedProvider(),
        )

    assert len(result["results"]) == 1
    assert result["results"][0]["name"] == "Valid Hospital"
    assert result["results"][0]["distance_km"] < 1


def test_google_all_category_nearby_search_is_bounded_to_one_request_shape():
    provider = GooglePlacesProvider("test-key", timeout_seconds=3)

    body = provider._nearby_search_body(
        {"category": "all", "radius_km": 10},
        22.9,
        88.4,
    )

    assert len(body["includedTypes"]) >= 5
    assert "hospital" in body["includedTypes"]
    assert "doctor" in body["includedTypes"]
    assert "pharmacy" in body["includedTypes"]
    assert body["maxResultCount"] == 20


def test_google_all_category_text_search_does_not_force_wrong_single_type():
    provider = GooglePlacesProvider("test-key", timeout_seconds=3)

    body = provider._text_search_body(
        {
            "category": "all",
            "specialty": "",
            "location": "Kalyani",
        }
    )

    assert "healthcare" in body["textQuery"].lower()
    assert "includedType" not in body
    assert "strictTypeFiltering" not in body


def test_universal_search_route_returns_200_instead_of_500_on_catastrophic_failure(
    tmp_path,
    monkeypatch,
):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "search-resilience@example.com", "Search Resilience")
    login_web(client, "patient", "search-resilience@example.com")

    def fail_search(**_kwargs):
        raise RuntimeError("catastrophic search failure")

    monkeypatch.setattr(universal_search_routes, "universal_search", fail_search)

    response = client.get("/universal-search?q=hospital&category=hospital")

    assert response.status_code == 200
    assert b"Search temporarily limited" in response.data
    assert b"ZENDOC is still available" in response.data
    assert b"internal server error" not in response.data.lower()



def test_advanced_finder_service_failure_returns_200_not_500(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "advanced-finder-fail@example.com", "Advanced Finder")
    login_web(client, "patient", "advanced-finder-fail@example.com")

    def explode(_self, _query):
        raise RuntimeError("finder service unavailable")

    monkeypatch.setattr(HealthcareFinder, "search", explode)

    response = client.get("/finder?category=hospital&location=Kalyani")

    assert response.status_code == 200
    assert b"Search temporarily limited" in response.data
    assert b"ZENDOC is still available" in response.data
    assert b"Internal server error" not in response.data


def test_advanced_finder_results_survive_analytics_failure(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "analytics-fail@example.com", "Analytics Fail")
    login_web(client, "patient", "analytics-fail@example.com")

    fake_result = {
        "query": {
            "category": "hospital",
            "specialty": "",
            "location": "Kalyani",
            "latitude": None,
            "longitude": None,
            "radius_km": 10,
        },
        "registered_providers": [],
        "official_public_directory": [],
        "claimed_public_directory_links": [],
        "external_places": {
            "available": True,
            "results": [],
            "message": None,
            "source": "test",
        },
        "results": [
            {
                "id": "analytics-safe:1",
                "name": "Analytics Safe Hospital",
                "category": "hospital",
                "city": "Kalyani",
                "state": "West Bengal",
                "source": "external_test",
                "verification_status": "external_unverified",
                "bookable_in_zendoc": False,
            }
        ],
        "source_tiers": {
            "zendoc_verified": 0,
            "official_public_directory_not_zendoc_verified": 0,
            "approved_public_listings_merged_into_verified": 0,
            "external_unverified": 1,
        },
        "search_status": "complete",
        "warnings": [],
        "message": None,
    }

    monkeypatch.setattr(
        HealthcareFinder,
        "search",
        lambda _self, _query: fake_result,
    )
    monkeypatch.setattr(
        main_routes,
        "record_finder_search",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("analytics down")),
    )

    response = client.get("/finder?category=hospital&location=Kalyani")

    assert response.status_code == 200
    assert b"Analytics Safe Hospital" in response.data
    assert b"Internal server error" not in response.data


def test_advanced_finder_external_exception_becomes_degraded_result(tmp_path):
    app = make_app(tmp_path)

    with app.app_context():
        result = HealthcareFinder(places_provider=ExplodingProvider()).search(
            {
                "category": "hospital",
                "specialty": "",
                "location": "Kalyani",
                "latitude": None,
                "longitude": None,
                "radius_km": 10,
            }
        )

    assert result["search_status"] in {"partial", "degraded"}
    assert result["warnings"]
    assert "temporarily unavailable" in " ".join(result["warnings"]).lower()


class EmptyAvailableProvider(PlacesProvider):
    source = "empty-available"

    def search(self, query):
        return PlacesResult(
            available=True,
            results=[],
            message="No primary matches.",
            source=self.source,
        )


class UnavailableProvider(PlacesProvider):
    source = "unavailable"

    def search(self, query):
        return PlacesResult(
            available=False,
            results=[],
            message="Primary source temporarily unavailable.",
            source=self.source,
        )


def test_real_search_does_not_chain_overpass_after_primary_results(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    monkeypatch.setattr(
        universal_health_search,
        "configured_places_provider",
        lambda: WorkingHospitalProvider(),
    )

    called = {"osm": 0}

    def fail_if_osm(*args, **kwargs):
        called["osm"] += 1
        raise AssertionError("Overpass must not run after usable primary results")

    monkeypatch.setattr(universal_health_search, "_osm_poi_results", fail_if_osm)

    with app.app_context():
        result = universal_search(
            "hospital in Kalyani",
            category="all",
            radius_km=10,
        )

    assert called["osm"] == 0
    assert any(item["name"] == "Resilient Test Hospital" for item in result["results"])


def test_real_search_skips_second_remote_source_when_primary_is_unavailable(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    monkeypatch.setattr(
        universal_health_search,
        "configured_places_provider",
        lambda: UnavailableProvider(),
    )

    called = {"osm": 0}

    def fail_if_osm(*args, **kwargs):
        called["osm"] += 1
        raise AssertionError("A primary outage must not chain another remote timeout")

    monkeypatch.setattr(universal_health_search, "_osm_poi_results", fail_if_osm)

    with app.app_context():
        result = universal_search(
            "hospital in Kalyani",
            category="all",
            radius_km=10,
        )

    assert called["osm"] == 0
    assert result["search_status"] in {"partial", "degraded"}
    assert any("temporarily unavailable" in warning.lower() for warning in result["warnings"])


def test_real_search_uses_overpass_only_as_empty_success_fallback(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    monkeypatch.setattr(
        universal_health_search,
        "configured_places_provider",
        lambda: EmptyAvailableProvider(),
    )

    calls = []

    def fake_osm(location, category, latitude, longitude, radius_km):
        calls.append(
            {
                "location": location,
                "category": category,
                "latitude": latitude,
                "longitude": longitude,
                "radius_km": radius_km,
            }
        )
        return (
            [
                {
                    "id": "osm:fallback:1",
                    "name": "Fallback Kalyani Hospital",
                    "category": "hospital",
                    "city": "Kalyani",
                    "source": "openstreetmap_overpass",
                    "verification_status": "external_unverified",
                    "bookable_in_zendoc": False,
                }
            ],
            None,
        )

    monkeypatch.setattr(universal_health_search, "_osm_poi_results", fake_osm)

    with app.app_context():
        result = universal_search(
            "hospital in Kalyani",
            category="all",
            radius_km=10,
        )

    assert len(calls) == 1
    assert calls[0]["location"] == "Kalyani"
    assert calls[0]["category"] == "hospital"
    assert any(item["name"] == "Fallback Kalyani Hospital" for item in result["results"])


def test_natural_location_query_uses_location_and_inferred_category_for_internal_sources(
    tmp_path,
    monkeypatch,
):
    app = make_app(tmp_path)
    seen = {"registered": None, "public": None}

    def fake_registered(text, category, latitude, longitude, radius_km):
        seen["registered"] = (text, category)
        return []

    def fake_public(text, category, latitude, longitude, radius_km):
        seen["public"] = (text, category)
        return [
            {
                "id": 1,
                "name": "Kalyani Public Hospital",
                "category": "hospital",
                "city": "Kalyani",
                "source": "official_public_directory",
                "verification_status": "not_verified",
                "bookable_in_zendoc": False,
            }
        ]

    monkeypatch.setattr(universal_health_search, "_registered_matches", fake_registered)
    monkeypatch.setattr(universal_health_search, "_public_matches", fake_public)

    with app.app_context():
        result = universal_search(
            "hospital in Kalyani",
            category="all",
            places_provider=EmptyAvailableProvider(),
        )

    assert seen["registered"] == ("Kalyani", "hospital")
    assert seen["public"] == ("Kalyani", "hospital")
    assert result["results"][0]["name"] == "Kalyani Public Hospital"


def test_named_location_query_preserves_provider_name_for_internal_search(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    seen = []

    monkeypatch.setattr(
        universal_health_search,
        "_registered_matches",
        lambda text, category, latitude, longitude, radius_km: seen.append((text, category)) or [],
    )
    monkeypatch.setattr(
        universal_health_search,
        "_public_matches",
        lambda text, category, latitude, longitude, radius_km: [],
    )

    with app.app_context():
        universal_search(
            "Apollo Hospital in Kolkata",
            category="all",
            places_provider=EmptyAvailableProvider(),
        )

    assert seen == [("Apollo", "hospital")]


def test_healthcare_search_api_returns_degraded_json_instead_of_500(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    client = app.test_client()
    token = api_token(client, "api-search-resilience@example.com")

    monkeypatch.setattr(
        HealthcareFinder,
        "search",
        lambda _self, _query: (_ for _ in ()).throw(RuntimeError("finder upstream failed")),
    )

    response = client.get(
        "/api/v1/healthcare/search?category=hospital&location=Kalyani",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["search_status"] == "degraded"
    assert payload["results"] == []
    assert payload["warnings"]
    assert "temporarily limited" in payload["message"].lower()


def test_healthcare_search_api_results_survive_analytics_failure(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    client = app.test_client()
    token = api_token(client, "api-search-analytics@example.com")

    fake = {
        "query": {"category": "hospital", "location": "Kalyani"},
        "registered_providers": [],
        "official_public_directory": [],
        "claimed_public_directory_links": [],
        "external_places": {"available": True, "results": [], "message": None, "source": "test"},
        "results": [
            {
                "id": "safe:1",
                "name": "API Safe Hospital",
                "category": "hospital",
                "source": "external_test",
                "verification_status": "external_unverified",
                "bookable_in_zendoc": False,
            }
        ],
        "source_tiers": {
            "zendoc_verified": 0,
            "official_public_directory_not_zendoc_verified": 0,
            "approved_public_listings_merged_into_verified": 0,
            "external_unverified": 1,
        },
        "search_status": "complete",
        "warnings": [],
        "message": None,
    }
    monkeypatch.setattr(HealthcareFinder, "search", lambda _self, _query: fake)
    monkeypatch.setattr(
        main_routes,
        "record_finder_search",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("analytics unavailable")),
    )

    response = client.get(
        "/api/v1/healthcare/search?category=hospital&location=Kalyani",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["results"][0]["name"] == "API Safe Hospital"
    assert payload["search_status"] == "complete"


def test_provider_discovery_api_returns_degraded_json_instead_of_500(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    client = app.test_client()
    token = api_token(client, "api-provider-resilience@example.com")

    monkeypatch.setattr(
        HealthcareFinder,
        "search",
        lambda _self, _query: (_ for _ in ()).throw(RuntimeError("provider discovery failed")),
    )

    response = client.get(
        "/api/v1/providers?category=doctor&location=Kalyani",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["search_status"] == "degraded"
    assert payload["results"] == []
    assert "temporarily limited" in payload["message"].lower()
