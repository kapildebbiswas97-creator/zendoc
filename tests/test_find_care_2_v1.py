"""
Find Care 2.0 Regression & Capability Test Suite.
Verifies all 13 healthcare categories, aliases, specialty normalization,
PIN code extraction, Haversine distance truth, deduplication, and zero-result recovery.
"""
import pytest
from zendoc.healthcare_finder import (
    CATEGORIES,
    CATEGORY_ALIASES,
    HealthcareFinder,
    extract_postal_code,
    normalize_query,
)
from zendoc.places_provider import PlacesResult, UnconfiguredPlacesProvider
from zendoc.public_data_ingestion import ingest_public_records
from tests.test_milestone1 import make_app
from zendoc.db import get_db


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def test_find_care_categories_and_aliases():
    expected_categories = {
        "doctor", "hospital", "clinic", "pharmacy", "diagnostic_centre",
        "laboratory", "emergency", "home_health", "mental_health",
        "physiotherapy", "ambulance", "government_facility", "specialist"
    }
    assert expected_categories.issubset(CATEGORIES)

    # Test category aliases
    assert normalize_query(category="physio")["category"] == "physiotherapy"
    assert normalize_query(category="chemist")["category"] == "pharmacy"
    assert normalize_query(category="er")["category"] == "emergency"
    assert normalize_query(category="gov")["category"] == "government_facility"
    assert normalize_query(category="nursing")["category"] == "home_health"
    assert normalize_query(category="therapy")["category"] == "mental_health"
    assert normalize_query(category="labs")["category"] == "laboratory"


def test_specialty_normalization():
    assert normalize_query(specialty="cardiologist")["specialty"] == "Cardiology"
    assert normalize_query(specialty="skin")["specialty"] == "Dermatology"
    assert normalize_query(specialty="child")["specialty"] == "Pediatrics"
    assert normalize_query(specialty="bone")["specialty"] == "Orthopedics"
    assert normalize_query(specialty="neuro")["specialty"] == "Neurology"
    assert normalize_query(specialty="eye")["specialty"] == "Ophthalmology"


def test_postal_code_extraction():
    assert extract_postal_code("Kalyani, 741235") == "741235"
    assert extract_postal_code("Beverly Hills 90210") == "90210"
    assert extract_postal_code("Kolkata") is None

    norm = normalize_query(location="Kalyani, 741235")
    assert norm["postal_code"] == "741235"


def test_truthful_distance_calculation(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        # Seed a doctor in Kalyani
        u_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) "
            "VALUES ('Dr. Distance Test', 'dist@example.com', 'dist@example.com', 'x', 'doctor', 1, '2026-09-01T00:00:00Z', '2026-09-01T00:00:00Z')"
        ).lastrowid
        db.execute(
            "INSERT INTO provider_profiles (user_id, provider_type, organization, city, state, latitude, longitude, verification_status, created_at, updated_at) "
            "VALUES (?, 'doctor', 'Kalyani Polyclinic', 'Kalyani', 'West Bengal', 22.975, 88.434, 'verified', '2026-09-01T00:00:00Z', '2026-09-01T00:00:00Z')",
            (u_id,)
        )
        db.commit()

        finder = HealthcareFinder(UnconfiguredPlacesProvider())
        # Search from ~2km away
        result = finder.search({
            "category": "doctor",
            "latitude": 22.980,
            "longitude": 88.440,
            "radius_km": 10
        })

        assert len(result["registered_providers"]) == 1
        provider = result["registered_providers"][0]
        assert provider["distance_km"] is not None
        assert 0.1 <= provider["distance_km"] <= 3.0
        assert provider["verification_tier"] == "ZENDOC_VERIFIED"
        assert provider["availability_truth"] == "LIVE_BOOKING"


def test_zero_result_context_and_recovery(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        finder = HealthcareFinder(UnconfiguredPlacesProvider())
        result = finder.search({
            "category": "physiotherapy",
            "specialty": "Pediatrics",
            "location": "NonexistentVillage, 999999",
            "radius_km": 5
        })

        assert len(result["results"]) == 0
        ctx = result.get("zero_result_context")
        assert ctx is not None
        assert len(ctx["sources_checked"]) == 3
        assert ctx["location_understood"]["postal_code"] == "999999"
        assert ctx["location_understood"]["radius_km"] == 5

        # Check suggestions
        actions = {s["action"] for s in ctx["expansion_suggestions"]}
        assert "expand_radius" in actions
        assert "clear_specialty" in actions


class MockExternalPlacesProvider:
    source = "google"
    def search(self, normalized):
        return PlacesResult(
            available=True,
            results=[
                {
                    "name": "Dr. Duplicate Specialist",
                    "city": "Kalyani",
                    "latitude": 22.975,
                    "longitude": 88.434,
                }
            ],
            source="google"
        )


def test_cross_source_deduplication(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        u_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) "
            "VALUES ('Dr. Duplicate Specialist', 'dedup@example.com', 'dedup@example.com', 'x', 'doctor', 1, '2026-09-01T00:00:00Z', '2026-09-01T00:00:00Z')"
        ).lastrowid
        db.execute(
            "INSERT INTO provider_profiles (user_id, provider_type, organization, city, state, latitude, longitude, verification_status, created_at, updated_at) "
            "VALUES (?, 'doctor', 'Kalyani Hospital', 'Kalyani', 'West Bengal', 22.975, 88.434, 'verified', '2026-09-01T00:00:00Z', '2026-09-01T00:00:00Z')",
            (u_id,)
        )
        db.commit()

        finder = HealthcareFinder(MockExternalPlacesProvider())
        result = finder.search({
            "category": "doctor",
            "location": "Kalyani",
            "radius_km": 10
        })

        # The external duplicate must be merged into the verified provider, not shown twice
        assert len(result["registered_providers"]) == 1
        assert len(result["external_places"]["results"]) == 0
        assert result["registered_providers"][0].get("external_map_match") is True
        assert len(result["results"]) == 1

