import pytest

from zendoc.db import get_db
from zendoc.healthcare_finder import HealthcareFinder
from zendoc.public_data_ingestion import ingest_public_records, search_public_healthcare_entities
from zendoc.public_source_registry import list_public_ingestion_sources
from zendoc.data_gap_registry import list_data_gaps
from zendoc.provider_onboarding import provider_onboarding_status
from tests.test_milestone1 import csrf, login_web, make_app, register_web


def owner_token(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminStrong123"},
    )
    assert response.status_code == 200
    return response.get_json()["token"]


def register_api_provider(client, email, role):
    response = client.post(
        "/api/v1/auth/register",
        json={"name": "Pilot Provider", "email": email, "password": "StrongPass123", "role": role},
    )
    assert response.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPass123"},
    )
    assert login.status_code == 200
    return login.get_json()["token"]


def test_public_ingestion_dry_run_does_not_mutate(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        owner = dict(get_db().execute("SELECT * FROM users WHERE role='admin' LIMIT 1").fetchone())
        result = ingest_public_records(
            owner,
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
            records=[
                {
                    "source_record_id": "hospital-1",
                    "category": "hospital",
                    "name": "Official Test Hospital",
                    "city": "Test City",
                    "state": "Test State",
                }
            ],
            dry_run=True,
        )
        assert result["dry_run"] is True
        assert result["preview"]["accepted_count"] == 1
        count = get_db().execute("SELECT COUNT(*) c FROM public_healthcare_entities").fetchone()["c"]
        assert count == 0


def test_public_ingestion_apply_keeps_official_record_unverified(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        owner = dict(get_db().execute("SELECT * FROM users WHERE role='admin' LIMIT 1").fetchone())
        result = ingest_public_records(
            owner,
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
            records=[
                {
                    "source_record_id": "hospital-2",
                    "category": "hospital",
                    "name": "District Public Hospital",
                    "district": "Pilot District",
                    "state": "Pilot State",
                    "public_phone": "0000000000",
                }
            ],
            dry_run=False,
        )
        assert result["accepted_count"] == 1
        rows = search_public_healthcare_entities(category="hospital", location="Pilot District")
        assert len(rows) == 1
        assert rows[0]["zendoc_verification_status"] == "not_verified"
        assert rows[0]["bookable_in_zendoc"] is False
        assert rows[0]["source_trust"] == "OFFICIAL_PUBLIC_DATA"


def test_healthcare_finder_separates_official_public_source_tier(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        owner = dict(get_db().execute("SELECT * FROM users WHERE role='admin' LIMIT 1").fetchone())
        ingest_public_records(
            owner,
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
            records=[
                {
                    "source_record_id": "finder-hospital",
                    "category": "hospital",
                    "name": "Finder Official Hospital",
                    "city": "Finder City",
                    "state": "Finder State",
                }
            ],
            dry_run=False,
        )
        result = HealthcareFinder().search({
            "category": "hospital",
            "location": "Finder City",
            "specialty": "",
            "radius_km": 10,
        })
        assert result["official_public_directory"]
        assert result["source_tiers"]["official_public_directory_not_zendoc_verified"] == 1
        item = result["official_public_directory"][0]
        assert item["bookable_in_zendoc"] is False


def test_geography_ingestion_resolves_parent_source_references(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        owner = dict(get_db().execute("SELECT * FROM users WHERE role='admin' LIMIT 1").fetchone())
        result = ingest_public_records(
            owner,
            source_id="lgd",
            ingestion_type="geography_nodes",
            records=[
                {"source_record_id": "country-in", "node_type": "country", "name": "India"},
                {"source_record_id": "state-test", "parent_source_record_id": "country-in", "node_type": "state", "name": "Pilot State"},
                {"source_record_id": "district-test", "parent_source_record_id": "state-test", "node_type": "district", "name": "Pilot District"},
                {"source_record_id": "village-test", "parent_source_record_id": "district-test", "node_type": "village", "name": "Pilot Village"},
            ],
            dry_run=False,
        )
        assert result["accepted_count"] == 4
        village = get_db().execute(
            "SELECT * FROM geography_nodes WHERE source='lgd' AND source_ref='village-test'"
        ).fetchone()
        assert village is not None


def test_ingestion_api_is_owner_only_and_requires_explicit_apply(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    patient_reg = client.post(
        "/api/v1/auth/register",
        json={"name": "Normal", "email": "normal-ingest@example.com", "password": "StrongPass123", "role": "patient"},
    )
    assert patient_reg.status_code == 201
    patient_login = client.post(
        "/api/v1/auth/login",
        json={"email": "normal-ingest@example.com", "password": "StrongPass123"},
    )
    patient_token = patient_login.get_json()["token"]
    denied = client.get(
        "/api/v1/admin/ingestion/sources",
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert denied.status_code == 403

    token = owner_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    preview = client.post(
        "/api/v1/admin/ingestion/preview",
        json={
            "source_id": "data_gov_hospitals",
            "ingestion_type": "public_healthcare_entities",
            "records": [{"source_record_id": "api-h1", "category": "hospital", "name": "API Hospital"}],
        },
        headers=headers,
    )
    assert preview.status_code == 200

    blocked_apply = client.post(
        "/api/v1/admin/ingestion/apply",
        json={
            "source_id": "data_gov_hospitals",
            "ingestion_type": "public_healthcare_entities",
            "records": [{"source_record_id": "api-h1", "category": "hospital", "name": "API Hospital"}],
        },
        headers=headers,
    )
    assert blocked_apply.status_code == 400


def test_provider_onboarding_evidence_requires_owner_review(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    doctor_token = register_api_provider(client, "pilot-doctor@example.com", "doctor")
    headers = {"Authorization": f"Bearer {doctor_token}"}

    profile = client.post(
        "/api/v1/provider/profile",
        json={
            "specialty": "Cardiology",
            "qualifications": "MBBS, MD",
            "license_identifier": "TEST-REG-123",
            "organization": "Pilot Heart Clinic",
            "address": "1 Pilot Road",
            "city": "Pilot City",
            "state": "Pilot State",
            "postal_code": "000001",
            "public_phone": "9999999999",
        },
        headers=headers,
    )
    assert profile.status_code == 200

    schedule = client.post(
        "/api/v1/provider/schedules",
        json={"weekday": 1, "start_time": "10:00", "end_time": "12:00", "slot_minutes": 30},
        headers=headers,
    )
    assert schedule.status_code == 201

    evidence = client.post(
        "/api/v1/provider/evidence",
        json={
            "evidence_type": "professional_registration",
            "identifier": "TEST-REG-123",
            "source_name": "Test Medical Register",
            "source_url": "https://example.invalid/registration/TEST-REG-123",
        },
        headers=headers,
    )
    assert evidence.status_code == 201
    evidence_id = evidence.get_json()["evidence"]["id"]

    before = client.get("/api/v1/provider/onboarding", headers=headers).get_json()["onboarding"]
    assert before["verification_ready"] is False
    assert before["verified_evidence_count"] == 0

    admin_headers = {"Authorization": f"Bearer {owner_token(client)}"}
    reviewed = client.post(
        f"/api/v1/admin/provider-evidence/{evidence_id}/review",
        json={"status": "verified"},
        headers=admin_headers,
    )
    assert reviewed.status_code == 200

    after = client.get("/api/v1/provider/onboarding", headers=headers).get_json()["onboarding"]
    assert after["verification_ready"] is True
    assert after["verified_evidence_count"] == 1
    with app.app_context():
        row = get_db().execute(
            "SELECT verification_status FROM provider_profiles WHERE user_id=(SELECT id FROM users WHERE email='pilot-doctor@example.com')"
        ).fetchone()
        assert row["verification_status"] == "pending"


def test_carefin_and_care_journey_pilot_pages(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "pilot-patient@example.com", "Pilot Patient")
    login_web(client, "patient", "pilot-patient@example.com")

    carefin = client.get("/connected-care/carefin")
    assert carefin.status_code == 200
    assert b"CareFin benefits discovery" in carefin.data

    token = csrf(carefin.data.decode())
    result = client.post(
        "/connected-care/carefin",
        data={
            "csrf_token": token,
            "state": "West Bengal",
            "district": "Nadia",
            "age": "40",
            "occupation": "self employed",
            "income_band": "low",
        },
    )
    assert result.status_code == 200
    assert b"possible pathway" in result.data.lower()
    assert b"Not yet verified" in result.data

    page = client.get("/connected-care/journey")
    assert page.status_code == 200
    assert b"Automatic Care Journey" in page.data
    token = csrf(page.data.decode())
    created = client.post(
        "/connected-care/journey/create",
        data={"csrf_token": token, "goal": "Find specialist care"},
        follow_redirects=True,
    )
    assert created.status_code == 200
    assert b"NEW" in created.data


def test_diagnostic_api_rejects_unconfirmed_request_before_booking(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    client.post(
        "/api/v1/auth/register",
        json={"name": "Diag User", "email": "diag-route@example.com", "password": "StrongPass123", "role": "patient"},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "diag-route@example.com", "password": "StrongPass123"},
    )
    token = login.get_json()["token"]
    response = client.post(
        "/api/v1/connected-care/diagnostics/book",
        json={
            "test_id": 1,
            "lab_id": 1,
            "scheduled_date": "2026-09-20",
            "address": "Concrete Address",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert "confirmation" in response.get_json()["error"]["message"].lower()


def test_dataset_adapter_maps_csv_explicitly(tmp_path):
    from zendoc.dataset_adapters import adapt_records, parse_csv_text

    rows = parse_csv_text("facility_id,facility_name,district_name\nH1,Pilot Hospital,Pilot District\n")
    adapted = adapt_records(
        ingestion_type="public_healthcare_entities",
        rows=rows,
        mapping={
            "source_record_id": "facility_id",
            "name": "facility_name",
            "district": "district_name",
        },
        defaults={"category": "hospital", "state": "Pilot State"},
    )
    assert adapted["canonical_record_count"] == 1
    assert adapted["records"][0]["source_record_id"] == "H1"
    assert adapted["records"][0]["category"] == "hospital"
    assert adapted["records"][0]["district"] == "Pilot District"


def test_dataset_adapter_refuses_missing_required_mapping():
    from zendoc.dataset_adapters import adapt_records

    with pytest.raises(ValueError):
        adapt_records(
            ingestion_type="geography_nodes",
            rows=[{"code": "1", "name": "State"}],
            mapping={"source_record_id": "code", "name": "name"},
            defaults={},
        )


def test_provider_evidence_browser_workflow(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "doctor", "browser-doctor@example.com", "Browser Doctor")
    login_web(client, "doctor", "browser-doctor@example.com")

    page = client.get("/provider/profile")
    assert page.status_code == 200
    token = csrf(page.data.decode())
    saved = client.post(
        "/provider/profile",
        data={
            "csrf_token": token,
            "specialty": "Cardiology",
            "qualifications": "MBBS, MD",
            "license_identifier": "BROWSER-REG-1",
            "organization": "Browser Clinic",
            "address": "1 Browser Road",
            "city": "Browser City",
            "state": "Browser State",
            "postal_code": "000001",
            "public_phone": "9999999999",
        },
        follow_redirects=True,
    )
    assert saved.status_code == 200
    assert b"Verification readiness" in saved.data

    token = csrf(saved.data.decode())
    submitted = client.post(
        "/provider/evidence",
        data={
            "csrf_token": token,
            "evidence_type": "professional_registration",
            "identifier": "BROWSER-REG-1",
            "source_name": "Browser Medical Register",
            "source_url": "https://example.invalid/BROWSER-REG-1",
        },
        follow_redirects=True,
    )
    assert submitted.status_code == 200
    assert b"Verification evidence submitted" in submitted.data
    assert b"Browser Medical Register" in submitted.data

    client.get("/logout")
    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    admin = client.get("/admin")
    assert admin.status_code == 200
    assert b"Provider Evidence Review" in admin.data
    assert b"Browser Medical Register" in admin.data


def test_official_source_registry_covers_core_national_and_west_bengal_sources(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        sources = {item["source_id"]: item for item in list_public_ingestion_sources()}
        expected = {
            "lgd",
            "data_gov_hospitals",
            "abdm_hfr",
            "abdm_hpr",
            "nmc_imr",
            "nmc_medical_colleges",
            "data_gov_hmis",
            "eraktkosh",
            "clinical_establishments",
            "nabh_directory",
            "nabl_labs",
            "pmbjp_kendras",
            "pmbjp_products",
            "nppa_prices",
            "cdsco_approved_drugs",
            "cdsco_nlem",
            "pmjay_hospitals",
            "myscheme",
            "swasthya_sathi_hospitals",
            "wbhs_empanelled_hco",
            "data_gov_cghs_hospitals",
            "data_gov_blood_banks",
        }
        assert expected.issubset(set(sources))
        assert all(item["personal_data_allowed"] is False for item in sources.values())


def test_data_gap_registry_separates_public_directories_from_live_operational_data(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        gaps = {item["gap_id"]: item for item in list_data_gaps()}
        assert gaps["pharmacy_live_stock"]["public_availability"] == "GENERALLY_NOT_PUBLIC"
        assert "PHARMACY" in gaps["pharmacy_live_stock"]["preferred_collection"]
        assert gaps["ambulance_live_dispatch"]["update_frequency"] == "REAL_TIME"
        assert gaps["personal_health_records"]["sensitivity"] == "HIGH"
        assert gaps["scheme_outcome"]["public_availability"] == "PRIVATE_OR_AUTHORIZED_ONLY"


def test_owner_can_read_data_gap_registry_but_patient_cannot(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    client.post(
        "/api/v1/auth/register",
        json={"name": "Gap Patient", "email": "gap-patient@example.com", "password": "StrongPass123", "role": "patient"},
    )
    patient_login = client.post(
        "/api/v1/auth/login",
        json={"email": "gap-patient@example.com", "password": "StrongPass123"},
    )
    denied = client.get(
        "/api/v1/admin/ingestion/data-gaps",
        headers={"Authorization": f"Bearer {patient_login.get_json()['token']}"},
    )
    assert denied.status_code == 403

    owner = owner_token(client)
    allowed = client.get(
        "/api/v1/admin/ingestion/data-gaps",
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert allowed.status_code == 200
    payload = allowed.get_json()
    assert any(item["gap_id"] == "doctor_live_slots" for item in payload["data_gaps"])
