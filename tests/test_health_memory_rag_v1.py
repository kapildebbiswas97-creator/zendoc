import pytest

from tests.test_milestone1 import make_app
from zendoc.agent_executor import execute_plan
from zendoc.agent_planner import build_plan
from zendoc.db import get_db, now_iso
from zendoc.health_memory_rag import search_health_memory_evidence
from zendoc.health_timeline import add_timeline_event
from zendoc.specialist_orchestrator import orchestrate_specialist


def _seed_patient():
    db = get_db()
    stamp = now_iso()
    patient_id = db.execute(
        """
        INSERT INTO users
        (name,email,email_normalized,password_hash,role,active,city,created_at,updated_at)
        VALUES ('Memory Patient','memory-rag@example.test','memory-rag@example.test',
                'unused','patient',1,'Kalyani',?,?)
        """,
        (stamp, stamp),
    ).lastrowid
    db.commit()
    return dict(db.execute("SELECT * FROM users WHERE id=?", (patient_id,)).fetchone())


def test_health_memory_rag_returns_only_matching_provenance_evidence(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        patient = _seed_patient()
        provider_event_id = add_timeline_event(
            patient["id"],
            "provider_outcome",
            "Cardiology visit completed",
            summary="Connected appointment was recorded as completed by the provider workflow.",
            provider_name="Dr Evidence",
            source="PROVIDER_RECORDED",
            source_ref="care_outcome:501",
            created_by=patient["id"],
        )
        add_timeline_event(
            patient["id"],
            "medical_record",
            "Patient note",
            summary="User wrote a general headache note.",
            source="USER_REPORTED",
            created_by=patient["id"],
        )

        db = get_db()
        db.execute(
            """
            INSERT INTO ai_interactions
            (user_id,feature,intent,input_text,output_text,risk_level,model_version,
             provider,emergency,success,latency_ms,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                patient["id"],
                "zendoc_ai",
                "health_records",
                "cardiology generated chat text",
                "cardiology generated response",
                "routine",
                "test",
                "test",
                0,
                1,
                1,
                now_iso(),
            ),
        )
        db.commit()

        result = search_health_memory_evidence(patient, "cardiology", limit=5)

        assert result["status"] == "OK"
        assert result["model_called"] is False
        assert result["retrieval_mode"] == "authorized_lexical_health_memory_rag"
        assert result["excluded_ai_interaction_count"] == 1
        assert result["match_count"] == 1
        assert result["matches"][0]["evidence_id"] == f"PROVIDER_RECORDED:{provider_event_id}"
        assert result["matches"][0]["provenance"] == "PROVIDER_RECORDED"
        assert "generated chat" not in " ".join(result["context_lines"]).lower()
        assert "does not diagnose" in result["truth_notice"].lower()


def test_health_memory_rag_returns_no_unrelated_fallback_evidence(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        patient = _seed_patient()
        add_timeline_event(
            patient["id"],
            "medical_record",
            "Blood pressure note",
            summary="Stored measurement discussion.",
            source="USER_REPORTED",
            created_by=patient["id"],
        )

        result = search_health_memory_evidence(patient, "oncology chemotherapy", limit=5)

        assert result["status"] == "NO_MATCHES"
        assert result["matches"] == []
        assert result["context_lines"] == []


def test_health_memory_rag_blocks_cross_patient_access_without_consent(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        patient = _seed_patient()
        db = get_db()
        stamp = now_iso()
        other_id = db.execute(
            """
            INSERT INTO users
            (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
            VALUES ('Other Patient','other-memory@example.test','other-memory@example.test',
                    'unused','patient',1,?,?)
            """,
            (stamp, stamp),
        ).lastrowid
        db.commit()
        other = dict(db.execute("SELECT * FROM users WHERE id=?", (other_id,)).fetchone())

        with pytest.raises(PermissionError):
            search_health_memory_evidence(other, "cardiology", patient_id=patient["id"])


def test_agent_os_health_memory_plan_includes_retrieval_and_executes_it(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        patient = _seed_patient()
        add_timeline_event(
            patient["id"],
            "provider_outcome",
            "Cardiology follow-up evidence",
            summary="Provider-recorded operational outcome.",
            source="PROVIDER_RECORDED",
            created_by=patient["id"],
        )

        plan = build_plan(patient, "Search my health memory for cardiology")
        assert plan.assigned_agent == "HealthMemoryAgent"
        assert [step.tool_name for step in plan.steps] == [
            "get_health_memory_context",
            "search_health_memory_evidence",
        ]

        result = execute_plan(plan, patient)
        assert result["status"] == "completed"
        retrieval = result["tool_results"][1]["output"]
        assert retrieval["status"] == "OK"
        assert retrieval["matches"][0]["provenance"] == "PROVIDER_RECORDED"


def test_specialist_orchestrator_preserves_health_memory_retrieval_payload(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        patient = _seed_patient()
        add_timeline_event(
            patient["id"],
            "provider_outcome",
            "Cardiology continuity evidence",
            summary="Provider-recorded completion evidence for the connected visit.",
            source="PROVIDER_RECORDED",
            created_by=patient["id"],
        )

        result = orchestrate_specialist(patient, "Search my health memory for cardiology")

        assert result["intent"] == "health_records"
        assert result["assigned_agent"] == "HealthMemoryAgent"
        assert result["payload"]["health_memory"]["status"] == "OK"
        retrieval = result["payload"]["retrieval"]
        assert retrieval["status"] == "OK"
        assert retrieval["model_called"] is False
        assert retrieval["matches"][0]["provenance"] == "PROVIDER_RECORDED"
        assert result["actions"][0]["type"] == "health_memory_evidence"
        assert "prior AI chat is excluded" in result["message"]
