"""
ZENDOC Milestone 11: Trust-First Intelligence & Healthcare Orchestration Test Suite

Verifies:
1. Emergency red-flag safety triage executes before any orchestration.
2. Subject resolution distinguishes self from family members with strict authorization gates.
3. Repetitive friction minimization auto-resolves saved locations and active prescriptions.
4. Consequential action gating: multi-step staging halts before order dispatch without user confirmation.
5. Absolute truthfulness: zero inventory returns truthful explanation without synthetic fabrication in live mode.
6. Clinical safeguards: low-confidence extractions require explicit human review.
7. Trust Center: transparency into provenance, active consents, and instant revocation.
8. Inbox 2.0: priority action-required states and contextual next safe actions.
9. Full integration with ZendocIntelligence layer.
"""
from __future__ import annotations

import json
import pytest

from zendoc import create_app
from zendoc.care_graph import get_patient_care_graph, record_care_continuity_event
from zendoc.context_engine import create_or_update_consent_grant, revoke_consent_grant
from zendoc.db import get_db, now_iso
from zendoc.family_care import add_family_member, create_family_access_grant
from zendoc.intelligence import ZendocIntelligence
from zendoc.inventory_service import update_inventory_observation
from zendoc.locations import save_location
from zendoc.orchestrator import HealthcareOrchestrator, resolve_subject_location
from zendoc.prescription_service import create_prescription
from zendoc.subject_resolver import resolve_request_subject


PASSWORD = "StrongPass123"


def make_m11_app(tmp_path, db_path=None, **overrides):
    config = {
        "TESTING": True,
        "DATABASE": str(db_path or (tmp_path / "m11-test.db")),
        "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        "SECRET_KEY": "m11-test-secret",
        "ADMIN_EMAIL": "owner@example.com",
        "ADMIN_PASSWORD": "OwnerStrong123",
        "RATE_LIMIT_PER_MINUTE": 1000,
        "CONNECTED_CARE_DATA_MODE": "LIVE",
    }
    config.update(overrides)
    return create_app(config)


def seed_test_user(db, name, email, role="patient", city="Bengaluru"):
    now = now_iso()
    cur = db.execute(
        "INSERT INTO users (name, email, email_normalized, password_hash, role, active, city, created_at, updated_at) VALUES (?, ?, ?, 'hash', ?, 1, ?, ?, ?)",
        (name, email, email.lower(), role, city, now, now),
    )
    db.commit()
    return cur.lastrowid


# ── 1. Emergency Safety Triage Always First ─────────────────────────────────────

def test_emergency_red_flag_bypasses_orchestration_to_immediate_safety(tmp_path):
    app = make_m11_app(tmp_path)
    with app.app_context():
        db = get_db()
        user_id = seed_test_user(db, "Test User", "test@example.com")
        user = {"id": user_id, "role": "patient"}

        orch = HealthcareOrchestrator()
        plan = orch.orchestrate(user, "I have severe crushing chest pain and shortness of breath")

        assert plan.status == "EMERGENCY"
        assert plan.urgency == "emergency"
        assert "EMERGENCY SAFETY ALERT" in plan.explanation
        assert "call_108" in plan.next_safe_actions
        assert plan.action_preview is None


# ── 2. Subject Resolution & Family Authorization Gates ─────────────────────────

def test_subject_resolution_self_vs_family_unauthorized(tmp_path):
    app = make_m11_app(tmp_path)
    with app.app_context():
        db = get_db()
        user_id = seed_test_user(db, "Rahul Sharma", "rahul@example.com")
        user = {"id": user_id, "role": "patient", "name": "Rahul Sharma"}

        # 1. Self query
        res_self = resolve_request_subject(user, "Find medicines for my cough")
        assert res_self.is_self is True
        assert res_self.patient_id == user_id
        assert res_self.authorized is True

        # 2. Family query without grant
        res_mother = resolve_request_subject(user, "Find medicines for my mother")
        assert res_mother.is_self is False
        assert res_mother.relationship == "mother"
        assert res_mother.authorized is False
        assert res_mother.requires_consent is True

        # Orchestration returns BLOCKED_PERMISSION
        orch = HealthcareOrchestrator()
        plan = orch.orchestrate(user, "My mother was prescribed these medicines. Find the best available way to get them.")
        assert plan.status == "BLOCKED_PERMISSION"
        assert "active family consent grant is required" in plan.explanation
        assert "request_family_consent" in plan.next_safe_actions


