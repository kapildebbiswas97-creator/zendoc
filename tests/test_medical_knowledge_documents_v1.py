import pytest

from zendoc.db import get_db
from zendoc.medical_knowledge_documents import (
    get_approved_medical_knowledge_document,
    list_medical_knowledge_documents,
    register_medical_knowledge_document,
    review_medical_knowledge_document,
)

from tests.test_milestone1 import make_client, register_web


def metadata(*, digest="b" * 64, version="2026-09-01", publication_date="2026-09-01"):
    return {
        "source_id": "icmr_guidelines",
        "document_title": f"Reviewed guideline {version}",
        "document_url": f"https://www.icmr.gov.in/example-{version}.pdf",
        "publication_date": publication_date,
        "retrieved_at": "2026-09-10T12:00:00+00:00",
        "content_sha256": digest,
        "usage_basis": "Official public document; owner reviewed the permitted-use basis for ZENDOC indexing.",
        "version": version,
    }


def owner_row(app):
    with app.app_context():
        return get_db().execute("SELECT * FROM users WHERE email='admin@example.com'").fetchone()


def test_document_must_be_explicitly_approved_before_handoff(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        owner = get_db().execute("SELECT * FROM users WHERE email='admin@example.com'").fetchone()
        registered = register_medical_knowledge_document(owner, metadata())
        assert registered["review_status"] == "PENDING"

        with pytest.raises(PermissionError, match="not approved"):
            get_approved_medical_knowledge_document(registered["document_uid"])

        approved = review_medical_knowledge_document(
            owner,
            registered["document_uid"],
            decision="APPROVED",
            notes="Terms, provenance, document identity and intended RAG use were reviewed by the owner.",
        )
        assert approved["review_status"] == "APPROVED"
        handoff = get_approved_medical_knowledge_document(registered["document_uid"])
        assert handoff["content_sha256"] == "b" * 64


def test_registration_is_idempotent_for_same_immutable_artifact(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        owner = get_db().execute("SELECT * FROM users WHERE email='admin@example.com'").fetchone()
        first = register_medical_knowledge_document(owner, metadata())
        second = register_medical_knowledge_document(owner, metadata())
        assert second["document_uid"] == first["document_uid"]
        assert len(list_medical_knowledge_documents()) == 1


def test_non_owner_cannot_register_or_review_medical_knowledge(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "patient", "knowledge-attacker@example.com")
    with app.app_context():
        owner = get_db().execute("SELECT * FROM users WHERE email='admin@example.com'").fetchone()
        patient = get_db().execute("SELECT * FROM users WHERE email='knowledge-attacker@example.com'").fetchone()
        registered = register_medical_knowledge_document(owner, metadata())

        with pytest.raises(PermissionError):
            register_medical_knowledge_document(patient, metadata(digest="c" * 64, version="2026-09-02"))
        with pytest.raises(PermissionError):
            review_medical_knowledge_document(
                patient,
                registered["document_uid"],
                decision="APPROVED",
                notes="Unauthorized user must never be able to approve this artifact.",
            )


def test_reviewed_document_is_immutable(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        owner = get_db().execute("SELECT * FROM users WHERE email='admin@example.com'").fetchone()
        registered = register_medical_knowledge_document(owner, metadata())
        review_medical_knowledge_document(
            owner,
            registered["document_uid"],
            decision="REJECTED",
            notes="Usage basis was insufficient for medical-knowledge indexing.",
        )
        with pytest.raises(ValueError, match="immutable"):
            review_medical_knowledge_document(
                owner,
                registered["document_uid"],
                decision="APPROVED",
                notes="Attempting to reverse the immutable review decision must fail.",
            )


def test_new_approved_version_can_supersede_only_approved_same_source_document(tmp_path):
    app, _client = make_client(tmp_path)
    with app.app_context():
        owner = get_db().execute("SELECT * FROM users WHERE email='admin@example.com'").fetchone()
        old = register_medical_knowledge_document(owner, metadata())
        review_medical_knowledge_document(
            owner,
            old["document_uid"],
            decision="APPROVED",
            notes="Initial version reviewed and approved for the governed ingestion handoff.",
        )

        new = register_medical_knowledge_document(
            owner,
            metadata(digest="d" * 64, version="2026-09-05", publication_date="2026-09-05"),
        )
        reviewed = review_medical_knowledge_document(
            owner,
            new["document_uid"],
            decision="APPROVED",
            notes="Newer version reviewed; it supersedes the previously approved artifact.",
            supersedes_document_uid=old["document_uid"],
        )
        assert reviewed["review_status"] == "APPROVED"
        assert reviewed["supersedes_document_uid"] == old["document_uid"]
        statuses = {item["document_uid"]: item["review_status"] for item in list_medical_knowledge_documents()}
        assert statuses[old["document_uid"]] == "SUPERSEDED"
        assert statuses[new["document_uid"]] == "APPROVED"
        with pytest.raises(PermissionError, match="not approved"):
            get_approved_medical_knowledge_document(old["document_uid"])
