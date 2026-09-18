from __future__ import annotations

import json
from datetime import datetime, timezone

from tests.test_agent_os_provider_outcome_continuity_v1 import (
    _seed_users_and_appointment,
    _waiting_provider_journey,
)
from tests.test_medical_hybrid_retrieval_v1 import approved_ingestion
from tests.test_milestone1 import login_web, make_app, register_web
from zendoc.agent_planner import build_plan
from zendoc.appointment_continuity import sync_provider_appointment_status
from zendoc.care_chain import (
    build_persisted_care_chain,
    finalize_care_chain,
    prepare_care_chain,
)
from zendoc.db import get_db, now_iso
from zendoc.model_router import ModelResponse, RoutingReason
from zendoc.pharmacy_order_routes import update_medicine_order_status
from zendoc.pharmacy_service import create_medicine_order
from zendoc.specialist_orchestrator import orchestrate_specialist
from zendoc.specialist_workflow_store import persist_specialist_result


PASSWORD = "StrongPass123"


def _patient(app, suffix="chain"):
    stamp = now_iso()
    db = get_db()
    patient_id = db.execute(
        """
        INSERT INTO users
        (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
        VALUES (?,?,?,?, 'patient',1,?,?)
        """,
        (
            f"Care Chain {suffix}",
            f"care-chain-{suffix}@example.test",
            f"care-chain-{suffix}@example.test",
            "unused",
            stamp,
            stamp,
        ),
    ).lastrowid
    db.commit()
    return dict(db.execute("SELECT * FROM users WHERE id=?", (patient_id,)).fetchone())


def _register_api(client, email="care-chain-api@example.test"):
    response = client.post(
        "/api/v1/auth/register",
        json={"name": "Care Chain API", "email": email, "password": PASSWORD, "role": "patient"},
    )
    assert response.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert login.status_code == 200
    return login.get_json()["token"]