def test_subject_resolution_family_authorized_permitted(tmp_path):
    app = make_m11_app(tmp_path)
    with app.app_context():
        db = get_db()
        son_id = seed_test_user(db, "Aman Gupta", "aman@example.com")
        mother_id = seed_test_user(db, "Sunita Gupta", "sunita@example.com")

        son = {"id": son_id, "role": "patient", "name": "Aman Gupta"}
        mother = {"id": mother_id, "role": "patient", "name": "Sunita Gupta"}

        # Add family member under son's account
        add_family_member(son, {
            "member_name": "Sunita Gupta",
            "relationship": "mother",
            "age": 62,
            "gender": "female",
            "city": "Bengaluru",
        })

        # Mother grants family access to son
        create_family_access_grant(mother, {
            "grantee_id": son_id,
            "scopes": ["pharmacy", "care_tasks", "reports"],
        })

        res = resolve_request_subject(son, "My mother was prescribed medicines", requested_scope="pharmacy")
        assert res.is_self is False
        assert res.patient_id == mother_id
        assert res.relationship == "mother"
        assert res.authorized is True


# ── 3. Friction Minimization via Saved Location Auto-Resolution ────────────────

def test_frictionless_saved_location_auto_resolution(tmp_path):
    app = make_m11_app(tmp_path)
    with app.app_context():
        db = get_db()
        son_id = seed_test_user(db, "Aman Gupta", "aman2@example.com")
        son = {"id": son_id, "role": "patient"}

        # Son saves parent home location
        save_location(son, {
            "label": "Mother's Home",
            "address": "42 Indiranagar, 100ft Road",
            "city": "Bengaluru",
            "location_type": "parent_home",
            "latitude": 12.9716,
            "longitude": 77.5946,
        })

        loc = resolve_subject_location(son, subject_patient_id=999, relationship="mother")
        assert loc is not None
        assert loc["city"] == "Bengaluru"
        assert loc["latitude"] == 12.9716
        assert loc["source"] == "SAVED_LOCATION_PARENT"


# ── 4. Signature Scenario: End-to-End Family Fulfilment Orchestration ─────────

