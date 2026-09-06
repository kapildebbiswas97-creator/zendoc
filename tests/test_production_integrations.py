import json
import urllib.error

from zendoc.places_provider import GooglePlacesProvider, UnconfiguredPlacesProvider


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit=-1):
        return self.payload if limit is None or limit < 0 else self.payload[:limit]


def test_unconfigured_places_provider_is_truthful():
    result = UnconfiguredPlacesProvider().search({"category": "hospital"})
    assert result.available is False
    assert result.results == []
    assert "configure" in result.message.lower()


def test_google_places_nearby_search_maps_real_provider_data(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse({
            "places": [{
                "id": "place-123",
                "displayName": {"text": "Example Medical Centre"},
                "formattedAddress": "Kolkata, West Bengal, India",
                "location": {"latitude": 22.57, "longitude": 88.36},
                "primaryType": "hospital",
                "types": ["hospital", "health"],
                "googleMapsUri": "https://maps.google.com/?cid=123",
                "businessStatus": "OPERATIONAL",
            }]
        })

    monkeypatch.setattr("zendoc.places_provider.urllib.request.urlopen", fake_urlopen)
    result = GooglePlacesProvider("server-key", timeout_seconds=4).search({
        "category": "hospital",
        "specialty": "",
        "location": "Kolkata",
        "latitude": 22.57,
        "longitude": 88.36,
        "radius_km": 10,
    })

    assert result.available is True
    assert len(result.results) == 1
    place = result.results[0]
    assert place["name"] == "Example Medical Centre"
    assert place["source"] == "google_places"
    assert place["verification_status"] == "external_unverified"
    assert place["bookable_in_zendoc"] is False
    assert captured["url"].endswith("/v1/places:searchNearby")
    assert captured["body"]["rankPreference"] == "DISTANCE"
    assert captured["body"]["locationRestriction"]["circle"]["radius"] == 10000.0


def test_google_places_text_search_uses_location_when_coordinates_missing(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse({"places": []})

    monkeypatch.setattr("zendoc.places_provider.urllib.request.urlopen", fake_urlopen)
    result = GooglePlacesProvider("server-key").search({
        "category": "doctor",
        "specialty": "Cardiology",
        "location": "Kolkata",
        "latitude": None,
        "longitude": None,
        "radius_km": 10,
    })

    assert result.available is True
    assert captured["url"].endswith("/v1/places:searchText")
    assert captured["body"]["includedType"] == "doctor"
    assert "Cardiology" in captured["body"]["textQuery"]
    assert "Kolkata" in captured["body"]["textQuery"]


def test_google_places_failure_never_fabricates_results(monkeypatch):
    def denied(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            "https://places.googleapis.com/v1/places:searchText",
            403,
            "forbidden",
            {},
            None,
        )

    monkeypatch.setattr("zendoc.places_provider.urllib.request.urlopen", denied)
    result = GooglePlacesProvider("bad-key").search({
        "category": "pharmacy",
        "location": "Kolkata",
    })

    assert result.available is False
    assert result.results == []
    assert "credentials" in result.message.lower()
