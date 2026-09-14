from tests.test_milestone1 import login_web, make_app, make_client, register_web
from zendoc.db import get_db
from zendoc.places_provider import UnconfiguredPlacesProvider
from zendoc.universal_health_search import universal_search


def seed_verified_doctor(db):
    stamp = "2026-09-14T00:00:00+00:00"
    user_id = db.execute(
        """
        INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
        VALUES ('Dr Ananya Sen','ananya-search@example.test','ananya-search@example.test','unused','doctor',1,?,?)
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


def seed_public_entity(db, record_id, category, name, specialty=""):
    stamp = "2026-09-14T00:00:00+00:00"
    db.execute(
        """
        INSERT INTO public_healthcare_entities
        (source_id,source_record_id,category,name,specialty,address,city,district,state,postal_code,active,created_at,updated_at)
        VALUES ('universal-search-test',?,?,?,?,?,'Kalyani','Nadia','West Bengal','741235',1,?,?)
        """,
        (record_id, category, name, specialty, "Test Road", stamp, stamp),
    )


def test_universal_search_finds_doctor_by_name_and_shows_specialty(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        seed_verified_doctor(db)
        db.commit()
        result = universal_search("Dr Ananya Sen", places_provider=UnconfiguredPlacesProvider())
        assert result["universal"] is True
        assert result["results"]
        doctor = result["grouped_results"]["doctor"]["results"][0]
        assert doctor["provider_name"] == "Dr Ananya Sen"
        assert doctor["specialty"] == "Cardiology"
        assert doctor["source"] == "zendoc_provider_network"


def test_location_text_returns_multiple_healthcare_categories(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        seed_verified_doctor(db)
        seed_public_entity(db, "HOSP-1", "hospital", "Kalyani General Hospital")
        seed_public_entity(db, "PHARM-1", "pharmacy", "Kalyani Community Pharmacy")
        seed_public_entity(db, "LAB-1", "laboratory", "Kalyani Diagnostics Lab", "Pathology")
        db.commit()
        result = universal_search("Kalyani", places_provider=UnconfiguredPlacesProvider())
        assert {"doctor", "hospital", "pharmacy", "laboratory"}.issubset(result["grouped_results"])
        assert result["category_counts"]["hospital"] == 1
        assert result["category_counts"]["pharmacy"] == 1
        assert result["source_tiers"]["zendoc_verified"] == 1
        assert result["source_tiers"]["official_public_directory_not_zendoc_verified"] == 3


def test_hospital_name_search_finds_public_directory_without_promoting_booking(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        seed_public_entity(db, "HOSP-NAME-1", "hospital", "Sunrise Multi Specialty Hospital")
        db.commit()
        result = universal_search("Sunrise Multi Specialty Hospital", places_provider=UnconfiguredPlacesProvider())
        hospital = result["grouped_results"]["hospital"]["results"][0]
        assert hospital["name"] == "Sunrise Multi Specialty Hospital"
        assert hospital["source"] == "official_public_directory"
        assert hospital["bookable_in_zendoc"] is False


def test_finder_page_exposes_one_box_universal_search(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENDOC_PLACES_PROVIDER", "none")
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "universal-page@example.com", "Universal Search Patient")
    login_web(client, "patient", "universal-page@example.com")

    page = client.get("/finder")
    assert page.status_code == 200
    assert b"Universal Healthcare Search" in page.data
    assert b"Search anything in healthcare" in page.data
    assert b"cardiologist in Kolkata" in page.data
    assert b"All healthcare" in page.data


def test_universal_route_groups_location_results_in_patient_ui(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENDOC_PLACES_PROVIDER", "none")
    app, client = make_client(tmp_path)
    with app.app_context():
        db = get_db()
        seed_verified_doctor(db)
        seed_public_entity(db, "UI-HOSP-1", "hospital", "Kalyani UI Hospital")
        seed_public_entity(db, "UI-PHARM-1", "pharmacy", "Kalyani UI Pharmacy")
        db.commit()
    register_web(client, "patient", "universal-ui@example.com", "Universal UI Patient")
    login_web(client, "patient", "universal-ui@example.com")

    response = client.get("/universal-search?q=Kalyani&category=all")
    assert response.status_code == 200
    body = response.data
    assert b"Doctors" in body
    assert b"Hospitals" in body
    assert b"Pharmacies" in body
    assert b"Dr Ananya Sen" in body
    assert b"Cardiology" in body
    assert b"Kalyani UI Hospital" in body
    assert b"Kalyani UI Pharmacy" in body