def test_signature_scenario_family_medicine_fulfilment_with_confirmation(tmp_path):
    app = make_m11_app(tmp_path)
    with app.app_context():
        db = get_db()
        son_id = seed_test_user(db, "Aman Gupta", "aman3@example.com")
        mother_id = seed_test_user(db, "Sunita Gupta", "sunita3@example.com")
        pharmacy_id = seed_test_user(db, "Apollo Indiranagar", "apollo@example.com", role="pharmacy")

        son = {"id": son_id, "role": "patient", "name": "Aman Gupta"}
        mother = {"id": mother_id, "role": "patient", "name": "Sunita Gupta"}
        pharmacy = {"id": pharmacy_id, "role": "pharmacy"}

        now = now_iso()
        # Seed verified provider profile for pharmacy in Bengaluru
        db.execute(
            """
            INSERT INTO provider_profiles
            (user_id, provider_type, organization, city, latitude, longitude, verification_status, digitalization_level, delivery_fee_base_inr, created_at, updated_at)
            VALUES (?, 'pharmacy', 'Apollo Indiranagar', 'Bengaluru', 12.9716, 77.5946, 'verified', 2, 50.0, ?, ?)
            """,
            (pharmacy_id, now, now),
        )
        db.commit()

        # 1. Authorize son
        add_family_member(son, {
            "member_name": "Sunita Gupta",
            "relationship": "mother",
            "city": "Bengaluru",
        })
        create_family_access_grant(mother, {
            "grantee_id": son_id,
            "scopes": ["pharmacy", "care_tasks"],
        })

        # 2. Save parent location
        save_location(son, {
            "label": "Mother's Home",
            "address": "12 Richmond Road",
            "city": "Bengaluru",
            "location_type": "parent_home",
            "latitude": 12.9716,
            "longitude": 77.5946,
        })

        # 3. Retrieve or seed medication SKU
        sku_row = db.execute("SELECT id FROM medication_skus WHERE sku_code='MET500'").fetchone()
        if sku_row:
            sku_id = sku_row["id"]
        else:
            cur = db.execute(
                """
                INSERT INTO medication_skus
                (sku_code, name, generic_name, form, strength, mrp_inr, rx_required, created_at)
                VALUES ('MET500', 'Metformin 500mg', 'Metformin Hydrochloride', 'tablet', '500mg', 120.0, 1, ?)
                """,
                (now,),
            )
            db.commit()
            sku_id = cur.lastrowid

        # 4. Mother has active prescription for this medication
        rx = create_prescription(
            patient_id=mother_id,
            prescriber_name="Dr. V. Rao",
            items=[{
                "name": "Metformin 500mg",
                "quantity_prescribed": 30,
                "dosage": "500mg daily",
                "extraction_confidence": 0.98,
                "sku_id": sku_id,
            }],
        )
        assert rx["needs_review"] is False

        # 5. Pharmacy has confirmed inventory in stock (quantity 50 >= 30 prescribed)
        update_inventory_observation(
            pharmacy_id=pharmacy_id,
            sku_id=sku_id,
            quantity=50,
            price_inr=110.0,
            stock_status="CONFIRMED",
            source="pharmacy_manual",
        )

        # 6. Execute orchestration: "My mother was prescribed these medicines..."
        orch = HealthcareOrchestrator()
        plan = orch.orchestrate(
            son,
            "My mother was prescribed these medicines. Find the best available way to get them near her home.",
        )

        # Invariant: Consequential action halts at AWAITING_CONFIRMATION
        assert plan.status == "AWAITING_CONFIRMATION"
        assert plan.action_preview is not None
        assert plan.action_preview.action_type == "ORDER_MEDICINES"
        assert plan.action_preview.requires_user_confirmation is True
        assert plan.action_preview.total_cost_inr > 0
        assert plan.plan_hash is not None

        # Invariant: Executing without user_confirmed=True fails
        with pytest.raises(PermissionError, match="Explicit user confirmation"):
            orch.confirm_and_execute(
                actor=son,
                plan_id=plan.action_preview.plan_id,
                user_confirmed=False,
                delivery_address="12 Richmond Road",
            )

        # 7. Explicit user confirmation executes order
        result = orch.confirm_and_execute(
            actor=son,
            plan_id=plan.action_preview.plan_id,
            user_confirmed=True,
            delivery_address="12 Richmond Road",
            expected_plan_hash=plan.plan_hash,
        )

        assert result["status"] == "EXECUTED"
        receipt = result["receipt"]
        assert receipt["status"] == "SUBMITTED"
        assert receipt["order_id"] > 0
        assert receipt["delivery_address"] == "12 Richmond Road"

        # Invariant: Care Graph records continuity event
        graph = get_patient_care_graph(mother_id, actor=mother)
        assert len(graph["events"]) > 0
        event_types = [e["event_type"] for e in graph["events"]]
        assert "ORDER_SUBMITTED" in event_types


# ── 5. Truthful Zero-Inventory Handling ────────────────────────────────────────

def test_truthful_zero_inventory_orchestration_response(tmp_path):
    app = make_m11_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = seed_test_user(db, "Karan Joshi", "karan@example.com")
        patient = {"id": patient_id, "role": "patient"}

        # Seed unique medication SKU
        now = now_iso()
        db.execute(
            """
            INSERT INTO medication_skus
            (sku_code, name, generic_name, form, strength, mrp_inr, rx_required, created_at)
            VALUES ('TEST_ATOR20', 'Atorvastatin 20mg', 'Atorvastatin', 'tablet', '20mg', 180.0, 1, ?)
            """,
            (now,),
        )
        sku_id = db.execute("SELECT id FROM medication_skus WHERE sku_code='TEST_ATOR20'").fetchone()["id"]
        db.commit()

        # Patient has prescription
        create_prescription(
            patient_id=patient_id,
            prescriber_name="Dr. Mehta",
            items=[{
                "name": "Atorvastatin 20mg",
                "quantity_prescribed": 30,
                "dosage": "20mg at bedtime",
                "extraction_confidence": 0.95,
                "sku_id": sku_id,
            }],
        )

        # ZERO inventory observations in DB
        orch = HealthcareOrchestrator()
        plan = orch.orchestrate(patient, "Find best way to get my prescribed medicines near my home")

        assert plan.status == "COMPLETED"
        assert plan.action_preview is None
        assert "No confirmed participating pharmacy inventory" in plan.explanation
        assert "increase_search_radius" in plan.next_safe_actions


# ── 6. Clinical Uncertainty Safeguard ──────────────────────────────────────────

