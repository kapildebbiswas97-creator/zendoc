"""
ZENDOC Milestone 10: Connected Care, Context Engine, Hyperlocal Pharmacy Fulfilment,
Prescription Safety Guard, and Care Continuity Test Suite.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from zendoc import create_app
from zendoc.care_graph import get_patient_care_graph, record_care_continuity_event
from zendoc.context_engine import (
    build_minimum_context_bundle,
    create_or_update_consent_grant,
    get_active_consent_grant,
    revoke_consent_grant,
    verify_context_authorization,
)
from zendoc.db import get_db, now_iso
from zendoc.diagnostic_service import (
    book_diagnostic_test,
    list_diagnostic_catalog,
    search_lab_offers,
)
from zendoc.fulfilment_optimizer import optimize_prescription_fulfilment
from zendoc.health_memory_continuity import (
    determine_next_safe_actions,
    get_health_memory_provenance_summary,
)
from zendoc.inventory_service import (
    calculate_distance_km,
    evaluate_freshness,
    search_pharmacy_offers,
    update_inventory_observation,
)
from zendoc.order_service import (
    acknowledge_order,
    get_order_details,
    submit_order_from_plan,
    update_order_tracking_status,
)
from zendoc.prescription_service import (
    confirm_uncertain_prescription_item,
    create_prescription,
    get_prescription,
    is_autonomous_prescription_request,
)
from zendoc.trust_service import (
    get_provider_trust_signals,
    is_interaction_eligible_for_review,
    submit_verified_review,
)


PASSWORD = "StrongPass123"


def make_m10_app(tmp_path, db_path=None, **overrides):
    config = {
        "TESTING": True,
        "DATABASE": str(db_path or (tmp_path / "m10-test.db")),
        "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        "SECRET_KEY": "m10-test-secret",
        "ADMIN_EMAIL": "owner@example.com",
        "ADMIN_PASSWORD": "OwnerStrong123",
        "RATE_LIMIT_PER_MINUTE": 1000,
    }
    config.update(overrides)
    return create_app(config)


def register_api(client, email, role="patient", name="M10 User", password=PASSWORD):
    return client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": password, "role": role},
    )


def login_api(client, email, role="patient", password=PASSWORD):
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "role": role},
    )


# ── 1. Context Engine & Privacy Minimization Tests ─────────────────────────────

def test_context_engine_privacy_minimization_and_exclusion(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        # Seed patient and pharmacy
        p_cur = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) VALUES (?, ?, ?, ?, 'patient', 1, ?, ?)",
            ("Arun Sharma", "arun@example.com", "arun@example.com", "hash", now_iso(), now_iso()),
        )
        patient_id = p_cur.lastrowid
        db.commit()

        actor = {"id": patient_id, "role": "patient"}

        # Self-access bundle
        bundle = build_minimum_context_bundle(
            actor=actor,
            patient_id=patient_id,
            purpose="pharmacy_fulfilment",
            action="order_medicines",
        )

        assert bundle.patient_id == patient_id
        assert bundle.consent_status == "NOT_REQUIRED_SELF"
        # Invariant: Mental health conversations, unrelated records, and vitals are strictly excluded
        assert "mental_wellness_conversations" in bundle.excluded_fields
        assert "unrelated_medical_records" in bundle.excluded_fields
        assert "doctor_confidential_notes" in bundle.excluded_fields


def test_context_engine_delegated_consent_lifecycle(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        p_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) VALUES (?, ?, ?, ?, 'patient', 1, ?, ?)",
            ("Parent", "parent@example.com", "parent@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        c_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) VALUES (?, ?, ?, ?, 'patient', 1, ?, ?)",
            ("Caregiver", "caregiver@example.com", "caregiver@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.commit()

        caregiver_actor = {"id": c_id, "role": "patient"}

        # Without consent grant, access is blocked
        with pytest.raises(PermissionError) as exc_info:
            verify_context_authorization(caregiver_actor, p_id, "pharmacy")
        assert "Access denied" in str(exc_info.value)

        # Grant consent
        grant = create_or_update_consent_grant(
            subject_id=p_id,
            grantee_id=c_id,
            purpose="pharmacy",
            scopes=["prescriptions", "delivery_address"],
        )
        assert grant["status"] == "active"

        # Now authorization succeeds
        auth_type = verify_context_authorization(caregiver_actor, p_id, "pharmacy")
        assert auth_type == "DELEGATED_CONSENT"

        # Revoke consent
        revoked = revoke_consent_grant(grant["id"], actor_id=p_id)
        assert revoked is True

        # Now authorization fails again
        with pytest.raises(PermissionError):
            verify_context_authorization(caregiver_actor, p_id, "pharmacy")


# ── 2. Hyperlocal Inventory & Freshness Truth Tests ────────────────────────────

def test_haversine_distance_calculation():
    # Connaught Place Delhi (28.6315, 77.2167) to India Gate Delhi (28.6129, 77.2295) ~ 2.4 km
    dist = calculate_distance_km(28.6315, 77.2167, 28.6129, 77.2295)
    assert dist is not None
    assert 2.0 <= dist <= 3.0

    # Missing coordinates returns None, never fabricates
    assert calculate_distance_km(None, 77.2, 28.6, 77.2) is None
    assert calculate_distance_km(28.6, None, 28.6, 77.2) is None


def test_inventory_freshness_truth_and_unknown_invariants():
    now = datetime.now(timezone.utc)

    # Fresh observation (30 mins ago) -> CONFIRMED
    fresh_time = (now - timedelta(minutes=30)).isoformat()
    status, label = evaluate_freshness(fresh_time)
    assert status == "CONFIRMED"
    assert "minute" in label

    # Stale observation (3 hours ago > 2h threshold) -> STALE
    stale_time = (now - timedelta(hours=3)).isoformat()
    status, label = evaluate_freshness(stale_time)
    assert status == "STALE"
    assert "hour" in label

    # Missing observation -> UNKNOWN (never promoted to CONFIRMED)
    status, label = evaluate_freshness(None)
    assert status == "UNKNOWN"
    assert "unconfirmed" in label.lower()


def test_pharmacy_inventory_observation_and_search(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        # Seed pharmacy provider
        pharm_user_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) VALUES (?, ?, ?, ?, 'pharmacy', 1, ?, ?)",
            ("Green Cross Pharmacy", "gc@example.com", "gc@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.execute(
            "INSERT INTO provider_profiles (user_id, organization, provider_type, city, latitude, longitude, delivery_available, delivery_radius_km, created_at, updated_at) VALUES (?, ?, 'pharmacy', 'Delhi', 28.6300, 77.2100, 1, 10.0, ?, ?)",
            (pharm_user_id, "Green Cross Pharmacy", now_iso(), now_iso()),
        )
        db.commit()

        # Update stock for Metformin (SKU 2 from demo seed)
        obs = update_inventory_observation(
            pharmacy_id=pharm_user_id,
            sku_id=2,
            quantity=50,
            price_inr=140.0,
            stock_status="CONFIRMED",
        )
        assert obs["id"] > 0
        assert obs["price_inr"] == 140.0

        # Search pharmacy offers near Delhi location
        offers = search_pharmacy_offers("Metformin", patient_lat=28.6315, patient_lon=77.2167)
        assert len(offers) >= 1
        assert offers[0]["pharmacy_name"] == "Green Cross Pharmacy"
        assert offers[0]["effective_status"] == "CONFIRMED"


# ── 3. Prescription Safety Guard & Confidence Tracking Tests ───────────────────

def test_prescription_safety_guard_blocks_autonomous_rx():
    # Clinical boundary: Autonomous prescribe requests are flagged
    assert is_autonomous_prescription_request("Please prescribe Amoxicillin 500mg for me") is True
    assert is_autonomous_prescription_request("Can you give me prescription for alprazolam?") is True
    assert is_autonomous_prescription_request("What are standard exercises for knee pain?") is False


def test_prescription_uncertain_extraction_human_review_gate(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        p_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) VALUES (?, ?, ?, ?, 'patient', 1, ?, ?)",
            ("Ramesh", "ramesh@example.com", "ramesh@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.commit()

        # Create prescription with 1 confident item (0.95) and 1 uncertain item (0.75)
        rx = create_prescription(
            patient_id=p_id,
            prescriber_name="Dr. Mehta",
            items=[
                {"medicine_name": "Metformin 500mg", "extraction_confidence": 0.98},
                {"medicine_name": "Amlodipine 5mg", "extraction_confidence": 0.72},
            ],
        )

        assert rx["needs_review"] is True
        items = rx["items"]
        assert len(items) == 2

        confident_item = next(i for i in items if "Metformin" in i["medicine_name"])
        uncertain_item = next(i for i in items if "Amlodipine" in i["medicine_name"])

        assert confident_item["review_status"] == "verified"
        assert uncertain_item["review_status"] == "item_review_required"

        # Explicit human confirmation gate
        confirmed_item = confirm_uncertain_prescription_item(
            item_id=uncertain_item["id"],
            actor={"id": p_id, "role": "patient"},
        )
        assert confirmed_item["review_status"] == "user_confirmed"

        updated_rx = get_prescription(rx["id"])
        assert updated_rx["needs_review"] is False


# ── 4. Multi-Pharmacy Fulfilment Optimizer Tests ────────────────────────────────

def test_fulfilment_optimizer_staging_and_plan_hash(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        p_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) VALUES (?, ?, ?, ?, 'patient', 1, ?, ?)",
            ("Sunil", "sunil@example.com", "sunil@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        # Seed pharmacy and stock
        pharm_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) VALUES (?, ?, ?, ?, 'pharmacy', 1, ?, ?)",
            ("City Pharmacy", "cp@example.com", "cp@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.execute(
            "INSERT INTO provider_profiles (user_id, organization, provider_type, city, latitude, longitude, delivery_available, delivery_radius_km, delivery_fee_base_inr, created_at, updated_at) VALUES (?, ?, 'pharmacy', 'Delhi', 28.6300, 77.2100, 1, 10.0, 40.0, ?, ?)",
            (pharm_id, "City Pharmacy", now_iso(), now_iso()),
        )
        db.commit()

        # Add inventory for Paracetamol 500 mg (SKU 5)
        update_inventory_observation(pharm_id, 5, 100, 35.0, stock_status="CONFIRMED")

        # Invariant: Uncertain / mismatched extraction (650mg vs 500mg) cannot be automatically fulfilled
        mismatch_rx = create_prescription(
            patient_id=p_id,
            prescriber_name="Dr. Gupta",
            items=[{"medicine_name": "Paracetamol 650mg", "sku_id": 5, "quantity_prescribed": 20}],
        )
        mismatch_plan = optimize_prescription_fulfilment(
            prescription_id=mismatch_rx["id"],
            patient_lat=28.63,
            patient_lon=77.21,
            strategy="balanced",
        )
        assert mismatch_plan["status"] == "ITEM_REVIEW_REQUIRED"
        assert mismatch_plan["plan_id"] is None

        # Invariant: Exact matching catalog item with confirmed stock and fee produces order-ready plan
        rx = create_prescription(
            patient_id=p_id,
            prescriber_name="Dr. Gupta",
            items=[{"medicine_name": "Paracetamol 500 mg", "sku_id": 5, "quantity_prescribed": 20}],
        )

        plan = optimize_prescription_fulfilment(
            prescription_id=rx["id"],
            patient_lat=28.63,
            patient_lon=77.21,
            strategy="balanced",
        )

        assert plan["plan_id"] > 0
        assert plan["plan_hash"] is not None
        assert len(plan["plan_hash"]) >= 16
        assert plan["status"] == "staged"


# ── 5. Consequential Action Guard & Order Lifecycle Tests ──────────────────────

def test_order_submission_requires_explicit_user_confirmation(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        p_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) VALUES (?, ?, ?, ?, 'patient', 1, ?, ?)",
            ("Kavita", "kavita@example.com", "kavita@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        pharm_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) VALUES (?, ?, ?, ?, 'pharmacy', 1, ?, ?)",
            ("Kavita Meds", "km@example.com", "km@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.execute(
            "INSERT INTO provider_profiles (user_id, organization, provider_type, city, latitude, longitude, delivery_available, delivery_radius_km, delivery_fee_base_inr, created_at, updated_at) VALUES (?, ?, 'pharmacy', 'Delhi', 28.6300, 77.2100, 1, 10.0, 40.0, ?, ?)",
            (pharm_id, "Kavita Meds", now_iso(), now_iso()),
        )
        db.commit()

        update_inventory_observation(pharm_id, 1, 50, 60.0, stock_status="CONFIRMED")

        rx = create_prescription(
            patient_id=p_id,
            prescriber_name="Dr. Joshi",
            items=[{"medicine_name": "Amlodipine 5 mg", "sku_id": 1, "quantity_prescribed": 30}],
        )
        plan = optimize_prescription_fulfilment(rx["id"])

        user_actor = {"id": p_id, "role": "patient"}

        # Invariant: Calling submit_order_from_plan without user_confirmed=True fails
        with pytest.raises(ValueError) as exc:
            submit_order_from_plan(
                plan_id=plan["plan_id"],
                actor=user_actor,
                user_confirmed=False,
                delivery_address="102 Palm Grove, Delhi",
            )
        assert "explicit user confirmation" in str(exc.value).lower()

        # Invariant: Calling without concrete delivery address fails
        with pytest.raises(ValueError) as exc_addr:
            submit_order_from_plan(
                plan_id=plan["plan_id"],
                actor=user_actor,
                user_confirmed=True,
                delivery_address="",
            )
        assert "delivery_address" in str(exc_addr.value).lower()

        # Calling with user_confirmed=True and delivery address succeeds
        order_res = submit_order_from_plan(
            plan_id=plan["plan_id"],
            actor=user_actor,
            user_confirmed=True,
            delivery_address="102 Palm Grove, Delhi",
        )
        assert order_res["status"].lower() in ["confirmed", "submitted"]
        assert order_res["order_id"] > 0

        # Verify care graph recorded the event
        graph = get_patient_care_graph(p_id, actor=user_actor)
        assert any(e["event_type"] == "ORDER_PLACED" for e in graph["events"])


def test_order_tracking_status_progression_and_pharmacy_ack(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        p_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) VALUES (?, ?, ?, ?, 'patient', 1, ?, ?)",
            ("Anand", "anand@example.com", "anand@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        pharm_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) VALUES (?, ?, ?, ?, 'pharmacy', 1, ?, ?)",
            ("Quick Pharmacy", "qp@example.com", "qp@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.execute(
            "INSERT INTO provider_profiles (user_id, organization, provider_type, city, latitude, longitude, delivery_available, delivery_radius_km, delivery_fee_base_inr, created_at, updated_at) VALUES (?, ?, 'pharmacy', 'Delhi', 28.6300, 77.2100, 1, 10.0, 40.0, ?, ?)",
            (pharm_id, "Quick Pharmacy", now_iso(), now_iso()),
        )
        db.commit()

        update_inventory_observation(pharm_id, 3, 50, 180.0, stock_status="CONFIRMED")
        rx = create_prescription(p_id, "Dr. Sen", [{"medicine_name": "Atorvastatin 10 mg", "sku_id": 3}])
        plan = optimize_prescription_fulfilment(rx["id"])

        order = submit_order_from_plan(
            plan_id=plan["plan_id"],
            actor={"id": p_id, "role": "patient"},
            user_confirmed=True,
            delivery_address="102 Palm Grove, Delhi",
        )

        pharm_actor = {"id": pharm_id, "role": "pharmacy"}

        # Pharmacy acknowledges
        ack = acknowledge_order(pharm_actor, order["order_id"], action="accept")
        assert ack["status"].lower() in ["accepted", "acknowledged"]

        # Tracking progression: packed (PREPARING) -> dispatched (OUT_FOR_DELIVERY) -> delivered
        step1 = update_order_tracking_status(pharm_actor, order["order_id"], "packed")
        assert step1["tracking_status"].upper() in ["PACKED", "PREPARING"]

        step2 = update_order_tracking_status(pharm_actor, order["order_id"], "dispatched")
        assert step2["tracking_status"].upper() in ["DISPATCHED", "OUT_FOR_DELIVERY"]

        step3 = update_order_tracking_status(pharm_actor, order["order_id"], "delivered")
        assert step3["tracking_status"].upper() == "DELIVERED"


# ── 6. Diagnostic Marketplace Tests ────────────────────────────────────────────

def test_diagnostic_catalog_and_home_collection_booking(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        p_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) VALUES (?, ?, ?, ?, 'patient', 1, ?, ?)",
            ("Vikas", "vikas@example.com", "vikas@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        lab_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) VALUES (?, ?, ?, ?, 'hospital', 1, ?, ?)",
            ("Metropolis Lab", "metro@example.com", "metro@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.execute(
            "INSERT INTO provider_profiles (user_id, organization, provider_type, city, verification_status, created_at, updated_at) VALUES (?, 'Metropolis Lab', 'lab', 'Delhi', 'verified', ?, ?)",
            (lab_id, now_iso(), now_iso()),
        )
        db.execute(
            "INSERT INTO diagnostic_offers (lab_id, test_id, price_inr, home_collection_available, home_collection_fee_inr, verified, data_mode, created_at) VALUES (?, 1, 350.0, 1, 50.0, 1, 'LIVE', ?)",
            (lab_id, now_iso()),
        )
        db.commit()

        # Catalog has seeded tests
        catalog = list_diagnostic_catalog()
        assert len(catalog) >= 7  # CBC, FBS, LIPID, etc.

        # Invariant: booking without user confirmation fails
        with pytest.raises(ValueError) as exc:
            book_diagnostic_test(
                actor={"id": p_id, "role": "patient"},
                patient_id=p_id,
                test_id=1,
                lab_id=lab_id,
                scheduled_date="2026-09-10",
                address="A-12 Mayur Vihar, Delhi",
                collection_type="home_collection",
                user_confirmed=False,
            )
        assert "user confirmation" in str(exc.value).lower()

        # Invariant: booking without real lab_id fails
        with pytest.raises(ValueError) as exc_lab:
            book_diagnostic_test(
                actor={"id": p_id, "role": "patient"},
                patient_id=p_id,
                test_id=1,
                lab_id=None,
                scheduled_date="2026-09-10",
                address="A-12 Mayur Vihar, Delhi",
                collection_type="home_collection",
                user_confirmed=True,
            )
        assert "lab offer is required" in str(exc_lab.value).lower()

        # Book CBC test (ID 1) with user_confirmed=True and verified lab offer
        booking = book_diagnostic_test(
            actor={"id": p_id, "role": "patient"},
            patient_id=p_id,
            test_id=1,
            lab_id=lab_id,
            scheduled_date="2026-09-10",
            address="A-12 Mayur Vihar, Delhi",
            collection_type="home_collection",
            user_confirmed=True,
        )

        assert booking["booking_id"] > 0
        assert booking["status"].lower() == "requested"
        assert booking["booking_uid"].startswith("diag_")


# ── 7. Verified Reviews & Trust Signals Tests ──────────────────────────────────

def test_verified_reviews_require_actual_interaction(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        p_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) VALUES (?, ?, ?, ?, 'patient', 1, ?, ?)",
            ("Neha", "neha@example.com", "neha@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        pharm_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) VALUES (?, ?, ?, ?, 'pharmacy', 1, ?, ?)",
            ("Apex Meds", "apex@example.com", "apex@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.execute(
            "INSERT INTO provider_profiles (user_id, organization, provider_type, city, latitude, longitude, delivery_available, delivery_radius_km, delivery_fee_base_inr, created_at, updated_at) VALUES (?, ?, 'pharmacy', 'Delhi', 28.6300, 77.2100, 1, 10.0, 40.0, ?, ?)",
            (pharm_id, "Apex Meds", now_iso(), now_iso()),
        )
        db.commit()

        # Before any interaction, user is not eligible to review
        assert is_interaction_eligible_for_review(p_id, "pharmacy_order", 999) is False

        # Place and complete an order
        update_inventory_observation(pharm_id, 4, 30, 95.0, stock_status="CONFIRMED")
        rx = create_prescription(p_id, "Dr. Rao", [{"medicine_name": "Telmisartan 40 mg", "sku_id": 4}])
        plan = optimize_prescription_fulfilment(rx["id"])
        order = submit_order_from_plan(
            plan_id=plan["plan_id"],
            actor={"id": p_id, "role": "patient"},
            user_confirmed=True,
            delivery_address="45 Civil Lines, Delhi",
        )
        pharm_actor = {"id": pharm_id, "role": "pharmacy"}
        acknowledge_order(pharm_actor, order["order_id"], action="accept")
        update_order_tracking_status(pharm_actor, order["order_id"], "PREPARING")
        update_order_tracking_status(pharm_actor, order["order_id"], "OUT_FOR_DELIVERY")
        update_order_tracking_status(pharm_actor, order["order_id"], "DELIVERED")

        # Now eligible!
        assert is_interaction_eligible_for_review(p_id, "pharmacy_order", order["order_id"]) is True

        # Submit verified review
        rev = submit_verified_review(
            actor={"id": p_id, "role": "patient"},
            provider_id=pharm_id,
            interaction_type="pharmacy_order",
            interaction_id=order["order_id"],
            rating=5,
            comment="Fast delivery, verified stock!",
        )
        assert rev["is_verified"] is True

        # Check provider trust signals
        trust = get_provider_trust_signals(pharm_id)
        assert trust["total_reviews"] >= 1
        assert trust["average_rating"] == 5.0
        assert trust["verified_rate"] == 1.0


# ── 8. Route & Integration API Tests ───────────────────────────────────────────

def test_connected_care_pages_and_api_endpoints(tmp_path):
    app = make_m10_app(tmp_path)
    client = app.test_client()

    # Register and login patient
    reg = register_api(client, "webpatient@example.com", role="patient", name="Web Patient")
    assert reg.status_code == 201
    log = login_api(client, "webpatient@example.com", role="patient")
    assert log.status_code == 200
    token = log.json["token"]
    user_id = log.json["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["role"] = "patient"

    # Pages render 200 in LIVE mode (default)
    home_page = client.get("/connected-care")
    assert home_page.status_code == 200
    # Invariant: LIVE mode must NOT show synthetic demo banner
    assert b"SYNTHETIC DEMO ENVIRONMENT" not in home_page.data
    assert b"Privacy Minimization Active" in home_page.data

    # DEMO mode explicitly shows synthetic demo banner
    demo_app = make_m10_app(tmp_path / "demo_run", CONNECTED_CARE_DATA_MODE="DEMO")
    demo_client = demo_app.test_client()
    register_api(demo_client, "demopatient@example.com", role="patient", name="Demo Patient")
    dlog = login_api(demo_client, "demopatient@example.com", role="patient")
    with demo_client.session_transaction() as sess:
        sess["user_id"] = dlog.json["user"]["id"]
        sess["role"] = "patient"
    demo_home = demo_client.get("/connected-care")
    assert demo_home.status_code == 200
    assert b"SYNTHETIC DEMO ENVIRONMENT" in demo_home.data

    inbox_page = client.get("/connected-care/inbox")
    assert inbox_page.status_code == 200
    assert b"Unified Healthcare Inbox" in inbox_page.data

    diagnostics_page = client.get("/connected-care/diagnostics")
    assert diagnostics_page.status_code == 200

    # API: query context
    ctx_res = client.get("/api/v1/connected-care/context", headers=headers)
    assert ctx_res.status_code == 200
    ctx_data = ctx_res.get_json()
    assert "mental_wellness_conversations" in ctx_data["excluded_fields"]

    # API: pharmacy offers search
    offers_res = client.get("/api/v1/connected-care/pharmacy-offers?q=Metformin", headers=headers)
    assert offers_res.status_code == 200
    assert "offers" in offers_res.get_json()

    # API: next safe actions
    actions_res = client.get("/api/v1/connected-care/next-safe-actions", headers=headers)
    assert actions_res.status_code == 200
    assert "next_safe_actions" in actions_res.get_json()


def test_order_confirmation_api_requires_user_confirmed_flag(tmp_path):
    app = make_m10_app(tmp_path)
    client = app.test_client()

    register_api(client, "guarduser@example.com", role="patient", name="Guard User")
    log = login_api(client, "guarduser@example.com", role="patient")
    token = log.json["token"]
    user_id = log.json["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["role"] = "patient"

    with app.app_context():
        db = get_db()
        p = db.execute("SELECT id FROM users WHERE email='guarduser@example.com'").fetchone()
        pid = p["id"]
        pharm_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) VALUES (?, ?, ?, ?, 'pharmacy', 1, ?, ?)",
            ("Guard Pharmacy", "gp@example.com", "gp@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.execute(
            "INSERT INTO provider_profiles (user_id, organization, provider_type, city, latitude, longitude, delivery_available, delivery_radius_km, delivery_fee_base_inr, created_at, updated_at) VALUES (?, ?, 'pharmacy', 'Delhi', 28.6300, 77.2100, 1, 10.0, 40.0, ?, ?)",
            (pharm_id, "Guard Pharmacy", now_iso(), now_iso()),
        )
        db.commit()

        update_inventory_observation(pharm_id, 5, 50, 30.0, stock_status="CONFIRMED")
        rx = create_prescription(pid, "Dr. Test", [{"medicine_name": "Paracetamol 500 mg", "sku_id": 5}])
        plan = optimize_prescription_fulfilment(rx["id"])
        plan_id = plan["plan_id"]
        assert plan_id is not None

    # Attempt order confirmation without user_confirmed=True -> 400
    res_unconfirmed = client.post(
        "/api/v1/connected-care/orders/confirm",
        json={"plan_id": plan_id, "user_confirmed": False},
        headers=headers,
    )
    assert res_unconfirmed.status_code == 400
    assert "explicit user confirmation" in res_unconfirmed.get_json()["error"]["message"].lower()

    # Confirm with user_confirmed=True -> 200
    res_confirmed = client.post(
        "/api/v1/connected-care/orders/confirm",
        json={"plan_id": plan_id, "user_confirmed": True, "delivery_address": "22 Park Lane"},
        headers=headers,
    )
    assert res_confirmed.status_code == 200
    assert res_confirmed.get_json()["order"]["status"].lower() in ["confirmed", "submitted"]


# ── 9. Permanent Truthfulness Invariant Regression Tests ─────────────────────────

def test_zero_inventory_yields_no_confirmed_offers_and_no_fabricated_data(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        # Searching for medicine with NO inventory records
        offers = search_pharmacy_offers(medicine_ids=[1], city="Delhi")
        # Invariant: No fake pharmacies, no fake stock, no fake offers
        assert len(offers) == 0

        # Optimizer with zero candidate inventory produces NO_CONFIRMED_INVENTORY
        db = get_db()
        p_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) VALUES (?, ?, ?, ?, 'patient', 1, ?, ?)",
            ("ZeroTest", "zero@example.com", "zero@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.commit()

        rx = create_prescription(p_id, "Dr. Real", [{"medicine_name": "Amlodipine 5 mg", "sku_id": 1}])
        plan = optimize_prescription_fulfilment(rx["id"])

        # Invariant: Never fabricates a fallback partner pharmacy or price
        assert plan["plan_id"] is None
        assert plan["status"] == "NO_CONFIRMED_INVENTORY"
        assert plan["options"] == {}
        assert "no confirmed participating pharmacy inventory" in plan["message"].lower()


def test_unknown_inventory_never_promoted_to_confirmed(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        pharm_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) VALUES (?, ?, ?, ?, 'pharmacy', 1, ?, ?)",
            ("Unknown Pharm", "up@example.com", "up@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.execute(
            "INSERT INTO provider_profiles (user_id, organization, provider_type, city, latitude, longitude, delivery_fee_base_inr, created_at, updated_at) VALUES (?, ?, 'pharmacy', 'Delhi', 28.63, 77.21, 40.0, ?, ?)",
            (pharm_id, "Unknown Pharm", now_iso(), now_iso()),
        )
        db.commit()

        update_inventory_observation(pharm_id, 1, quantity=0, price_inr=None, stock_status="UNKNOWN")

        offers = search_pharmacy_offers(medicine_ids=[1], include_unknown=True)
        assert len(offers) == 1
        # Invariant: UNKNOWN is NEVER promoted to CONFIRMED
        assert offers[0]["inventory"][1]["effective_status"] == "UNKNOWN"
        assert offers[0]["inventory"][1]["price_inr"] is None


def test_missing_price_and_distance_never_generates_plausible_defaults(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        pharm_id = db.execute(
            "INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at) VALUES (?, ?, ?, ?, 'pharmacy', 1, ?, ?)",
            ("NoPrice Pharm", "np@example.com", "np@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        # No coordinates in profile
        db.execute(
            "INSERT INTO provider_profiles (user_id, organization, provider_type, city, latitude, longitude, delivery_fee_base_inr, created_at, updated_at) VALUES (?, ?, 'pharmacy', 'Delhi', NULL, NULL, NULL, ?, ?)",
            (pharm_id, "NoPrice Pharm", now_iso(), now_iso()),
        )
        db.commit()

        update_inventory_observation(pharm_id, 1, quantity=10, price_inr=None, stock_status="CONFIRMED")
        offers = search_pharmacy_offers(medicine_ids=[1], patient_lat=28.63, patient_lon=77.21)

        assert len(offers) == 1
        # Invariant: Distance is None and text is "Distance unavailable", never a generated distance
        assert offers[0]["distance_km"] is None
        assert offers[0]["distance_text"] == "Distance unavailable"
        # Invariant: Price is None, never ₹0 or estimated
        assert offers[0]["inventory"][1]["price_inr"] is None

