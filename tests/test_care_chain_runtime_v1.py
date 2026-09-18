import json

from zendoc.agent_planner import build_plan
from zendoc.care_chain import finalize_care_chain, prepare_care_chain
from zendoc.db import get_db, now_iso
from zendoc.model_router import reset_model_router
from zendoc.specialist_orchestrator import orchestrate_specialist
from zendoc.specialist_workflow_store import persist_specialist_result
from tests.test_milestone1 import make_app


def _seed_patient():
    db = get_db()
    stamp = now_iso()
    patient_id = db.execute(
        """
        INSERT INTO users
        (name,email,email_normalized,password_hash,role,active,city,created_at,updated_at)
        VALUES ('Care Chain Patient','care-chain-runtime@example.test',
                'care-chain-runtime@example.test','unused','patient',1,'Kalyani',?,?)
        """,
        (stamp, stamp),
    ).lastrowid
    db.commit()
    return dict(db.execute("SELECT * FROM users WHERE id=?", (patient_id,)).fetchone())


def test_care_chain_connects_grounding_agent_os_and_metadata_audit_without_overclaiming(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENDOC_PLACES_PROVIDER", "none")
    monkeypatch.setenv("ZENDOC_LOCAL_AI_ENABLED", "0")
    reset_model_router()
    app = make_app(tmp_path)

    with app.app_context():
        patient = _seed_patient()
        command = "Book appointment with a cardiologist in Kalyani next week"
        plan = build_plan(patient, command)

        prepared = prepare_care_chain(
            patient,
            command,
            intent=plan.intent,
            privacy_class=plan.privacy_class,
            input_channel="typed",
        )
        assert prepared["input"]["status"] == "TYPED_INPUT"
        assert prepared["input"]["manual_submit_required"] is True
        assert prepared["health_memory"]["status"] == "AUTHORIZED_MINIMUM_METADATA"
        assert prepared["health_memory"]["raw_events_exposed_to_chain"] is False
        assert prepared["health_memory"]["local_advisory_fields"] == ["city"]
        assert prepared["rag"]["status"] == "NOT_REQUIRED_FOR_LOGISTICS"
        assert prepared["local_advisory"]["tool_execution_authority"] is False
        assert prepared["local_advisory"]["cloud_allowed"] is False
        assert prepared["truth"]["model_output_executes_tools"] is False

        result = orchestrate_specialist(patient, command, {})
        result["care_chain"] = prepared
        result = persist_specialist_result(patient, result, {})
        result = finalize_care_chain(patient, result, prepared)

        chain = result["care_chain"]
        assert chain["agent_os"]["assigned_agent"] == "BookingAgent"
        assert chain["agent_os"]["deterministic_server_validation"] is True
        assert chain["safe_action"]["status"] == "WAITING_HUMAN"
        assert chain["safe_action"]["requires_confirmation"] is True
        assert chain["safe_action"]["payment_executed"] is False
        assert chain["provider_confirmation"]["status"] == "NOT_YET_REQUESTED"
        assert chain["provider_confirmation"]["provider_confirmed"] is False
        assert chain["outcome"]["status"] == "NOT_VERIFIED_YET"
        assert chain["longitudinal_memory"]["status"] == "AWAITING_AUTHORITATIVE_OUTCOME"
        assert chain["audit"]["status"] == "RECORDED"
        assert chain["audit"]["raw_prompt_stored"] is False
        assert chain["audit"]["raw_transcript_stored"] is False
        assert chain["audit"]["raw_health_memory_copied"] is False

        audit_row = get_db().execute(
            "SELECT entity_id FROM audit_logs WHERE id=?",
            (chain["audit"]["audit_log_id"],),
        ).fetchone()
        assert audit_row
        assert command not in str(audit_row["entity_id"] or "")

        task = get_db().execute(
            "SELECT metadata_json FROM agent_tasks WHERE id=?",
            (result["workflow_task"]["id"],),
        ).fetchone()
        metadata_text = str(task["metadata_json"] or "")
        metadata = json.loads(metadata_text)
        assert command not in metadata_text
        assert metadata["raw_prompt_stored"] is False
        assert metadata["care_chain"]["raw_prompt_stored"] is False
        assert metadata["care_chain"]["raw_transcript_stored"] is False


def test_local_asr_channel_is_verified_only_by_matching_metadata_audit(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENDOC_LOCAL_AI_ENABLED", "0")
    reset_model_router()
    app = make_app(tmp_path)

    with app.app_context():
        patient = _seed_patient()
        stamp = now_iso()
        cursor = get_db().execute(
            """
            INSERT INTO audit_logs (actor_id,action,entity_type,entity_id,created_at)
            VALUES (?,?,?,?,?)
            """,
            (
                patient["id"],
                "edgecare_asr_transcribe",
                "local_asr",
                "local_openai_compatible_asr:whisper_small:success",
                stamp,
            ),
        )
        audit_id = int(cursor.lastrowid)
        get_db().commit()

        command = "Find a doctor near Kalyani"
        plan = build_plan(patient, command)
        verified = prepare_care_chain(
            patient,
            command,
            intent=plan.intent,
            privacy_class=plan.privacy_class,
            input_channel="local_asr_transcript",
            asr_audit_log_id=audit_id,
        )
        assert verified["input"]["status"] == "VERIFIED_LOCAL_ASR_TRANSCRIPT"
        assert verified["input"]["asr_audit_log_id"] == audit_id
        assert verified["input"]["transcript_persisted_by_chain"] is False
        assert verified["input"]["audio_persisted_by_chain"] is False

        unverified = prepare_care_chain(
            patient,
            command,
            intent=plan.intent,
            privacy_class=plan.privacy_class,
            input_channel="local_asr_transcript",
            asr_audit_log_id=audit_id + 999,
        )
        assert unverified["input"]["status"] == "UNVERIFIED_INPUT_CHANNEL"
        assert unverified["input"]["asr_audit_log_id"] is None
