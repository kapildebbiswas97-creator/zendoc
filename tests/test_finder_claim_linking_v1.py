from zendoc.db import get_db
from zendoc.healthcare_finder import HealthcareFinder
from zendoc.places_provider import UnconfiguredPlacesProvider
from zendoc.public_data_ingestion import ingest_public_records, search_public_healthcare_entities
from zendoc.public_entity_claims import review_public_entity_claim, submit_public_entity_claim
from tests.test_milestone1 import make_app


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def create_doctor(db, *, email, name, verification_status="verified", city="Kalyani"):
    now = "2026-09-08T00:00:00+00:00"
    user_id = db.execute(
        """
        INSERT INTO users
        (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
        VALUES (?,?,?,?,?,1,?,?)
        """,
        (name, email, email, "x", "doctor", now, now),
    ).lastrowid
    profile_id = db.execute(
        """
        INSERT INTO provider_profiles
        (user_id,provider_type,specialty,qualifications,license_identifier,organization,address,city,state,
         postal_code,public_phone,verification_status,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            user_id,
            "doctor",
            "Cardiology",
            "MBBS",
            f"REG-{user_id}",
            f"{name} Clinic",
            "1 Road",
            city,
            "West Bengal",
            "741235",
            "1234567890",
            verification_status,
            now,
            now,
        ),
    ).lastrowid
    db.commit()
    return int(user_id), int(profile_id)


def ingest_public_doctor(source_id, source_record_id, *, name="Public Dr Listing", city="Kalyani"):
    ingest_public_records(
        owner_actor(),
        source_id=source_id,
        ingestion_type="public_healthcare_entities",
        records=[{
            "source_record_id": source_record_id,
            "category": "doctor",
            "name": name,
            "address": "1 Road",
            "city": city,
            "district": "Nadia",
            "state": "West Bengal",
            "postal_code": "741235",
            "freshness_at": "2026-09-08T00:00:00+00:00",
        }],
        dry_run=False,
    )
    return int(
        get_db().execute(
            "SELECT id FROM public_healthcare_entities WHERE source_id=? AND source_record_id=?",
            (source_id, source_record_id),
        ).fetchone()["id"]
    )


def approve_claim(provider_user_id, public_entity_id):
    claim = submit_public_entity_claim(
        {"id": provider_user_id, "role": "doctor", "active": 1},
        public_entity_id=public_entity_id,
        claimant_note="This is my public listing.",
    )
    return review_public_entity_claim(
        owner_actor(),
        claim["id"],
        status="approved",
        review_note="Ownership linkage approved.",
    )


def test_verified_provider_and_approved_public_listing_merge_in_finder(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        provider_user_id, profile_id = create_doctor(
            db,
            email="finder-linked@example.com",
            name="Dr Finder Linked",
            verification_status="verified",
        )
        public_entity_id = ingest_public_doctor(
            "data_gov_hospitals",
            "FINDER-LINK-1",
            name="Dr Finder Linked Clinic",
        )
        approve_claim(provider_user_id, public_entity_id)

        finder = HealthcareFinder(places_provider=UnconfiguredPlacesProvider())
        result = finder.search({
            "category": "doctor",
            "specialty": "",
            "location": "Kalyani",
            "latitude": None,
            "longitude": None,
            "radius_km": 10,
        })

        assert result["source_tiers"]["zendoc_verified"] == 1
        assert result["source_tiers"]["approved_public_listings_merged_into_verified"] == 1
        assert len(result["registered_providers"]) == 1
        assert result["official_public_directory"] == []
        assert len(result["results"]) == 1

        provider = result["registered_providers"][0]
        assert provider["id"] == profile_id
        assert provider["verification_status"] == "verified"
        assert provider["public_listing_claim_linked"] is True
        assert provider["approved_public_listing_ids"] == [public_entity_id]
        assert provider["public_directory_provenance"][0]["source_id"] == "data_gov_hospitals"


def test_approved_claim_does_not_promote_unverified_provider(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        provider_user_id, profile_id = create_doctor(
            db,
            email="finder-pending@example.com",
            name="Dr Finder Pending",
            verification_status="pending",
        )
        public_entity_id = ingest_public_doctor(
            "data_gov_hospitals",
            "FINDER-PENDING-1",
            name="Dr Finder Pending Clinic",
        )
        approve_claim(provider_user_id, public_entity_id)

        finder = HealthcareFinder(places_provider=UnconfiguredPlacesProvider())
        result = finder.search({
            "category": "doctor",
            "specialty": "",
            "location": "Kalyani",
            "latitude": None,
            "longitude": None,
            "radius_km": 10,
        })

        assert result["registered_providers"] == []
        assert result["source_tiers"]["approved_public_listings_merged_into_verified"] == 0
        assert len(result["official_public_directory"]) == 1
        public = result["official_public_directory"][0]
        assert public["approved_provider_profile_id"] == profile_id
        assert public["verification_status"] != "verified"


def test_conflicting_approved_claims_prevent_cross_source_dedupe(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        user_a, profile_a = create_doctor(
            db,
            email="claim-conflict-a@example.com",
            name="Dr Conflict A",
        )
        user_b, profile_b = create_doctor(
            db,
            email="claim-conflict-b@example.com",
            name="Dr Conflict B",
        )

        entity_a = ingest_public_doctor(
            "data_gov_hospitals",
            "CLAIM-CONFLICT-A",
            name="Shared Public Clinic",
        )
        entity_b = ingest_public_doctor(
            "clinical_establishments",
            "CLAIM-CONFLICT-B",
            name="Shared Public Clinic",
        )
        approve_claim(user_a, entity_a)
        approve_claim(user_b, entity_b)

        public_results = search_public_healthcare_entities(
            category="doctor",
            location="Kalyani",
            limit=25,
        )
        matches = [item for item in public_results if item["name"] == "Shared Public Clinic"]
        assert len(matches) == 2
        assert all(item["claim_link_conflict"] is True for item in matches)
        assert {tuple(item["claim_link_conflict_provider_profile_ids"]) for item in matches} == {
            tuple(sorted([profile_a, profile_b]))
        }
        assert all(item["cross_source_deduplicated"] is False for item in matches)


def test_finder_cache_revision_reflects_newly_approved_claim(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        provider_user_id, _profile_id = create_doctor(
            db,
            email="finder-cache@example.com",
            name="Dr Finder Cache",
            verification_status="verified",
        )
        public_entity_id = ingest_public_doctor(
            "data_gov_hospitals",
            "FINDER-CACHE-1",
            name="Dr Finder Cache Clinic",
        )

        finder = HealthcareFinder(places_provider=UnconfiguredPlacesProvider())
        query = {
            "category": "doctor",
            "specialty": "",
            "location": "Kalyani",
            "latitude": None,
            "longitude": None,
            "radius_km": 10,
        }

        before = finder.search(query)
        assert len(before["registered_providers"]) == 1
        assert len(before["official_public_directory"]) == 1
        assert before["source_tiers"]["approved_public_listings_merged_into_verified"] == 0

        approve_claim(provider_user_id, public_entity_id)

        after = finder.search(query)
        assert len(after["registered_providers"]) == 1
        assert after["official_public_directory"] == []
        assert after["source_tiers"]["approved_public_listings_merged_into_verified"] == 1


def test_deduped_claim_link_preserves_exact_claimed_public_entity_id(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        provider_user_id, profile_id = create_doctor(
            db,
            email="finder-dedup-claim@example.com",
            name="Dr Dedup Claim",
            verification_status="verified",
        )

        entity_a = ingest_public_doctor(
            "data_gov_hospitals",
            "DEDUP-CLAIM-A",
            name="Dedup Claim Clinic",
        )
        _entity_b = ingest_public_doctor(
            "clinical_establishments",
            "DEDUP-CLAIM-B",
            name="Dedup Claim Clinic",
        )
        approve_claim(provider_user_id, entity_a)

        public_results = search_public_healthcare_entities(
            category="doctor",
            location="Kalyani",
            limit=25,
        )
        public = next(item for item in public_results if item["name"] == "Dedup Claim Clinic")
        assert public["duplicate_source_count"] == 2
        assert public["approved_provider_profile_id"] == profile_id
        assert public["approved_public_entity_ids"] == [entity_a]

        finder = HealthcareFinder(places_provider=UnconfiguredPlacesProvider())
        result = finder.search({
            "category": "doctor",
            "specialty": "",
            "location": "Kalyani",
            "latitude": None,
            "longitude": None,
            "radius_km": 10,
        })
        provider = next(item for item in result["registered_providers"] if item["id"] == profile_id)
        assert provider["approved_public_listing_ids"] == [entity_a]
        link = next(
            item
            for item in result["claimed_public_directory_links"]
            if item["provider_profile_id"] == profile_id
        )
        assert link["public_entity_id"] == entity_a
        assert link["approved_public_entity_ids"] == [entity_a]
