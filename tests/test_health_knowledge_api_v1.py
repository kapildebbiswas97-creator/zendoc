from zendoc.db import get_db
from zendoc.medical_knowledge_documents import (
    register_medical_knowledge_document,
    review_medical_knowledge_document,
)
from zendoc.medical_rag_ingestion import ingest_approved_medical_text

from tests.test_milestone1 import api_token, make_client
from tests.test_milestone4 import headers


def metadata(*, digest="3" * 64, version="2026-09-01"):
    return {
        "source_id": "icmr_guidelines",
        "document_title": f"API evidence guideline {version}",
        "document_url": f"https://www.icmr.gov.in/api-evidence-{version}.pdf",
        "publication_date": version,
        "retrieved_at": "2026-09-10T12:00:00+00:00",
        "content_sha256": digest,
        "usage_basis": "Official artifact reviewed for provenance and permitted evidence-indexing use.",
        "version": version,
    }


def seed_evidence(app):
    owner = get_db().execute("SELECT * FROM users WHERE email='admin@example.com'").fetchone()
    pending = register_medical_knowledge_document(owner, metadata())
    approved = review_medical_knowledge_document(
        owner,
        pending["document_uid"],
        decision="APPROVED",
        notes="Provenance, usage basis, version and evidence API indexing use were explicitly reviewed.",
    )
    ingest_approved_medical_text(
        owner,
        document_uid=approved["document_uid"],
        extracted_text=(
            "Hypertension blood pressure monitoring lifestyle sodium exercise and clinician follow up. " * 35
            + "The document contains additional contextual public health information. " * 15
        ),
        parser_name="pdf_text",
        parser_version="1.0",
        max_words=50,
        overlap_words=10,
    )
    return owner, approved


def test_health_knowledge_evidence_api_requires_authentication(tmp_path):
    _app, client = make_client(tmp_path)
    response = client.get("/api/v1/health-knowledge/evidence?q=hypertension")
    assert response.status_code == 401


def test_health_knowledge_api_returns_evidence_not_a_medical_answer(tmp_path):
    app, client = make_client(tmp_path)
    patient_token = api_token(client, "knowledge-api-patient@example.com")
    with app.app_context():
        _owner, approved = seed_evidence(app)

    response = client.get(
        "/api/v1/health-knowledge/evidence?q=blood%20pressure%20hypertension&limit=4",
        headers=headers(patient_token),
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "EVIDENCE_FOUND"
    assert payload["answer"] is None
    assert payload["answer_status"] == "EVIDENCE_ONLY"
    assert payload["medical_advice"] is False
    assert payload["retrieval_mode"] == "LEXICAL_ONLY"
    assert payload["evidence"]
    first = payload["evidence"][0]
    assert first["document_title"] == approved["document_title"]
    assert first["document_sha256"] == "3" * 64
    assert first["document_url"].startswith("https://")
    assert len(first["excerpt"]) <= 700


def test_health_knowledge_api_fails_openly_when_no_approved_evidence_matches(tmp_path):
    app, client = make_client(tmp_path)
    patient_token = api_token(client, "knowledge-api-empty@example.com")
    with app.app_context():
        seed_evidence(app)

    response = client.get(
        "/api/v1/health-knowledge/evidence?q=zyxwvunmatchedterm",
        headers=headers(patient_token),
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "NO_APPROVED_EVIDENCE"
    assert payload["answer"] is None
    assert payload["evidence"] == []
    assert "will not answer from model memory" in payload["notice"]


def test_health_knowledge_api_excludes_superseded_evidence(tmp_path):
    app, client = make_client(tmp_path)
    patient_token = api_token(client, "knowledge-api-superseded@example.com")
    with app.app_context():
        owner, old = seed_evidence(app)
        new_pending = register_medical_knowledge_document(owner, metadata(digest="4" * 64, version="2026-09-05"))
        review_medical_knowledge_document(
            owner,
            new_pending["document_uid"],
            decision="APPROVED",
            notes="New version reviewed and approved; old version is no longer retrieval eligible.",
            supersedes_document_uid=old["document_uid"],
        )

    response = client.get(
        "/api/v1/health-knowledge/evidence?q=hypertension",
        headers=headers(patient_token),
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "NO_APPROVED_EVIDENCE"
    assert payload["evidence"] == []


def test_health_knowledge_api_validates_query_and_limit(tmp_path):
    _app, client = make_client(tmp_path)
    patient_token = api_token(client, "knowledge-api-validation@example.com")
    assert client.get("/api/v1/health-knowledge/evidence", headers=headers(patient_token)).status_code == 400
    assert client.get(
        "/api/v1/health-knowledge/evidence?q=health&limit=99",
        headers=headers(patient_token),
    ).status_code == 400
