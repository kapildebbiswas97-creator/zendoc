import pytest

from zendoc.medical_knowledge_registry import (
    get_medical_knowledge_source,
    list_medical_knowledge_sources,
    validate_medical_knowledge_document,
)


def valid_document(**overrides):
    metadata = {
        "source_id": "icmr_guidelines",
        "document_title": "Example reviewed guideline",
        "document_url": "https://www.icmr.gov.in/example-guideline.pdf",
        "publication_date": "2026-09-01",
        "retrieved_at": "2026-09-10T12:00:00+00:00",
        "content_sha256": "a" * 64,
        "usage_basis": "Publicly accessible official document; usage terms require human review before indexing.",
        "version": "2026-09-01",
    }
    metadata.update(overrides)
    return metadata


def test_registry_contains_only_truthful_non_ingested_source_families():
    sources = list_medical_knowledge_sources()
    assert sources
    assert {item["source_id"] for item in sources} >= {
        "who_guidelines",
        "mohfw_guidelines",
        "icmr_guidelines",
        "ncdc_technical_guidelines",
        "abdm_policy_standards",
    }
    for source in sources:
        assert source["source_status"] == "DISCOVERY_APPROVED"
        assert source["ingestion_status"] == "REVIEW_REQUIRED"
        assert source["allowed_for_discovery"] is True
        assert source["allowed_for_answering_without_snapshot"] is False
        assert source["requires_document_level_usage_review"] is True
        assert source["canonical_url"].startswith("https://")


def test_registry_returns_defensive_copies():
    source = get_medical_knowledge_source("who_guidelines")
    source["publisher"] = "tampered"
    fresh = get_medical_knowledge_source("who_guidelines")
    assert fresh["publisher"] == "World Health Organization"


def test_document_metadata_validation_stays_review_only():
    result = validate_medical_knowledge_document(valid_document())
    assert result["status"] == "REVIEWABLE"
    assert result["ingestion_allowed"] is False
    assert result["next_gate"] == "DOCUMENT_USAGE_AND_CONTENT_REVIEW"
    assert result["document"]["content_sha256"] == "a" * 64


def test_unknown_source_is_rejected():
    with pytest.raises(ValueError, match="not approved"):
        validate_medical_knowledge_document(valid_document(source_id="random_blog"))


def test_insecure_url_and_bad_digest_are_rejected():
    with pytest.raises(ValueError, match="HTTPS"):
        validate_medical_knowledge_document(valid_document(document_url="http://example.com/guideline.pdf"))
    with pytest.raises(ValueError, match="SHA-256"):
        validate_medical_knowledge_document(valid_document(content_sha256="not-a-digest"))


def test_missing_usage_basis_and_future_dates_are_rejected():
    with pytest.raises(ValueError, match="usage_basis"):
        validate_medical_knowledge_document(valid_document(usage_basis=""))
    with pytest.raises(ValueError, match="future"):
        validate_medical_knowledge_document(valid_document(publication_date="2999-01-01"))


def test_retrieval_cannot_predate_publication():
    with pytest.raises(ValueError, match="predate"):
        validate_medical_knowledge_document(
            valid_document(publication_date="2026-09-10", retrieved_at="2026-09-01T00:00:00+00:00")
        )
