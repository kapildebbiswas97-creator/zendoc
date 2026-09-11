"""Read-only, evidence-bound Knowledge Agent foundation.

This agent never performs healthcare actions. It runs deterministic emergency
screening first, then retrieves only currently APPROVED medical-knowledge chunks.
It returns an evidence bundle for a later separately-reviewed explanation layer.
"""
from __future__ import annotations

from typing import Any

from .medical_hybrid_retrieval import hybrid_medical_retrieval
from .safety import SafetyEngine


MAX_QUERY_CHARS = 500
MAX_EVIDENCE_ITEMS = 8
MAX_EXCERPT_CHARS = 700


def _actor_value(actor: Any, key: str, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    if isinstance(actor, dict):
        return actor.get(key, default)
    return getattr(actor, key, default)


def _bounded_excerpt(text: str) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= MAX_EXCERPT_CHARS:
        return clean
    return clean[: MAX_EXCERPT_CHARS - 1].rstrip() + "…"


def run_knowledge_agent(actor: Any, query: str, *, limit: int = 6) -> dict:
    """Retrieve governed evidence without diagnosis or autonomous action."""
    actor_id = int(_actor_value(actor, "id", 0) or 0)
    role = str(_actor_value(actor, "role", "") or "").strip()
    if not actor_id or not role:
        raise PermissionError("Authentication is required to use the Knowledge Agent.")

    query = str(query or "").strip()
    if not query:
        raise ValueError("Knowledge query is required.")
    if len(query) > MAX_QUERY_CHARS:
        raise ValueError(f"Knowledge query must be at most {MAX_QUERY_CHARS} characters.")
    try:
        limit = int(limit)
    except (TypeError, ValueError) as error:
        raise ValueError("limit must be an integer.") from error
    if limit < 1 or limit > MAX_EVIDENCE_ITEMS:
        raise ValueError(f"limit must be between 1 and {MAX_EVIDENCE_ITEMS}.")

    safety = SafetyEngine().assess(query)
    if safety.get("emergency"):
        return {
            "agent": "KnowledgeAgent",
            "status": "EMERGENCY_ESCALATION",
            "answer": None,
            "evidence": [],
            "urgency": "emergency",
            "message": safety.get("guidance") or "Seek urgent emergency care now.",
            "reason": safety.get("reason"),
            "healthcare_action_executed": False,
            "retrieval_performed": False,
        }

    retrieval = hybrid_medical_retrieval(query, limit=limit)
    evidence = []
    for rank, item in enumerate(retrieval.get("results", []), start=1):
        source = item["evidence"]
        evidence.append(
            {
                "evidence_id": item["chunk_uid"],
                "rank": rank,
                "excerpt": _bounded_excerpt(item["text"]),
                "retrieval_score": item["hybrid_score"],
                "source_id": source["source_id"],
                "document_title": source["document_title"],
                "document_url": source["document_url"],
                "publication_date": source["publication_date"],
                "version": source["version"],
                "document_sha256": source["content_sha256"],
                "chunk_sha256": source["chunk_sha256"],
            }
        )

    if not evidence:
        return {
            "agent": "KnowledgeAgent",
            "status": "NO_APPROVED_EVIDENCE",
            "answer": None,
            "evidence": [],
            "urgency": "routine",
            "retrieval_mode": retrieval["mode"],
            "pgvector": retrieval["pgvector"],
            "healthcare_action_executed": False,
            "retrieval_performed": True,
            "message": (
                "No approved indexed medical evidence matched this request. "
                "The Knowledge Agent will not answer from model memory as though retrieval succeeded."
            ),
        }

    return {
        "agent": "KnowledgeAgent",
        "status": "EVIDENCE_READY",
        "answer": None,
        "answer_status": "EVIDENCE_ONLY",
        "evidence": evidence,
        "urgency": "routine",
        "retrieval_mode": retrieval["mode"],
        "pgvector": retrieval["pgvector"],
        "healthcare_action_executed": False,
        "retrieval_performed": True,
        "requester_role": role,
        "message": (
            "Approved evidence is ready for a separately safety-reviewed explanation layer. "
            "No diagnosis, prescription, booking, order, or other healthcare action was executed."
        ),
    }
