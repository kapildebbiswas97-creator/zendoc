"""Governed registry for authoritative medical-knowledge sources.

This module approves *publishers/source families for discovery and review*. It does
not claim that website content is licensed for bulk ingestion, downloaded, current,
or clinically validated for a particular patient use. A concrete document must
pass a separate acquisition/usage review before later RAG ingestion.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from urllib.parse import urlparse


SOURCE_STATUS_DISCOVERY_APPROVED = "DISCOVERY_APPROVED"
INGESTION_STATUS_REVIEW_REQUIRED = "REVIEW_REQUIRED"
INGESTION_STATUS_BLOCKED = "BLOCKED"

TRUST_TIER_PRIMARY_AUTHORITY = "PRIMARY_AUTHORITY"


MEDICAL_KNOWLEDGE_SOURCES: dict[str, dict] = {
    "who_guidelines": {
        "source_id": "who_guidelines",
        "publisher": "World Health Organization",
        "canonical_url": "https://www.who.int/publications/who-guidelines",
        "jurisdiction": "global",
        "source_kind": "clinical_public_health_guidelines",
        "trust_tier": TRUST_TIER_PRIMARY_AUTHORITY,
        "source_status": SOURCE_STATUS_DISCOVERY_APPROVED,
        "ingestion_status": INGESTION_STATUS_REVIEW_REQUIRED,
        "allowed_for_discovery": True,
        "allowed_for_answering_without_snapshot": False,
        "requires_document_level_usage_review": True,
        "requires_version_and_publication_date": True,
        "notes": "WHO is an authoritative guideline publisher; each concrete publication still requires provenance, version and usage review before ingestion.",
    },
    "mohfw_guidelines": {
        "source_id": "mohfw_guidelines",
        "publisher": "Ministry of Health and Family Welfare, Government of India",
        "canonical_url": "https://www.mohfw.gov.in/",
        "jurisdiction": "india",
        "source_kind": "national_health_guidance",
        "trust_tier": TRUST_TIER_PRIMARY_AUTHORITY,
        "source_status": SOURCE_STATUS_DISCOVERY_APPROVED,
        "ingestion_status": INGESTION_STATUS_REVIEW_REQUIRED,
        "allowed_for_discovery": True,
        "allowed_for_answering_without_snapshot": False,
        "requires_document_level_usage_review": True,
        "requires_version_and_publication_date": True,
        "notes": "Use only concrete Ministry/DGHS publications whose provenance, date and permitted use have been reviewed.",
    },
    "icmr_guidelines": {
        "source_id": "icmr_guidelines",
        "publisher": "Indian Council of Medical Research",
        "canonical_url": "https://www.icmr.gov.in/guidelines",
        "jurisdiction": "india",
        "source_kind": "research_clinical_ethics_guidelines",
        "trust_tier": TRUST_TIER_PRIMARY_AUTHORITY,
        "source_status": SOURCE_STATUS_DISCOVERY_APPROVED,
        "ingestion_status": INGESTION_STATUS_REVIEW_REQUIRED,
        "allowed_for_discovery": True,
        "allowed_for_answering_without_snapshot": False,
        "requires_document_level_usage_review": True,
        "requires_version_and_publication_date": True,
        "notes": "ICMR publishes multiple guideline classes; document type and applicability must be retained in metadata.",
    },
    "ncdc_technical_guidelines": {
        "source_id": "ncdc_technical_guidelines",
        "publisher": "National Centre for Disease Control, Ministry of Health and Family Welfare",
        "canonical_url": "https://ncdc.mohfw.gov.in/includes/Resource_Library/index.php?tab=Technical+Guidelines",
        "jurisdiction": "india",
        "source_kind": "public_health_technical_guidelines",
        "trust_tier": TRUST_TIER_PRIMARY_AUTHORITY,
        "source_status": SOURCE_STATUS_DISCOVERY_APPROVED,
        "ingestion_status": INGESTION_STATUS_REVIEW_REQUIRED,
        "allowed_for_discovery": True,
        "allowed_for_answering_without_snapshot": False,
        "requires_document_level_usage_review": True,
        "requires_version_and_publication_date": True,
        "notes": "Technical guidance is discoverable, but every retained document needs dated provenance and a usage-basis review.",
    },
    "abdm_policy_standards": {
        "source_id": "abdm_policy_standards",
        "publisher": "National Health Authority / Ayushman Bharat Digital Mission",
        "canonical_url": "https://abdm.gov.in/",
        "jurisdiction": "india",
        "source_kind": "digital_health_policy_interoperability",
        "trust_tier": TRUST_TIER_PRIMARY_AUTHORITY,
        "source_status": SOURCE_STATUS_DISCOVERY_APPROVED,
        "ingestion_status": INGESTION_STATUS_REVIEW_REQUIRED,
        "allowed_for_discovery": True,
        "allowed_for_answering_without_snapshot": False,
        "requires_document_level_usage_review": True,
        "requires_version_and_publication_date": True,
        "notes": "Registry inclusion is architecture preparation only and does not mean ZENDOC is officially integrated with ABDM.",
    },
}


_REQUIRED_DOCUMENT_FIELDS = (
    "source_id",
    "document_title",
    "document_url",
    "publication_date",
    "retrieved_at",
    "content_sha256",
    "usage_basis",
    "version",
)


def list_medical_knowledge_sources() -> list[dict]:
    """Return a stable copy of source-family governance metadata."""
    return [deepcopy(MEDICAL_KNOWLEDGE_SOURCES[key]) for key in sorted(MEDICAL_KNOWLEDGE_SOURCES)]


def get_medical_knowledge_source(source_id: str) -> dict | None:
    key = str(source_id or "").strip().lower()
    source = MEDICAL_KNOWLEDGE_SOURCES.get(key)
    return deepcopy(source) if source else None


def _valid_https_url(value: str) -> bool:
    try:
        parsed = urlparse(str(value or "").strip())
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.netloc)


def _valid_sha256(value: str) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def _parse_date(value: str, field_name: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required.")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} must be an ISO date or date-time.") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def validate_medical_knowledge_document(metadata: dict) -> dict:
    """Validate governance metadata before a future ingestion pipeline may use it.

    Passing this validator means the handoff is structurally reviewable. It does
    *not* mean the medical content is clinically endorsed, licensed for all uses,
    or already present in a RAG index.
    """
    if not isinstance(metadata, dict):
        raise ValueError("Document metadata must be an object.")

    missing = [field for field in _REQUIRED_DOCUMENT_FIELDS if not str(metadata.get(field) or "").strip()]
    if missing:
        raise ValueError(f"Missing medical-knowledge metadata: {', '.join(missing)}")

    source = get_medical_knowledge_source(metadata["source_id"])
    if not source or source["source_status"] != SOURCE_STATUS_DISCOVERY_APPROVED:
        raise ValueError("Medical-knowledge source is not approved for discovery/review.")
    if source["ingestion_status"] == INGESTION_STATUS_BLOCKED:
        raise ValueError("Medical-knowledge source is blocked from ingestion.")

    if not _valid_https_url(metadata["document_url"]):
        raise ValueError("document_url must use HTTPS.")
    if not _valid_sha256(metadata["content_sha256"]):
        raise ValueError("content_sha256 must be a 64-character hexadecimal SHA-256 digest.")

    published = _parse_date(metadata["publication_date"], "publication_date")
    retrieved = _parse_date(metadata["retrieved_at"], "retrieved_at")
    now = datetime.now(timezone.utc)
    if published > now:
        raise ValueError("publication_date cannot be in the future.")
    if retrieved > now:
        raise ValueError("retrieved_at cannot be in the future.")
    if retrieved < published:
        raise ValueError("retrieved_at cannot predate publication_date.")

    usage_basis = str(metadata["usage_basis"]).strip()
    if len(usage_basis) < 8:
        raise ValueError("usage_basis must record a meaningful licence/terms/public-use basis.")

    return {
        "status": "REVIEWABLE",
        "source": source,
        "document": {
            "source_id": source["source_id"],
            "document_title": str(metadata["document_title"]).strip(),
            "document_url": str(metadata["document_url"]).strip(),
            "publication_date": published.date().isoformat(),
            "retrieved_at": retrieved.isoformat(timespec="seconds"),
            "content_sha256": str(metadata["content_sha256"]).strip().lower(),
            "usage_basis": usage_basis,
            "version": str(metadata["version"]).strip(),
        },
        "ingestion_allowed": False,
        "next_gate": "DOCUMENT_USAGE_AND_CONTENT_REVIEW",
        "notice": "Structural validation only. Do not index or answer from this document until a separate approval records permitted use, provenance and content review.",
    }
