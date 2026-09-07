from datetime import datetime, timedelta, timezone

import pytest

from zendoc.agent_executor import (
    _diagnostic_options,
    _health_memory_context,
    _latest_prescription_review,
    _pharmacy_search,
    execute_plan,
)
from zendoc.agent_planner import build_plan
from zendoc.agent_task_engine import create_agent_task
from zendoc.context_engine import create_or_update_consent_grant
from zendoc.db import get_db, now_iso
from zendoc.diagnostic_service import AVAILABILITY_CONFIRMED
from zendoc.operations_automation import run_safe_operations_automation
from zendoc.prescription_service import create_prescription
from tests.test_milestone10_connected_care import make_m10_app


def test_provider_discovery_agent_executes_registered_provider_search(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        doctor_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,city,active,created_at,updated_at) VALUES (?,?,?,?, 'doctor','Kolkata',1,?,?)",
            ("Dr Test", "drtest@example.com", "drtest@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.execute(
            """
            INSERT INTO provider_profiles
            (user_id, provider_type, specialty, organization, city, verification_status, created_at, updated_at)
            VALUES (?, 'doctor', 'Cardiology', 'Test Heart Clinic', 'Kolkata', 'verified', ?, ?)
            """,
            (doctor_id, now_iso(), now_iso()),
        )
        db.commit()

        actor = {"id": 999, "role": "patient", "city": "Kolkata", "active": 1}
        plan = build_plan(actor, "Find cardiology doctor near me")
        assert plan.assigned_agent == "ProviderDiscoveryAgent"
        result = execute_plan(plan, actor)
        output = result["tool_results"][0]["output"]
        assert output["registered_providers"]
        assert output["registered_providers"][0]["source"] == "zendoc_provider_network"