def test_prepare_and_finalize_chain_persists_only_metadata(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        patient = _patient(app, "metadata")
        command = "Help me understand basic nutrition and sodium choices."
        plan = build_plan(patient, command)
        assert plan.intent == "nutrition"

        prepared = prepare_care_chain(
            patient,
            command,
            intent=plan.intent,
            privacy_class=plan.privacy_class,
        )
        assert prepared["input"]["status"] == "TYPED_INPUT"
        assert prepared["health_memory"]["status"] == "AUTHORIZED_MINIMUM_METADATA"
        assert prepared["health_memory"]["local_advisory_context_status"] == "AUTHORIZED_MINIMUM_CONTEXT"
        assert set(prepared["health_memory"]["local_advisory_fields"]) == {"allergies"}
        assert "data" not in prepared["health_memory"]
        assert prepared["rag"]["status"] in {"NO_APPROVED_EVIDENCE", "EVIDENCE_READY"}
        assert prepared["local_advisory"]["tool_execution_authority"] is False
        assert prepared["local_advisory"]["cloud_allowed"] is False

        result = orchestrate_specialist(patient, command, {})
        result["care_chain"] = prepared
        result = persist_specialist_result(patient, result, {})
        result = finalize_care_chain(patient, result, prepared)
        get_db().commit()

        assert result["care_chain"]["audit"]["status"] == "RECORDED"
        assert result["care_chain"]["safe_action"]["payment_executed"] is False
        assert result["care_chain"]["provider_confirmation"]["model_can_assert_confirmation"] is False

        task_id = result["workflow_task"]["id"]
        task_row = get_db().execute(
            "SELECT metadata_json FROM agent_tasks WHERE id=?",
            (task_id,),
        ).fetchone()
        metadata = json.loads(task_row["metadata_json"])
        chain_meta = metadata["care_chain"]
        assert chain_meta["raw_prompt_stored"] is False
        assert chain_meta["raw_transcript_stored"] is False
        assert chain_meta["raw_health_memory_stored"] is False
        assert command not in task_row["metadata_json"]

        audit_row = get_db().execute(
            "SELECT * FROM audit_logs WHERE id=?",
            (result["care_chain"]["audit"]["audit_log_id"],),
        ).fetchone()
        assert audit_row["action"] == "care_chain_snapshot"
        assert command not in str(audit_row["entity_id"] or "")


def test_verified_asr_audit_links_voice_input_and_spoofed_id_fails_closed(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        patient = _patient(app, "voice")
        cursor = get_db().execute(
            """
            INSERT INTO audit_logs (actor_id,action,entity_type,entity_id,created_at)
            VALUES (?,?,?,?,?)
            """,
            (
                patient["id"],
                "edgecare_asr_transcribe",
                "local_asr",
                "openai_compatible:whisper_small:success",
                now_iso(),
            ),
        )
        get_db().commit()
        audit_id = int(cursor.lastrowid)

        verified = prepare_care_chain(
            patient,
            "Help me with nutrition basics.",
            intent="nutrition",
            privacy_class="PERSONAL",
            input_channel="local_asr_transcript",
            asr_audit_log_id=audit_id,
        )
        assert verified["input"]["status"] == "VERIFIED_LOCAL_ASR_TRANSCRIPT"
        assert verified["input"]["channel"] == "local_asr_transcript"
        assert verified["input"]["asr_audit_log_id"] == audit_id
        assert verified["input"]["transcript_persisted_by_chain"] is False
        assert verified["input"]["audio_persisted_by_chain"] is False

        spoofed = prepare_care_chain(
            patient,
            "Help me with nutrition basics.",
            intent="nutrition",
            privacy_class="PERSONAL",
            input_channel="local_asr_transcript",
            asr_audit_log_id=audit_id + 99999,
        )
        assert spoofed["input"]["status"] == "UNVERIFIED_INPUT_CHANNEL"
        assert spoofed["input"]["channel"] == "typed_or_unverified"
        assert spoofed["input"]["asr_audit_log_id"] is None


def test_rag_stage_exposes_approved_evidence_metadata_not_excerpts(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        approved_ingestion(app)
        patient = _patient(app, "rag")
        prepared = prepare_care_chain(
            patient,
            "Teach me about hypertension blood pressure monitoring.",
            intent="health_learning",
            privacy_class="HEALTH_SENSITIVE",
        )
        assert prepared["rag"]["status"] == "EVIDENCE_READY"
        assert prepared["rag"]["retrieval_performed"] is True
        assert prepared["rag"]["evidence_count"] > 0
        first = prepared["rag"]["evidence"][0]
        assert first["source_id"] == "icmr_guidelines"
        assert first["document_url"].startswith("https://")
        assert "excerpt" not in first
        assert "text" not in first
        assert prepared["rag"]["answer_generated_by_rag_layer"] is False
        assert prepared["rag"]["healthcare_action_executed"] is False


def test_agent_os_api_returns_canonical_care_chain(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    token = _register_api(client)
    response = client.post(
        "/api/v1/agent/orchestrate",
        json={
            "message": "Help me understand basic nutrition and hydration.",
            "input_channel": "typed",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    chain = payload["care_chain"]
    assert chain["version"] == "2026.1"
    assert chain["input"]["status"] == "TYPED_INPUT"
    assert chain["agent_os"]["deterministic_server_validation"] is True
    assert chain["local_advisory"]["tool_execution_authority"] is False
    assert chain["safe_action"]["clinical_authority_delegated_to_model"] is False
    assert chain["audit"]["raw_prompt_stored"] is False
    assert payload["workflow_task"]["id"]


def test_agent_os_page_exposes_local_voice_without_auto_submit(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "care-chain-web@example.test", "Care Chain Web")
    login_web(client, "patient", "care-chain-web@example.test")

    page = client.get("/agent-os")
    assert page.status_code == 200
    body = page.data.decode()
    assert 'id="assistant-message"' in body
    assert 'id="edgecare-voice-input-toggle"' in body
    assert 'name="input_channel" value="typed"' in body
    assert 'name="asr_audit_log_id" value=""' in body
    assert "edgecare_voice.js" in body
    assert "nothing is auto-submitted" in body.lower()


def test_persisted_chain_reflects_provider_outcome_and_longitudinal_memory(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient, provider, profile_id, appointment_id = _seed_users_and_appointment(
            db, suffix="care-chain-persisted"
        )
        journey, _action = _waiting_provider_journey(patient, appointment_id, profile_id)

        db.execute(
            "UPDATE appointments SET status='confirmed',updated_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), appointment_id),
        )
        db.commit()
        sync_provider_appointment_status(provider, appointment_id)

        confirmed = build_persisted_care_chain(patient, journey["id"])
        assert confirmed["provider_confirmation"]["provider_confirmed"] is True
        assert confirmed["outcome"]["verified"] is False

        db.execute(
            "UPDATE appointments SET status='completed',updated_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), appointment_id),
        )
        db.commit()
        sync_provider_appointment_status(provider, appointment_id)

        completed = build_persisted_care_chain(patient, journey["id"])
        assert completed["provider_confirmation"]["appointment_status"] == "completed"
        assert completed["outcome"]["verified"] is True
        assert completed["outcome"]["care_outcome_id"]
        assert completed["longitudinal_memory"]["provider_recorded"] is True
        assert completed["longitudinal_memory"]["health_memory_event_id"]
        assert completed["truth"]["clinical_findings_inferred_from_completion"] is False

class _FakeLocalCareChainRouter:
    def __init__(self):
        self.calls = []

    def route(self, prompt, *args, **kwargs):
        self.calls.append({"prompt": prompt, "kwargs": dict(kwargs)})
        return ModelResponse(
            text="Local advisory prepared; deterministic Agent OS must decide any action.",
            provider="local_ollama",
            model="synthetic-local-care-model",
            latency_ms=3,
            success=True,
            routing_reason=RoutingReason.LOCAL_SLM,
            task_type=kwargs.get("task_type", "planning_assistance"),
            privacy_class=kwargs.get("privacy_class", "HEALTH_SENSITIVE"),
            output={
                "text": "Local advisory prepared; deterministic Agent OS must decide any action.",
                "data": {},
            },
        )


def test_care_chain_uses_successful_local_slm_only_as_non_executable_advisory(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    router = _FakeLocalCareChainRouter()
    monkeypatch.setattr("zendoc.care_chain.get_model_router", lambda: router)

    with app.app_context():
        patient = _patient(app, "local-slm")
        prepared = prepare_care_chain(
            patient,
            "Help me understand basic nutrition and hydration.",
            intent="nutrition",
            privacy_class="PERSONAL",
        )

        advisory = prepared["local_advisory"]
        assert advisory["status"] == "LOCAL_MODEL_ADVISORY_USED"
        assert advisory["local_model_used"] is True
        assert advisory["provider"] == "local_ollama"
        assert advisory["model"] == "synthetic-local-care-model"
        assert advisory["tool_execution_authority"] is False
        assert advisory["cloud_allowed"] is False

        assert len(router.calls) == 1
        call = router.calls[0]
        assert call["kwargs"]["allow_cloud"] is False
        assert call["kwargs"]["privacy_class"] == "HEALTH_SENSITIVE"
        assert call["kwargs"]["risk_class"] == "read_only"
        assert "Never output a diagnosis" in call["kwargs"]["system_prompt"]
        assert prepared["truth"]["model_output_executes_tools"] is False


def test_emergency_care_chain_skips_rag_and_local_model_before_agent_execution(tmp_path, monkeypatch):
    app = make_app(tmp_path)

    class _MustNotRunRouter:
        def route(self, *args, **kwargs):
            raise AssertionError("Local/cloud model must not run before deterministic emergency safety.")

    monkeypatch.setattr("zendoc.care_chain.get_model_router", lambda: _MustNotRunRouter())

    with app.app_context():
        patient = _patient(app, "emergency")
        prepared = prepare_care_chain(
            patient,
            "I have severe chest pain and cannot breathe properly.",
            intent="general_agent",
            privacy_class="HEALTH_SENSITIVE",
        )

        assert prepared["safety"]["emergency"] is True
        assert prepared["safety"]["model_bypasses_safety"] is False
        assert prepared["rag"]["status"] == "SKIPPED_EMERGENCY_SAFETY"
        assert prepared["rag"]["retrieval_performed"] is False
        assert prepared["local_advisory"]["status"] == "SKIPPED_EMERGENCY_SAFETY"
        assert prepared["local_advisory"]["local_model_used"] is False
        assert prepared["local_advisory"]["tool_execution_authority"] is False

def test_persisted_chain_tracks_verified_internal_pharmacy_service_confirmation_without_external_claim(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient = _patient(app, "service-pharmacy")
        stamp = now_iso()
        pharmacy_id = db.execute(
            """
            INSERT INTO users
            (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
            VALUES ('Chain Pharmacy','chain-pharmacy@example.test','chain-pharmacy@example.test',
                    'unused','pharmacy',1,?,?)
            """,
            (stamp, stamp),
        ).lastrowid
        db.execute(
            """
            INSERT INTO provider_profiles
            (user_id,provider_type,verification_status,created_at,updated_at)
            VALUES (?,'pharmacy','verified',?,?)
            """,
            (pharmacy_id, stamp, stamp),
        )
        db.commit()

        order = create_medicine_order(
            patient,
            {
                "items": [{"name": "ORS", "quantity": 1}],
                "delivery_address": "Care chain test address",
                "pharmacy_id": int(pharmacy_id),
            },
        )
        action = db.execute(
            """
            SELECT * FROM care_actions
            WHERE service_ref=? AND patient_id=?
            ORDER BY id DESC LIMIT 1
            """,
            (f"zendoc_pharmacy_order:{int(order['id'])}", int(patient["id"])),
        ).fetchone()
        assert action is not None
        journey_id = int(action["journey_id"])

        staged = build_persisted_care_chain(patient, journey_id)
        staged_confirmation = staged["provider_confirmation"]
        assert staged_confirmation["status"] == "WAITING_SERVICE_CONFIRMATION"
        assert staged_confirmation["internally_integrated"] is True
        assert staged_confirmation["integration_source_type"] == "pharmacy_order"
        assert staged_confirmation["service_status"] == "STAGED"
        assert staged_confirmation["service_confirmed"] is False
        assert staged_confirmation["authoritative_confirmation"] is False
        assert staged_confirmation["external_execution"] is False

        pharmacy = {"id": int(pharmacy_id), "role": "pharmacy"}
        update_medicine_order_status(pharmacy, int(order["id"]), "accepted")
        confirmed = build_persisted_care_chain(patient, journey_id)
        confirmed_state = confirmed["provider_confirmation"]
        assert confirmed_state["status"] == "SERVICE_CONFIRMED"
        assert confirmed_state["service_status"] == "CONFIRMED"
        assert confirmed_state["service_confirmed"] is True
        assert confirmed_state["authoritative_confirmation"] is True
        assert confirmed_state["external_execution"] is False
        assert confirmed["outcome"]["verified"] is False

        update_medicine_order_status(pharmacy, int(order["id"]), "preparing")
        update_medicine_order_status(pharmacy, int(order["id"]), "completed")
        completed = build_persisted_care_chain(patient, journey_id)
        completed_state = completed["provider_confirmation"]
        assert completed_state["status"] == "SERVICE_COMPLETED"
        assert completed_state["service_status"] == "COMPLETED"
        assert completed_state["authoritative_confirmation"] is True
        assert completed_state["external_execution"] is False
        # Internal pharmacy completion is not silently upgraded into a verified
        # clinical outcome or external fulfilment claim.
        assert completed["outcome"]["verified"] is False
        assert completed["truth"]["internal_service_state_is_external_execution"] is False

