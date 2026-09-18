from urllib.parse import parse_qs, urlparse

from zendoc.osm_healthcare import OverpassHealthcareProvider, _overpass_query, _public_element
from zendoc.universal_health_search import _text_parts
from zendoc.video_provider import NullVideoProvider, _youtube_search_url


def test_natural_pharmacy_location_shorthand_is_understood():
    term, location, category = _text_parts("pharmacy Kalyani")
    assert term == "pharmacy Kalyani"
    assert location == "Kalyani"
    assert category == "pharmacy"


def test_competition_kalyani_healthcare_queries_are_understood():
    cases = {
        "pharmacy Kalyani": ("Kalyani", "pharmacy"),
        "medical store Kalyani": ("Kalyani", "pharmacy"),
        "clinics in Kalyani": ("Kalyani", "clinic"),
        "hospitals in Kalyani": ("Kalyani", "hospital"),
        "cardiologist in Kalyani": ("Kalyani", "doctor"),
    }
    for query, expected in cases.items():
        _term, location, category = _text_parts(query)
        assert (location, category) == expected


def test_named_hospital_search_is_not_misread_as_location():
    term, location, category = _text_parts("Apollo Hospital")
    assert term == "Apollo Hospital"
    assert location == ""
    assert category == "hospital"


def test_overpass_query_is_bounded_to_requested_healthcare_category():
    query = _overpass_query("pharmacy", 22.975, 88.434, 10000)
    assert "around:10000,22.975000,88.434000" in query
    assert '["amenity"="pharmacy"]' in query
    assert '["healthcare"="pharmacy"]' in query
    assert "hospital" not in query


def test_osm_element_remains_external_and_unbookable():
    result = _public_element(
        {
            "type": "node",
            "id": 123,
            "lat": 22.975,
            "lon": 88.434,
            "tags": {
                "name": "Example Medical Store",
                "amenity": "pharmacy",
                "addr:city": "Kalyani",
                "phone": "+91 00000 00000",
            },
        },
        "pharmacy",
    )
    assert result["category"] == "pharmacy"
    assert result["source"] == "openstreetmap_overpass"
    assert result["bookable_in_zendoc"] is False
    assert result["verification_status"] == "external_unverified"
    assert "openstreetmap.org" in result["map_url"]


def test_overpass_provider_normalizes_fake_response_without_network(monkeypatch):
    provider = OverpassHealthcareProvider()
    monkeypatch.setattr(provider, "_geocode", lambda location, country_code="": (22.975, 88.434))
    monkeypatch.setattr(
        provider,
        "_post_overpass",
        lambda query: {
            "elements": [
                {"type": "node", "id": 1, "lat": 22.975, "lon": 88.434, "tags": {"name": "Alpha Pharmacy", "amenity": "pharmacy"}},
                {"type": "node", "id": 2, "lat": 22.976, "lon": 88.435, "tags": {"name": "Beta Pharmacy", "amenity": "pharmacy"}},
            ]
        },
    )
    result = provider.search({"category": "pharmacy", "location": "Kalyani", "radius_km": 10})
    assert result["available"] is True
    assert [item["name"] for item in result["results"]] == ["Alpha Pharmacy", "Beta Pharmacy"]


def test_video_fallback_uses_exact_topic_not_forced_fitness_suffix():
    url = _youtube_search_url("inhaler technique patient education")
    query = parse_qs(urlparse(url).query)["search_query"][0]
    assert query == "inhaler technique patient education"
    assert "fitness tutorial" not in query


def test_null_video_provider_exposes_real_youtube_search_handoff():
    result = NullVideoProvider().search("knee rehabilitation patient education")
    assert result["available"] is False
    assert result["results"] == []
    assert result["search_provider"] == "youtube_web_search"
    assert result["search_url"].startswith("https://www.youtube.com/results?search_query=")