def test_medication_safety_agent_reads_latest_prescription_without_changing_it(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?, 'patient',1,?,?)",
            ("Rx Patient", "rxagent@example.com", "rxagent@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.commit()
        rx = create_prescription(
            patient_id=patient_id,
            prescriber_name="Dr Safe",
            items=[{"medicine_name": "Metformin 500 mg", "sku_id": 2, "extraction_confidence": 0.99}],
        )

        actor = {"id": patient_id, "role": "patient", "active": 1}
        plan = build_plan(actor, "Check my prescription medicine strength")
        assert plan.assigned_agent == "MedicationSafetyAgent"
        result = execute_plan(plan, actor)
        output = result["tool_results"][0]["output"]
        assert output["prescription_id"] == rx["id"]
        assert output["status"] == "FULFILMENT_READY"
        assert output["fulfilment_ready"] is True
        assert "No medicine substitution" in output["safety_notice"]


def test_diagnostics_agent_returns_confirmed_fresh_offer(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,city,active,created_at,updated_at) VALUES (?,?,?,?, 'patient','Kolkata',1,?,?)",
            ("Diag Patient", "diagagent@example.com", "diagagent@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        lab_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,city,active,created_at,updated_at) VALUES (?,?,?,?, 'hospital','Kolkata',1,?,?)",
            ("Fresh Lab", "freshlab@example.com", "freshlab@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.execute(
            "INSERT INTO provider_profiles (user_id,organization,provider_type,city,verification_status,created_at,updated_at) VALUES (?,?,'lab','Kolkata','verified',?,?)",
            (lab_id, "Fresh Lab", now_iso(), now_iso()),
        )
        db.execute(
            "INSERT INTO diagnostic_offers (lab_id,test_id,price_inr,home_collection_available,home_collection_fee_inr,verified,data_mode,observed_at,created_at) VALUES (?,1,400,1,0,1,'LIVE',?,?)",
            (lab_id, now_iso(), now_iso()),
        )
        db.commit()

        actor = {"id": patient_id, "role": "patient", "city": "Kolkata", "active": 1}
        plan = build_plan(actor, "Find CBC blood test in Kolkata")
        assert plan.assigned_agent == "DiagnosticsAgent"
        result = execute_plan(plan, actor)
        output = result["tool_results"][0]["output"]
        assert output["status"] == "OK"
        assert output["offers"][0]["availability_state"] == AVAILABILITY_CONFIRMED


def test_safe_operations_automation_requeues_only_retriable_task(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        owner = db.execute("SELECT * FROM users WHERE role='admin' LIMIT 1").fetchone()
        owner_actor = dict(owner)
        task = create_agent_task(
            task_type="integration_retry_test",
            requested_by=owner["id"],
            assigned_agent="OperationsAgent",
            max_attempts=3,
            actor=owner_actor,
        )
        db.execute(
            "UPDATE agent_tasks SET status='failed', attempt_count=1, last_error_category='timeout' WHERE id=?",
            (task["id"],),
        )
        db.commit()

        result = run_safe_operations_automation(owner_actor)
        assert result["requeued_count"] == 1
        assert result["executed_tasks"] == 0
        assert all(value is False for value in result["safety"].values())
        updated = db.execute("SELECT * FROM agent_tasks WHERE id=?", (task["id"],)).fetchone()
        assert updated["status"] == "queued"


def test_safe_operations_automation_rejects_normal_user(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        with pytest.raises(PermissionError):
            run_safe_operations_automation({
                "id": 123,
                "role": "patient",
                "active": 1,
                "email": "normal@example.com",
            })


def test_health_memory_agent_routes_to_authorized_minimum_context(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,city,active,created_at,updated_at) VALUES (?,?,?,?, 'patient','Kolkata',1,?,?)",
            ("Memory Patient", "memoryagent@example.com", "memoryagent@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.commit()

        actor = {"id": patient_id, "role": "patient", "city": "Kolkata", "active": 1}
        plan = build_plan(actor, "Show my health memory timeline")
        assert plan.assigned_agent == "HealthMemoryAgent"
        assert plan.intent == "health_records"
        assert plan.steps[0].tool_name == "get_health_memory_context"

        result = execute_plan(plan, actor)
        output = result["tool_results"][0]["output"]
        assert output["status"] == "OK"
        assert output["patient_id"] == patient_id
        assert output["context_contract"]["consent_status"] == "NOT_REQUIRED_SELF"
        assert "complete_lifetime_memory" in output["context_contract"]["excluded_fields"]
        assert output["health_memory"]["patient_id"] == patient_id
        assert "diagnose" in output["safety_notice"].lower()


def test_health_memory_agent_blocks_cross_patient_idor_without_consent(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        actor_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?, 'patient',1,?,?)",
            ("Actor Patient", "memoryactor@example.com", "memoryactor@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        target_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?, 'patient',1,?,?)",
            ("Other Patient", "memorytarget@example.com", "memorytarget@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.commit()

        actor = {"id": actor_id, "role": "patient", "active": 1}
        with pytest.raises(PermissionError):
            _health_memory_context(actor, {"patient_id": target_id})


def test_hospital_health_memory_requires_explicit_patient_consent(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,city,active,created_at,updated_at) VALUES (?,?,?,?, 'patient','Kolkata',1,?,?)",
            ("Consent Patient", "consentpatient@example.com", "consentpatient@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        hospital_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,city,active,created_at,updated_at) VALUES (?,?,?,?, 'hospital','Kolkata',1,?,?)",
            ("Consent Hospital", "consenthospital@example.com", "consenthospital@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.commit()

        actor = {"id": hospital_id, "role": "hospital", "city": "Kolkata", "active": 1}

        with pytest.raises(PermissionError):
            _health_memory_context(actor, {"patient_id": patient_id})

        create_or_update_consent_grant(
            subject_id=patient_id,
            grantee_id=hospital_id,
            purpose="health_memory_view",
            scopes=["timeline"],
            actor={"id": patient_id, "role": "patient", "active": 1},
        )

        output = _health_memory_context(actor, {"patient_id": patient_id})
        assert output["patient_id"] == patient_id
        assert output["context_contract"]["consent_status"] == "ACTIVE"
        assert "complete_lifetime_memory" in output["context_contract"]["excluded_fields"]


@pytest.mark.parametrize(
    ("handler", "arguments"),
    [
        (_latest_prescription_review, {}),
        (_diagnostic_options, {"query": "CBC"}),
        (_pharmacy_search, {"query": "Metformin"}),
    ],
)
def test_specialist_handlers_block_cross_patient_target_without_consent(tmp_path, handler, arguments):
    app = make_m10_app(tmp_path)
    with app.app_context():
        db = get_db()
        actor_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?, 'patient',1,?,?)",
            ("Adversary", "adversary@example.com", "adversary@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        target_id = db.execute(
            "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?, 'patient',1,?,?)",
            ("Target", "specialisttarget@example.com", "specialisttarget@example.com", "hash", now_iso(), now_iso()),
        ).lastrowid
        db.commit()

        actor = {"id": actor_id, "role": "patient", "active": 1}
        attempted = dict(arguments)
        attempted["patient_id"] = target_id

        with pytest.raises(PermissionError):
            handler(actor, attempted)


def test_emergency_precedence_beats_health_memory_specialist_routing(tmp_path):
    app = make_m10_app(tmp_path)
    with app.app_context():
        actor = {"id": 777, "role": "patient", "active": 1}
        plan = build_plan(actor, "Show my health memory, I have severe chest pain and cannot breathe")
        assert plan.intent == "emergency"
        assert plan.assigned_agent == "SafetyAgent"
        assert plan.steps == ()
        assert plan.urgency == "emergency"