def test_clinical_uncertainty_guard_blocks_unreviewed_extraction(tmp_path):
    app = make_m11_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = seed_test_user(db, "Anita Roy", "anita@example.com")
        patient = {"id": patient_id, "role": "patient"}

        # Prescription with low extraction confidence (confidence 0.60 < 0.90)
        rx = create_prescription(
            patient_id=patient_id,
            prescriber_name="Dr. Sen",
            items=[{
                "name": "Amoxicillin 500mg",
                "quantity_prescribed": 15,
                "extraction_confidence": 0.60,
            }],
        )
        assert rx["needs_review"] is True

        orch = HealthcareOrchestrator()
        plan = orch.orchestrate(patient, "Order my prescribed medicines")

        assert plan.status == "BLOCKED_DATA"
        assert "confirm the exact medication" in plan.explanation
        assert "review_prescription_items" in plan.next_safe_actions


# ── 7. Trust Center API & Consent Revocation ───────────────────────────────────

def test_trust_center_api_and_consent_revocation(tmp_path):
    app = make_m11_app(tmp_path)
    client = app.test_client()

    with app.app_context():
        db = get_db()
        user_id = seed_test_user(db, "Vivek Nair", "vivek@example.com")
        pharmacy_id = seed_test_user(db, "Local Meds", "localmeds@example.com", role="pharmacy")

        user = {"id": user_id, "role": "patient"}

        # Create active consent grant
        grant = create_or_update_consent_grant(
            subject_id=user_id,
            grantee_id=pharmacy_id,
            purpose="pharmacy_fulfilment",
            scopes=["prescriptions", "delivery_address"],
            actor=user,
        )

        # Login session
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["csrf_token"] = "valid_csrf_123"

        # 1. Fetch trust center JSON
        res = client.get("/api/v1/connected-care/trust-center")
        assert res.status_code == 200
        data = res.get_json()
        assert data["patient_id"] == user_id
        assert len(data["consent_grants"]) == 1
        assert data["consent_grants"][0]["id"] == grant["id"]

        # 2. Revoke consent grant
        res_revoke = client.post(
            "/api/v1/connected-care/trust-center/revoke",
            headers={"X-CSRF-Token": "valid_csrf_123"},
            json={"grant_type": "consent", "grant_id": grant["id"]},
        )
        assert res_revoke.status_code == 200
        assert res_revoke.get_json()["revoked"] is True

        # 3. Confirm it is revoked
        res_after = client.get("/api/v1/connected-care/trust-center")
        assert len(res_after.get_json()["consent_grants"]) == 0


# ── 8. Inbox 2.0 Action Required States ────────────────────────────────────────

def test_inbox_2_action_required_and_next_safe_actions(tmp_path):
    app = make_m11_app(tmp_path)
    client = app.test_client()

    with app.app_context():
        db = get_db()
        user_id = seed_test_user(db, "Pooja Verma", "pooja@example.com")

        # Seed a staged plan for this user
        now = now_iso()
        db.execute(
            """
            INSERT INTO fulfilment_plans
            (plan_uid, patient_id, actor_id, prescription_id, strategy_type, strategy_name, item_total_inr, delivery_fee_inr, total_inr, plan_hash, why_explanation, status, data_mode, created_at)
            VALUES ('plan_test_1', ?, ?, NULL, 'single_store', 'Complete Lowest Cost', 200.0, 40.0, 240.0, 'hash_abc123', '["Best match"]', 'staged', 'LIVE', ?)
            """,
            (user_id, user_id, now),
        )
        db.commit()

        with client.session_transaction() as sess:
            sess["user_id"] = user_id

        res = client.get("/connected-care/inbox")
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert "Action Required" in html
        assert "Pending Reviews &amp; Confirmations" in html
        assert "Review &amp; Confirm" in html
        assert "Trust Center" in html


# ── 9. Intelligence Layer Routing Integration ─────────────────────────────────

def test_intelligence_respond_routes_orchestration(tmp_path):
    app = make_m11_app(tmp_path)
    with app.app_context():
        db = get_db()
        user_id = seed_test_user(db, "Siddharth Sen", "sid@example.com")
        user = {"id": user_id, "role": "patient", "name": "Siddharth Sen"}

        result, latency = ZendocIntelligence().respond(
            "My mother was prescribed these medicines. Find the best available way to get them near her home.",
            user=user,
        )

        assert result.provider == "healthcare_orchestrator"
        assert "orchestration_plan" in result.model_metadata
        plan_data = result.model_metadata["orchestration_plan"]
        assert plan_data["subject_relationship"] == "mother"
        assert len(result.possible_actions) > 0


