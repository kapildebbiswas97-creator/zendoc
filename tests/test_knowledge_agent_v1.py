from zendoc.db import get_db
from zendoc.knowledge_agent import run_knowledge_agent
from zendoc.medical_knowledge_documents import register_medical_knowledge_document, review_medical_knowledge_document
from zendoc.medical_rag_ingestion import ingest_approved_medical_text

from tests.test_milestone1 import api_token, make_client
from tests.test_milestone4 import headers


def _seed(app):
    owner = get_db().execute("SELECT * FROM users WHERE email='admin@example.com'").fetchone()
    pending = register_medical_knowledge_document(owner, {
        "source_id": "icmr_guidelines",
        "document_title": "Knowledge Agent Evidence",
        "document_url": "https://www.icmr.gov.in/knowledge-agent-evidence.pdf",
        "publication_date": "2026-09-01",
        "retrieved_at": "2026-09-10T12:00:00+00:00",
        "content_sha256": "5" * 64,
        "usage_basis": "Official artifact reviewed for governed evidence retrieval and Knowledge Agent use.",
        "version": "2026-09-01",
    })
    approved = review_medical_knowledge_document(
        owner,
        pending["document_uid"],
        decision="APPROVED",
        notes="Provenance, permitted use, version and Knowledge Agent evidence scope were reviewed.",
    )
    ingest_approved_medical_text(
        owner,
        document_uid=approved["document_uid"],
        extracted_text="Hypertension blood pressure monitoring clinician follow up lifestyle guidance. " * 50,
        parser_name="pdf_text",
        parser_version="1.0",
        max_words=50,
        overlap_words=10,
    )
    return approved


def test_knowledge_agent_is_read_only_and_evidence_bound(tmp_path):
    app, client = make_client(tmp_path)
    token = api_token(client, "knowledge-agent-patient@example.com")
    with app.app_context():
        approved = _seed(app)
        actor = get_db().execute("SELECT * FROM users WHERE email='knowledge-agent-patient@example.com'").fetchone()
        result = run_knowledge_agent(actor, "hypertension blood pressure", limit=4)
        assert result["status"] == "EVIDENCE_READY"
        assert result["answer"] is None
        assert result["answer_status"] == "EVIDENCE_ONLY"
        assert result["healthcare_action_executed"] is False
        assert result["evidence"]
        assert result["evidence"][0]["document_title"] == approved["document_title"]

    response = client.post(
        "/api/v1/health-knowledge/agent",
        json={"query": "hypertension blood pressure", "limit": 4},
        headers=headers(token),
    )
    assert response.status_code == 200
    assert response.get_json()["status"] == "EVIDENCE_READY"


def test_knowledge_agent_runs_emergency_safety_before_retrieval(tmp_path):
    app, client = make_client(tmp_path)
    token = api_token(client, "knowledge-agent-emergency@example.com")
    with app.app_context():
        actor = get_db().execute("SELECT * FROM users WHERE email='knowledge-agent-emergency@example.com'").fetchone()
        result = run_knowledge_agent(actor, "I have severe chest pain and cannot breathe")
        assert result["status"] == "EMERGENCY_ESCALATION"
        assert result["retrieval_performed"] is False
        assert result["evidence"] == []
        assert result["healthcare_action_executed"] is False

    response = client.post(
        "/api/v1/health-knowledge/agent",
        json={"query": "I have severe chest pain and cannot breathe"},
        headers=headers(token),
    )
    assert response.status_code == 200
    assert response.get_json()["status"] == "EMERGENCY_ESCALATION"


def test_knowledge_agent_returns_no_evidence_instead_of_model_memory(tmp_path):
    app, client = make_client(tmp_path)
    token = api_token(client, "knowledge-agent-empty@example.com")
    with app.app_context():
        actor = get_db().execute("SELECT * FROM users WHERE email='knowledge-agent-empty@example.com'").fetchone()
        result = run_knowledge_agent(actor, "unmatchedzyxwvterm")
        assert result["status"] == "NO_APPROVED_EVIDENCE"
        assert result["answer"] is None
        assert result["evidence"] == []
        assert "will not answer from model memory" in result["message"]


def test_knowledge_agent_requires_authentication_and_valid_bounds(tmp_path):
    app, client = make_client(tmp_path)
    assert client.post("/api/v1/health-knowledge/agent", json={"query": "health"}).status_code == 401

    token = api_token(client, "knowledge-agent-validation@example.com")
    assert client.post(
        "/api/v1/health-knowledge/agent",
        json={"query": "", "limit": 4},
        headers=headers(token),
    ).status_code == 400
    assert client.post(
        "/api/v1/health-knowledge/agent",
        json={"query": "health", "limit": 99},
        headers=headers(token),
    ).status_code == 400
