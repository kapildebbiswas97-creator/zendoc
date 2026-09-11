import pytest

from zendoc.db import get_db
from zendoc.medical_knowledge_documents import (
    register_medical_knowledge_document,
    review_medical_knowledge_document,
)
from zendoc.medical_rag_ingestion import (
    chunk_medical_text,
    ingest_approved_medical_text,
    list_medical_knowledge_chunks,
    normalize_extracted_text,
)

from tests.test_milestone1 import make_client, register_web


def metadata(*, digest="e" * 64, version="2026-09-01", publication_date="2026-09-01"):
    return {
        "source_id": "icmr_guidelines",
        "document_title": f"Guideline {version}",
        "document_url": f"https://www.icmr.gov.in/guideline-{version}.pdf",
        "publication_date": publication_date,
        "retrieved_at": "2026-09-10T12:00:00+00:00",
        "content_sha256": digest,
        "usage_basis": "Official artifact with document-level provenance and permitted-use review recorded by the owner.",
        "version": version,
    }


def approve_document(owner, **overrides):
    registered = register_medical_knowledge_document(owner, metadata(**overrides))
    return review_medical_knowledge_document(
        owner,
        registered["document_uid"],
        decision="APPROVED",
        notes="Provenance, terms, version and intended medical-knowledge indexing use were explicitly reviewed.",
    )


def test_normalization_and_chunking_are_deterministic():
    normalized = normalize_extracted_text(" First   paragraph. \n\n Second\nparagraph. ")
    assert normalized == "First paragraph.\n\nSecond paragraph."
    text = " ".join(f"word{i}" for i in range(105))
    chunks = chunk_medical_text(text, max_words=50, overlap_words=10)
    assert len(chunks) == 3
    assert chunks[0].split()[-10:] == chunks[1].split()[:10]
    assert chunks[1].split()[-10:] == chunks[2].split()[:10]


def test_only_approved_document_can_enter_rag_ingestion(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        owner = get_db().execute("SELECT * FROM users WHERE email='admin@example.com'").fetchone()
        pending = register_medical_knowledge_document(owner, metadata())
        with pytest.raises(PermissionError, match="not approved"):
            ingest_approved_medical_text(
                owner,
                document_uid=pending["document_uid"],
                extracted_text="medical guidance text " * 60,
                parser_name="pdf_text",
                parser_version="1",
            )


def test_approved_ingestion_persists_provenance_bound_chunks(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        owner = get_db().execute("SELECT * FROM users WHERE email='admin@example.com'").fetchone()
        approved = approve_document(owner)
        text = " ".join(f"clinicalword{i}" for i in range(105))
        ingestion = ingest_approved_medical_text(
            owner,
            document_uid=approved["document_uid"],
            extracted_text=text,
            parser_name="pdf_text",
            parser_version="1.0",
            max_words=50,
            overlap_words=10,
        )
        assert ingestion["chunk_count"] == 3
        assert ingestion["document_uid"] == approved["document_uid"]
        chunks = list_medical_knowledge_chunks(approved["document_uid"])
        assert len(chunks) == 3
        assert [item["ordinal"] for item in chunks] == [0, 1, 2]
        for chunk in chunks:
            assert chunk["metadata"]["document_uid"] == approved["document_uid"]
            assert chunk["metadata"]["content_sha256"] == "e" * 64
            assert chunk["metadata"]["parser_name"] == "pdf_text"
            assert chunk["chunk_sha256"]


def test_same_extraction_is_idempotent(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        owner = get_db().execute("SELECT * FROM users WHERE email='admin@example.com'").fetchone()
        approved = approve_document(owner)
        kwargs = dict(
            document_uid=approved["document_uid"],
            extracted_text="repeatable extracted medical guidance " * 80,
            parser_name="pdf_text",
            parser_version="1.0",
            max_words=50,
            overlap_words=10,
        )
        first = ingest_approved_medical_text(owner, **kwargs)
        second = ingest_approved_medical_text(owner, **kwargs)
        assert second["ingestion_uid"] == first["ingestion_uid"]
        count = get_db().execute("SELECT COUNT(*) AS n FROM medical_knowledge_ingestions").fetchone()["n"]
        assert count == 1


def test_non_owner_cannot_ingest_approved_medical_text(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "patient", "rag-attacker@example.com")
    with app.app_context():
        owner = get_db().execute("SELECT * FROM users WHERE email='admin@example.com'").fetchone()
        patient = get_db().execute("SELECT * FROM users WHERE email='rag-attacker@example.com'").fetchone()
        approved = approve_document(owner)
        with pytest.raises(PermissionError):
            ingest_approved_medical_text(
                patient,
                document_uid=approved["document_uid"],
                extracted_text="unauthorized ingestion attempt " * 80,
                parser_name="pdf_text",
                parser_version="1.0",
            )


def test_superseded_document_chunks_fail_closed(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        owner = get_db().execute("SELECT * FROM users WHERE email='admin@example.com'").fetchone()
        old = approve_document(owner)
        ingest_approved_medical_text(
            owner,
            document_uid=old["document_uid"],
            extracted_text="old approved guidance text " * 80,
            parser_name="pdf_text",
            parser_version="1.0",
        )
        new_pending = register_medical_knowledge_document(
            owner,
            metadata(digest="f" * 64, version="2026-09-05", publication_date="2026-09-05"),
        )
        review_medical_knowledge_document(
            owner,
            new_pending["document_uid"],
            decision="APPROVED",
            notes="New version reviewed and approved; old version must be removed from retrieval eligibility.",
            supersedes_document_uid=old["document_uid"],
        )
        with pytest.raises(PermissionError, match="not approved"):
            list_medical_knowledge_chunks(old["document_uid"])


def test_chunk_bounds_are_enforced():
    with pytest.raises(ValueError, match="between 40 and 1000"):
        chunk_medical_text("some words", max_words=10, overlap_words=0)
    with pytest.raises(ValueError, match="smaller than max_words"):
        chunk_medical_text("some words", max_words=50, overlap_words=50)
