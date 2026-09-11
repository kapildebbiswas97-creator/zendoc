"""Authenticated evidence API for governed medical knowledge.

The v1 endpoint retrieves evidence only. It intentionally does not synthesize a
clinical answer. A later reasoning model may consume this evidence through a
separate safety-reviewed layer, but retrieval failure must remain visible.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .medical_hybrid_retrieval import hybrid_medical_retrieval
from .routes import require_api_user


bp = Blueprint("medical_knowledge", __name__)
MAX_EXCERPT_CHARS = 700


def _bounded_excerpt(text: str) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= MAX_EXCERPT_CHARS:
        return clean
    return clean[: MAX_EXCERPT_CHARS - 1].rstrip() + "…"


@bp.get("/api/v1/health-knowledge/evidence")
def api_health_knowledge_evidence():
    user, error = require_api_user()
    if error:
        return error

    query = str(request.args.get("q") or "").strip()
    if not query:
        return jsonify({"error": {"code": 400, "message": "q is required"}}), 400
    if len(query) > 500:
        return jsonify({"error": {"code": 400, "message": "q must be at most 500 characters"}}), 400
    try:
        limit = int(request.args.get("limit", 6))
    except (TypeError, ValueError):
        return jsonify({"error": {"code": 400, "message": "limit must be an integer"}}), 400
    if limit < 1 or limit > 10:
        return jsonify({"error": {"code": 400, "message": "limit must be between 1 and 10"}}), 400

    try:
        retrieval = hybrid_medical_retrieval(query, limit=limit)
    except ValueError as service_error:
        return jsonify({"error": {"code": 400, "message": str(service_error)}}), 400

    evidence = []
    for rank, item in enumerate(retrieval["results"], start=1):
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

    found = bool(evidence)
    return jsonify(
        {
            "status": "EVIDENCE_FOUND" if found else "NO_APPROVED_EVIDENCE",
            "query": query,
            "answer": None,
            "answer_status": "EVIDENCE_ONLY",
            "medical_advice": False,
            "retrieval_mode": retrieval["mode"],
            "pgvector": retrieval["pgvector"],
            "evidence": evidence,
            "notice": (
                "Approved source evidence was retrieved. ZENDOC v1 does not synthesize a medical answer from this endpoint."
                if found
                else "No approved indexed evidence matched this query. ZENDOC will not answer from model memory as though retrieval succeeded."
            ),
            "requester_role": user["role"],
        }
    )
