from zendoc.places_provider import (
    FallbackPlacesProvider,
    GooglePlacesProvider,
    PlacesProvider,
    PlacesResult,
)
from zendoc.healthcare_finder import HealthcareFinder
from zendoc.universal_health_search import universal_search
import zendoc.routes as main_routes
import zendoc.universal_search_routes as universal_search_routes
from tests.test_milestone1 import login_web, make_app, register_web


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
