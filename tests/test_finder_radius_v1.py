"""Nearby discovery regressions use synthetic fixtures, never public data."""
import math
import urllib.error
from urllib.parse import parse_qs, urlsplit

import pytest

from tests.test_milestone1 import make_app
from zendoc.db import get_db
from zendoc.geospatial import EARTH_RADIUS_KM, bounding_box, haversine_km
from zendoc.healthcare_finder import HealthcareFinder, normalize_query
from zendoc.places_provider import NominatimPlacesProvider, UnconfiguredPlacesProvider
from zendoc.provider_service import search_registered_providers
from zendoc.public_data_ingestion import search_public_healthcare_entities


def seed_provider(db, key, latitude, longitude, updated="2026-09-01T00:00:00Z"):
    email = f"radius-{key}@example.test"
    user_id = db.execute(
        "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) "
        "VALUES (?,?,?,'unused','doctor',1,?,?)",
        (f"Doctor {key}", email, email, updated, updated),
    ).lastrowid
    return int(db.execute(
        "INSERT INTO provider_profiles (user_id,provider_type,organization,city,state,latitude,longitude,"
        "verification_status,created_at,updated_at) VALUES (?,'doctor',?,'Kalyani','West Bengal',?,?,'verified',?,?)",
        (user_id, f"Clinic {key}", latitude, longitude, updated, updated),
    ).lastrowid)


def seed_public(db, key, latitude, longitude, updated="2026-09-01T00:00:00Z"):
    return int(db.execute(
        "INSERT INTO public_healthcare_entities (source_id,source_record_id,category,name,city,state,latitude,longitude,"
        "created_at,updated_at) VALUES ('data_gov_hospitals',?,'doctor',?,'Kalyani','West Bengal',?,?,?,?)",
        (key, f"Public clinic {key}", latitude, longitude, updated, updated),
    ).lastrowid)


def test_gps_only_search_filters_all_database_tiers_without_promoting_public_data(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        for key, lat, lon in (("near", 22.901, 88.4), ("far", 28.6, 77.2), ("unknown", None, None)):
            seed_provider(db, key, lat, lon)
            seed_public(db, key, lat, lon)
        db.commit()
        result = HealthcareFinder(UnconfiguredPlacesProvider()).search(
            {"category": "doctor", "latitude": 22.9, "longitude": 88.4, "radius_km": 5}
        )
        assert [r["name"] for r in result["registered_providers"]] == ["Clinic near"]
        assert [r["name"] for r in result["official_public_directory"]] == ["Public clinic near"]
        public = result["official_public_directory"][0]
        assert public["verification_status"] == "not_verified"
        assert public["bookable_in_zendoc"] is False
        assert 0 < public["distance_km"] < 5
        assert result["source_tiers"]["zendoc_verified"] == 1
        # Manual searches still include listings whose coordinates are unknown.
        manual = search_public_healthcare_entities(category="doctor", location="Kalyani")
        assert len(manual) == 3


def test_nearest_results_are_selected_before_legacy_candidate_limits(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        for number in range(405):
            seed_public(db, f"far-{number:04d}", 22.92, 88.4)
            if number < 105:
                seed_provider(db, f"far-{number:04d}", 22.92, 88.4)
        old = "2020-01-01T00:00:00Z"
        seed_provider(db, "nearest", 22.90001, 88.4, old)
        seed_public(db, "nearest", 22.90001, 88.4, old)
        db.commit()
        query = dict(category="doctor", latitude=22.9, longitude=88.4, radius_km=5)
        registered = search_registered_providers(**query)
        public = search_public_healthcare_entities(**query)
        assert len(registered) == len(public) == 25
        assert registered[0]["name"] == "Clinic nearest"
        assert public[0]["name"] == "Public clinic nearest"
        assert [r["distance_km"] for r in public] == sorted(r["distance_km"] for r in public)
        assert [r["id"] for r in public] == [r["id"] for r in search_public_healthcare_entities(**query)]


@pytest.mark.parametrize("origin,point", [
    ((22.9, 88.4), (22.9 + math.degrees(5 / EARTH_RADIUS_KM), 88.4)),
    ((0, 179.99), (0, -179.99)),
    ((89.99, 0), (89.99, 90)),
])
def test_bounding_candidates_include_radius_edge_dateline_and_pole(tmp_path, origin, point):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        seed_provider(db, "edge", *point)
        seed_public(db, "edge", *point)
        db.commit()
        query = dict(category="doctor", latitude=origin[0], longitude=origin[1], radius_km=5)
        assert len(search_registered_providers(**query)) == 1
        assert len(search_public_healthcare_entities(**query)) == 1
        assert haversine_km(*origin, *point) <= 5 + 1e-9


@pytest.mark.parametrize("latitude,longitude", [("nan", 88.4), ("inf", 88.4), (91, 88.4), (22.9, 181), ("bad", 88.4), (22.9, None)])
def test_invalid_gps_does_not_turn_into_an_unbounded_database_search(monkeypatch, latitude, longitude):
    def fail(**kwargs):
        raise AssertionError("Invalid GPS must not query global provider rows")
    monkeypatch.setattr("zendoc.healthcare_finder.search_registered_providers", fail)
    monkeypatch.setattr("zendoc.healthcare_finder.search_public_healthcare_entities", fail)
    normalized = normalize_query(latitude=latitude, longitude=longitude, radius_km=float("inf"))
    assert normalized["latitude"] is normalized["longitude"] is None
    assert normalized["radius_km"] == 10
    result = HealthcareFinder(UnconfiguredPlacesProvider()).search({"latitude": latitude, "longitude": longitude})
    assert result["results"] == []
    assert "valid current location" in result["message"]


def test_osm_radius_is_bounded_and_filters_distant_or_unknown_coordinates(monkeypatch):
    provider = NominatimPlacesProvider()
    urls = []
    def response(url):
        urls.append(url)
        return [
            {"place_id": number, "osm_type": "node", "osm_id": number, "type": "clinic", "display_name": name,
             "lat": lat, "lon": lon, "address": {"city": "Kalyani"}}
            for number, name, lat, lon in [(1, "Far", "28.6", "77.2"), (2, "Near", "22.901", "88.4"), (3, "Unknown", "nan", "88.4")]
        ]
    monkeypatch.setattr(provider, "_get_json", response)
    result = provider.search({"category": "doctor", "latitude": 22.9, "longitude": 88.4, "radius_km": 5})
    assert len(result.results) == 1
    assert result.results[0]["name"] == "Near"
    assert result.results[0]["bookable_in_zendoc"] is False
    params = parse_qs(urlsplit(urls[0]).query)
    assert params["bounded"] == ["1"]
    assert "viewbox" in params


def test_osm_radius_outage_is_retried(monkeypatch):
    provider = NominatimPlacesProvider()
    calls = []
    def response(url):
        calls.append(url)
        if len(calls) == 1:
            raise urllib.error.URLError("temporary outage")
        return []
    monkeypatch.setattr(provider, "_get_json", response)
    query = {"category": "doctor", "latitude": 22.9, "longitude": 88.4, "radius_km": 5}
    assert provider.search(query).available is False
    assert provider.search(query).available is True
    assert len(calls) == 2


def test_invalid_helper_coordinates_are_rejected():
    with pytest.raises(ValueError):
        bounding_box(float("nan"), 88.4, 5)
    assert haversine_km(22.9, 88.4, "nan", 88.4) is None

