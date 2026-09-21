from pathlib import Path
import re

from zendoc.places_provider import PlacesProvider, PlacesResult
from zendoc.universal_health_search import universal_search
from tests.test_milestone1 import login_web, make_app, register_web


ROOT = Path(__file__).resolve().parents[1]


class NearbyHospitalProvider(PlacesProvider):
    source = "test_external_places"

    def search(self, query):
        return PlacesResult(
            available=True,
            results=[
                {
                    "id": "external:hospital:1",
                    "name": "Nearby Test Hospital",
                    "category": "hospital",
                    "address": "Nearby Road",
                    "city": "Kalyani",
                    "state": "West Bengal",
                    "latitude": 22.901,
                    "longitude": 88.401,
                    "source": self.source,
                    "verification_status": "external_unverified",
                    "bookable_in_zendoc": False,
                }
            ],
            source=self.source,
        )


def test_current_location_button_submits_own_finder_form():
    script = (ROOT / "static" / "finder.js").read_text(encoding="utf-8")

    assert 'button.closest("form")' in script
    assert 'form.requestSubmit()' in script
    assert "Location found. Searching nearby care..." in script


def test_service_worker_invalidates_old_static_cache_and_precaches_finder_assets():
    script = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")

    match = re.search(r'const STATIC_CACHE = "zendoc-static-v(\\d+)[^"]*";', script)
    assert match is not None
    assert int(match.group(1)) >= 4
    assert 'zendoc-static-v1' not in script
    assert 'zendoc-static-v2' not in script
    assert 'zendoc-static-v3' not in script
    assert '"/static/finder.js"' in script
    assert '"/static/product-expansion.css"' in script
    assert '"/static/edgecare_voice.js"' in script


def test_gps_universal_search_returns_distance_and_google_maps_handoff(tmp_path):
    app = make_app(tmp_path)

    with app.app_context():
        result = universal_search(
            "",
            category="hospital",
            latitude=22.9,
            longitude=88.4,
            radius_km=10,
            places_provider=NearbyHospitalProvider(),
        )

    hospital = result["grouped_results"]["hospital"]["results"][0]
    assert hospital["name"] == "Nearby Test Hospital"
    assert 0 < hospital["distance_km"] < 1
    assert hospital["google_maps_url"].startswith(
        "https://www.google.com/maps/search/?api=1&query="
    )
    assert hospital["google_directions_url"].startswith(
        "https://www.google.com/maps/dir/?api=1&origin="
    )
    assert result["search_origin"]["google_maps_url"].startswith(
        "https://www.google.com/maps/search/?api=1&query="
    )
    assert hospital["bookable_in_zendoc"] is False
    assert hospital["verification_status"] == "external_unverified"


def test_patient_navigation_surfaces_messages_wellness_payments_and_shop(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "hotfix-visibility@example.com", "Hotfix Visibility")
    login_web(client, "patient", "hotfix-visibility@example.com")

    response = client.get("/dashboard")
    assert response.status_code == 200
    body = response.data.decode()

    assert 'href="/messages"' in body
    assert "Message care team" in body
    assert 'href="/mental-wellness"' in body
    assert "Mental Wellness" in body
    assert 'href="/payments"' in body
    assert ">Payments<" in body
    assert 'href="/health-shop"' in body
    assert "Health Shop" in body
