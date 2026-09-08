from zendoc.public_data_ingestion import ingest_public_records
from tests.test_milestone1 import csrf, login_web, make_client, register_web


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def test_readiness_reports_safe_finder_mode_without_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENDOC_PLACES_PROVIDER", "google")
    monkeypatch.delenv("ZENDOC_GOOGLE_PLACES_API_KEY", raising=False)
    _app, client = make_client(tmp_path)

    response = client.get("/api/v1/ready")

    assert response.status_code == 200
    payload = response.get_json()
    finder = payload["healthcare_finder"]
    assert finder["configured_provider"] == "google"
    assert finder["mode"] == "openstreetmap_fallback_google_key_missing"
    assert finder["google_places_key_configured"] is False
    assert finder["external_discovery_available"] is True
    assert "API credentials" in finder["truth_notice"]
    assert "GOOGLE_PLACES_API_KEY" not in response.data.decode()


def test_patient_finder_renders_official_result_and_source_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENDOC_PLACES_PROVIDER", "none")
    app, client = make_client(tmp_path)

    with app.app_context():
        ingest_public_records(
            owner_actor(),
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
            records=[{
                "source_record_id": "LAUNCH-FINDER-HOSPITAL-1",
                "category": "hospital",
                "name": "Launch Quality Hospital",
                "address": "Station Road",
                "city": "Kalyani",
                "district": "Nadia",
                "state": "West Bengal",
                "postal_code": "741235",
                "freshness_at": "2026-09-08T00:00:00+00:00",
            }],
            dry_run=False,
        )

    register_web(client, "patient", "finder-launch@example.com", "Finder Launch Patient")
    login_web(client, "patient", "finder-launch@example.com")

    page = client.get("/finder")
    token = csrf(page.data.decode())
    response = client.post(
        "/finder",
        data={
            "csrf_token": token,
            "category": "hospital",
            "specialty": "",
            "location": "Kalyani",
            "radius_km": "10",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    body = response.data
    assert b"Launch Quality Hospital" in body
    assert b"Search source summary" in body
    assert b"ZENDOC verified" in body
    assert b"Official public directory" in body
    assert b"External map listings" in body
    assert b"Booking is not connected for this external listing" in body


def test_finder_empty_state_explains_external_provider_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENDOC_PLACES_PROVIDER", "none")
    _app, client = make_client(tmp_path)

    register_web(client, "patient", "finder-empty@example.com", "Finder Empty Patient")
    login_web(client, "patient", "finder-empty@example.com")

    page = client.get("/finder")
    token = csrf(page.data.decode())
    response = client.post(
        "/finder",
        data={
            "csrf_token": token,
            "category": "hospital",
            "specialty": "",
            "location": "A Location With No Seeded Records",
            "radius_km": "10",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"No matching care options yet" in response.data
    assert b"no maps/places provider is configured" in response.data
