import pytest

from zendoc.db import get_db
from zendoc.medical_hybrid_retrieval import (
    hybrid_medical_retrieval,
    lexical_medical_retrieval,
    pgvector_capability,
    store_medical_chunk_embedding,
)
from zendoc.medical_knowledge_documents import (
    register_medical_knowledge_document,
    review_medical_knowledge_document,
)
from zendoc.medical_rag_ingestion import ingest_approved_medical_text

from tests.test_milestone1 import make_client


def metadata(*, digest="1" * 64, version="2026-09-01"):
    return {
        "source_id": "icmr_guidelines",
        "document_title": f"Evidence guideline {version}",
        "document_url": f"https://www.icmr.gov.in/evidence-{version}.pdf",
        "publication_date": version,
        "retrieved_at": "2026-09-10T12:00:00+00:00",
        "content_sha256": digest,
        "usage_basis": "Official artifact reviewed for provenance and permitted medical-knowledge indexing use.",
        "version": version,
    }


def approved_ingestion(app):
    owner = get_db().execute("SELECT * FROM users WHERE email='admin@example.com'").fetchone()
    pending = register_medical_knowledge_document(owner, metadata())
    approved = review_medical_knowledge_document(
        owner,
        pending["document_uid"],
        decision="APPROVED",
        notes="Document provenance, usage basis, version and intended indexing scope were reviewed.",
    )
    ingestion = ingest_approved_medical_text(
        owner,
        document_uid=approved["document_uid"],
        extracted_text=(
            "Hypertension blood pressure monitoring lifestyle sodium exercise clinician follow up. " * 30
            + "Diabetes glucose monitoring appears in a separate contextual section. " * 20
        ),
        parser_name="pdf_text",
        parser_version="1.0",
        max_words=50,
        overlap_words=10,
    )
    return owner, approved, ingestion


def test_sqlite_truthfully_reports_pgvector_unavailable(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        capability = pgvector_capability()
        assert capability["available"] is False
        assert capability["status"] == "INTEGRATION_REQUIRED"
        assert capability["reason"] == "PGVECTOR_REQUIRES_POSTGRESQL"


def test_lexical_retrieval_returns_only_approved_evidence_with_provenance(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        _owner, approved, _ingestion = approved_ingestion(app)
        results = lexical_medical_retrieval("blood pressure hypertension", limit=5)
        assert results
        top = results[0]
        assert top["document_uid"] == approved["document_uid"]
        assert top["lexical_score"] > 0
        assert top["evidence"]["source_id"] == "icmr_guidelines"
        assert top["evidence"]["content_sha256"] == "1" * 64
        assert top["evidence"]["document_url"].startswith("https://")


def test_hybrid_retrieval_degrades_explicitly_to_lexical_on_sqlite(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        approved_ingestion(app)
        response = hybrid_medical_retrieval("blood pressure monitoring", limit=4)
        assert response["mode"] == "LEXICAL_ONLY"
        assert response["pgvector"]["available"] is False
        assert response["grounding_required"] is True
        assert response["results"]
        assert all(item["hybrid_score"] == item["lexical_score"] for item in response["results"])


def test_embedding_storage_fails_closed_when_pgvector_is_unavailable(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        owner, approved, _ingestion = approved_ingestion(app)
        chunk = lexical_medical_retrieval("hypertension", limit=1)[0]
        with pytest.raises(RuntimeError, match="PGVECTOR_INTEGRATION_REQUIRED"):
            store_medical_chunk_embedding(
                owner,
                chunk_uid=chunk["chunk_uid"],
                embedding_model="test-embedding",
                embedding=[0.1] * 16,
            )


def test_superseded_document_disappears_from_retrieval(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        owner, old, _ingestion = approved_ingestion(app)
        assert lexical_medical_retrieval("hypertension", limit=5)

        new_pending = register_medical_knowledge_document(owner, metadata(digest="2" * 64, version="2026-09-05"))
        review_medical_knowledge_document(
            owner,
            new_pending["document_uid"],
            decision="APPROVED",
            notes="Newer reviewed artifact supersedes the older guideline version for retrieval eligibility.",
            supersedes_document_uid=old["document_uid"],
        )
        assert lexical_medical_retrieval("hypertension", limit=5) == []


def test_query_and_limit_validation(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        with pytest.raises(ValueError, match="non-empty"):
            lexical_medical_retrieval("!!!")
        with pytest.raises(ValueError, match="between 1 and 25"):
            lexical_medical_retrieval("health", limit=0)
