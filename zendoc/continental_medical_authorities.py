"""Additional authoritative medical-knowledge source families.

These are discovery/review allow-list entries only. They never permit direct
live-web answering. Concrete documents still pass the existing snapshot,
provenance, date/version, SHA-256, usage and owner-approval gates.
"""
from __future__ import annotations

from copy import deepcopy


AUTHORITY_SOURCES = {
    "jp_mhlw_guidance": {
        "source_id": "jp_mhlw_guidance",
        "publisher": "Ministry of Health, Labour and Welfare, Japan",
        "canonical_url": "https://www.mhlw.go.jp/",
        "jurisdiction": "japan",
        "source_kind": "national_health_guidance",
    },
    "fr_has_guidance": {
        "source_id": "fr_has_guidance",
        "publisher": "Haute Autorite de Sante, France",
        "canonical_url": "https://www.has-sante.fr/",
        "jurisdiction": "france",
        "source_kind": "national_clinical_guidance",
    },
    "br_moh_guidance": {
        "source_id": "br_moh_guidance",
        "publisher": "Ministry of Health, Brazil",
        "canonical_url": "https://www.gov.br/saude/",
        "jurisdiction": "brazil",
        "source_kind": "national_health_guidance",
    },
    "au_health_guidance": {
        "source_id": "au_health_guidance",
        "publisher": "Australian Government Department of Health, Disability and Ageing",
        "canonical_url": "https://www.health.gov.au/",
        "jurisdiction": "australia",
        "source_kind": "national_health_guidance",
    },
    "nz_health_guidance": {
        "source_id": "nz_health_guidance",
        "publisher": "New Zealand Ministry of Health",
        "canonical_url": "https://www.health.govt.nz/",
        "jurisdiction": "new_zealand",
        "source_kind": "national_health_guidance",
    },
    "il_moh_guidance": {
        "source_id": "il_moh_guidance",
        "publisher": "Ministry of Health, Israel",
        "canonical_url": "https://www.gov.il/en/departments/ministry_of_health/",
        "jurisdiction": "israel",
        "source_kind": "national_health_guidance",
    },
    "ir_mohme_guidance": {
        "source_id": "ir_mohme_guidance",
        "publisher": "Ministry of Health and Medical Education, Iran",
        "canonical_url": "https://behdasht.gov.ir/",
        "jurisdiction": "iran",
        "source_kind": "national_health_guidance",
    },
    "za_ndoh_guidance": {
        "source_id": "za_ndoh_guidance",
        "publisher": "National Department of Health, South Africa",
        "canonical_url": "https://www.health.gov.za/",
        "jurisdiction": "south_africa",
        "source_kind": "national_health_guidance",
    },
}


def install_continental_medical_authorities(target: dict[str, dict]) -> None:
    common = {
        "trust_tier": "PRIMARY_AUTHORITY",
        "source_status": "DISCOVERY_APPROVED",
        "ingestion_status": "REVIEW_REQUIRED",
        "allowed_for_discovery": True,
        "allowed_for_answering_without_snapshot": False,
        "requires_document_level_usage_review": True,
        "requires_version_and_publication_date": True,
        "notes": "Authority allow-list only. Each concrete document requires immutable provenance and explicit review before RAG ingestion.",
    }
    for source_id, source in AUTHORITY_SOURCES.items():
        item = deepcopy(common)
        item.update(deepcopy(source))
        target[source_id] = item