# ── 10. PERMANENT REGRESSION: Emergency Detection ≠ Ambulance Dispatch ──────
#
# Invariant (must never be broken):
#   ZENDOC has NO live ambulance-dispatch integration.
#   Detecting an emergency NEVER means an ambulance was dispatched.
#   Status EMERGENCY means: user was given guidance to call 108 / go to ER.
#   Status AMBULANCE_DISPATCHED must never appear in any orchestration plan.
#
# This test is a permanent regression guard.  If it ever fails it means
# a developer introduced fake dispatch behaviour and the build must be stopped.

def test_emergency_dispatch_is_integration_required(tmp_path):
    """
    REGRESSION GUARD — DO NOT REMOVE OR WEAKEN.

    Verifies three invariants:
    1. EMERGENCY_DETECTED (plan.status == "EMERGENCY") is NOT equal to
       AMBULANCE_DISPATCHED — no dispatch confirmation, ID, ETA, driver,
       or GPS coordinates are returned.
    2. The emergency plan contains ONLY: local guidance, call-108 instruction,
       and find_nearest_er action.  No external service call result is present.
    3. Care Graph does NOT record an AMBULANCE_DISPATCHED event — only a
       local EMERGENCY_ALERT event may be recorded.
    """
    app = make_m11_app(tmp_path)
    with app.app_context():
        db = get_db()
        user_id = seed_test_user(db, "Audit User", "audit@example.com")
        user = {"id": user_id, "role": "patient"}

        orch = HealthcareOrchestrator()

        # Use the exact sentence from the audit directive
        plan = orch.orchestrate(user, "I have severe chest pain and difficulty breathing")

        # ── Invariant 1: status is EMERGENCY, not AMBULANCE_DISPATCHED ───────
        assert plan.status == "EMERGENCY", (
            f"Expected status EMERGENCY, got {plan.status!r}"
        )
        assert plan.status != "AMBULANCE_DISPATCHED", (
            "CRITICAL: plan.status must never be AMBULANCE_DISPATCHED — "
            "no live dispatch integration exists."
        )

        # ── Invariant 2: no fake dispatch artifacts in plan or steps ─────────
        plan_dict = plan.to_dict()
        plan_str = str(plan_dict).lower()

        # These strings must never appear in any orchestration output
        forbidden_phrases = [
            "ambulance dispatched",
            "ambulance_dispatched",
            "dispatch_id",
            "dispatch id",
            "eta_minutes",
            "driver_name",
            "driver_id",
            "fake",
            "ambulance is on the way",
            "ambulance has been sent",
        ]
        for phrase in forbidden_phrases:
            assert phrase not in plan_str, (
                f"CRITICAL: Forbidden phrase {phrase!r} found in emergency "
                f"orchestration output. ZENDOC has no live dispatch integration. "
                f"Remove all fake dispatch data immediately."
            )

        # ── Invariant 3: plan contains truthful guidance, not a real result ──
        # The escalation step result must only contain action=CALL_108 + guidance
        escalation_step = next(
            (s for s in plan.steps if s.step_id == "escalation"), None
        )
        assert escalation_step is not None, "escalation step must be present"
        result_keys = set(escalation_step.result.keys()) if escalation_step.result else set()
        # Only allowed keys in escalation result
        assert result_keys <= {"action", "guidance"}, (
            f"escalation step result contains unexpected keys: {result_keys - {'action', 'guidance'}}. "
            f"These may represent fake dispatch data."
        )
        assert escalation_step.result.get("action") == "CALL_108", (
            f"escalation action must be CALL_108, got {escalation_step.result.get('action')!r}"
        )

        # ── Invariant 4: Care Graph does NOT record AMBULANCE_DISPATCHED ─────
        graph = get_patient_care_graph(user_id, actor=user)
        events = graph.get("events", [])
        dispatched_events = [
            e for e in events
            if "AMBULANCE_DISPATCHED" in str(e).upper()
        ]
        assert len(dispatched_events) == 0, (
            f"CRITICAL: Care Graph contains AMBULANCE_DISPATCHED events: "
            f"{dispatched_events}. No real dispatch integration exists — "
            f"these records are fabricated."
        )

        # ── Invariant 5: next_safe_actions only reference local actions ───────
        for action in plan.next_safe_actions:
            assert action in ("call_108", "call_112", "find_nearest_er"), (
                f"next_safe_action {action!r} is not a valid local-only action. "
                f"Only call_108, call_112, find_nearest_er are permitted."
            )
