from zendoc.db import get_db
from zendoc.places_provider import PlacesProvider, PlacesResult, UnconfiguredPlacesProvider
from zendoc.universal_health_search import universal_search
import zendoc.universal_health_search as health_search
from tests.test_milestone1 import login_web, make_app, register_web


def seed_verified_doctor(db):
    stamp = "2026-09-24T00:00:00+00:00"
    user_id = db.execute(
        """
        INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
        VALUES ('Dr Ananya Sen','ananya-findcare@example.test','ananya-findcare@example.test','unused','doctor',1,?,?)
        """,
        (stamp, stamp),
    ).lastrowid
    db.execute(
        """
        INSERT INTO provider_profiles
        (user_id,provider_type,specialty,organization,address,city,state,postal_code,verification_status,created_at,updated_at)
        VALUES (?,'doctor','Cardiology','Heart Care Clinic','Station Road','Kalyani','West Bengal','741235','verified',?,?)
        """,
        (user_id, stamp, stamp),
    )


def seed_public_pharmacy(db):
    stamp = "2026-09-24T00:00:00+00:00"
    db.execute(
        """
        INSERT INTO public_healthcare_entities
        (source_id,source_record_id,category,name,specialty,address,city,district,state,postal_code,active,created_at,updated_at)
        VALUES ('find-care-v2','PHARM-NATURAL-1','pharmacy','Kalyani Natural Pharmacy','','Test Road','Kalyani','Nadia','West Bengal','741235',1,?,?)
        """,
        (stamp, stamp),
    )


def test_natural_specialist_in_location_matches_verified_provider_without_external_maps(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        seed_verified_doctor(db)
        db.commit()
        result = universal_search(
            "cardiologist in Kalyani",
            places_provider=UnconfiguredPlacesProvider(),
        )

    doctors = result["grouped_results"]["doctor"]["results"]
    assert any(item["provider_name"] == "Dr Ananya Sen" for item in doctors)
    assert any(item["specialty"] == "Cardiology" for item in doctors)


def test_category_prefix_location_matches_public_directory_without_literal_phrase_bug(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        seed_public_pharmacy(db)
        db.commit()
        result = universal_search(
            "pharmacy Kalyani",
            places_provider=UnconfiguredPlacesProvider(),
        )

    pharmacies = result["grouped_results"]["pharmacy"]["results"]
    assert any(item["name"] == "Kalyani Natural Pharmacy" for item in pharmacies)


def test_find_care_aliases_redirect_authenticated_users_without_404(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "finder-alias-v2@example.com", "Finder Alias")
    login_web(client, "patient", "finder-alias-v2@example.com")

    simple = client.get("/nearby-care")
    assert simple.status_code == 302
    assert simple.headers["Location"].endswith("/finder")

    searched = client.get("/find-care?q=Kalyani&category=hospital")
    assert searched.status_code == 302
    assert "/universal-search?" in searched.headers["Location"]
    assert "q=Kalyani" in searched.headers["Location"]
    assert "category=hospital" in searched.headers["Location"]


class CountingNominatimProvider(PlacesProvider):
    source = "openstreetmap_nominatim"

    def __init__(self):
        self.calls = 0

    def search(self, query):
        self.calls += 1
        return PlacesResult(
            available=True,
            results=[{
                "id": "nominatim:hospital:1",
                "name": "Nominatim Fallback Hospital",
                "category": "hospital",
                "latitude": 22.901,
                "longitude": 88.401,
                "source": self.source,
                "verification_status": "external_unverified",
                "bookable_in_zendoc": False,
            }],
            source=self.source,
        )


def test_production_nominatim_path_avoids_duplicate_osm_request_when_overpass_succeeds(
    tmp_path,
    monkeypatch,
):
    app = make_app(tmp_path)
    provider = CountingNominatimProvider()
    osm_calls = []

    monkeypatch.setattr(health_search, "configured_places_provider", lambda: provider)

    def fake_osm(location, category, latitude, longitude, radius_km):
        osm_calls.append((location, category, latitude, longitude, radius_km))
        return ([{
            "id": "osm:hospital:1",
            "name": "Overpass Nearby Hospital",
            "category": "hospital",
            "latitude": 22.9005,
            "longitude": 88.4005,
            "source": "openstreetmap_overpass",
            "verification_status": "external_unverified",
            "bookable_in_zendoc": False,
        }], None)

    monkeypatch.setattr(health_search, "_osm_poi_results", fake_osm)

    with app.app_context():
        result = health_search.universal_search(
            "",
            category="hospital",
            latitude=22.9,
            longitude=88.4,
            radius_km=10,
        )

    assert len(osm_calls) == 1
    assert provider.calls == 0
    assert result["results"][0]["name"] == "Overpass Nearby Hospital"


def test_production_nominatim_path_falls_back_once_when_overpass_has_no_results(
    tmp_path,
    monkeypatch,
):
    app = make_app(tmp_path)
    provider = CountingNominatimProvider()
    monkeypatch.setattr(health_search, "configured_places_provider", lambda: provider)
    monkeypatch.setattr(
        health_search,
        "_osm_poi_results",
        lambda *_args, **_kwargs: (
            [],
            "OpenStreetMap returned no tagged healthcare POIs near this location.",
        ),
    )

    with app.app_context():
        result = health_search.universal_search(
            "",
            category="hospital",
            latitude=22.9,
            longitude=88.4,
            radius_km=10,
        )

    assert provider.calls == 1
    assert any(item["name"] == "Nominatim Fallback Hospital" for item in result["results"])
