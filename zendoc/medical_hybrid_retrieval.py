"""Evidence-first medical knowledge retrieval with truthful pgvector fallback.

Lexical retrieval is always deterministic over APPROVED document chunks.
Vector storage/search is enabled only when PostgreSQL is configured *and* the
`vector` extension is already installed. The application never claims vector
retrieval succeeded when the capability is unavailable.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

from flask import current_app

from .db import get_db, now_iso
from .medical_knowledge_documents import REVIEW_APPROVED
from .security import assert_owner


TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def _tokens(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(str(text or "")) if len(token) > 1]


def pgvector_capability() -> dict:
    if current_app.config.get("DATABASE_ENGINE") != "postgresql":
        return {
            "available": False,
            "status": "INTEGRATION_REQUIRED",
            "reason": "PGVECTOR_REQUIRES_POSTGRESQL",
        }
    try:
        row = get_db().execute(
            "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector') AS enabled"
        ).fetchone()
    except Exception:
        return {
            "available": False,
            "status": "INTEGRATION_REQUIRED",
            "reason": "PGVECTOR_EXTENSION_CHECK_FAILED",
        }
    enabled = bool(row and row["enabled"])
    return {
        "available": enabled,
        "status": "WORKING" if enabled else "INTEGRATION_REQUIRED",
        "reason": None if enabled else "PGVECTOR_EXTENSION_NOT_INSTALLED",
    }


def ensure_pgvector_schema() -> bool:
    capability = pgvector_capability()
    if not capability["available"]:
        return False
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS medical_knowledge_embeddings (
            chunk_uid TEXT PRIMARY KEY REFERENCES medical_knowledge_chunks(chunk_uid) ON DELETE CASCADE,
            embedding_model TEXT NOT NULL,
            dimensions INTEGER NOT NULL,
            embedding vector NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_medical_embeddings_model "
        "ON medical_knowledge_embeddings(embedding_model, dimensions)"
    )
    return True


def lexical_medical_retrieval(query: str, *, limit: int = 8) -> list[dict]:
    terms = _tokens(query)
    if not terms:
        raise ValueError("A non-empty medical knowledge query is required.")
    try:
        limit = int(limit)
    except (TypeError, ValueError) as error:
        raise ValueError("limit must be an integer.") from error
    if limit < 1 or limit > 25:
        raise ValueError("limit must be between 1 and 25.")

    rows = get_db().execute(
        """
        SELECT c.chunk_uid,c.document_uid,c.ordinal,c.chunk_text,c.chunk_sha256,c.metadata_json,
               d.document_title,d.document_url,d.publication_date,d.version,d.source_id,d.content_sha256
        FROM medical_knowledge_chunks c
        JOIN medical_knowledge_documents d ON d.document_uid=c.document_uid
        WHERE d.review_status=?
        ORDER BY d.publication_date DESC,c.document_uid,c.ordinal
        """,
        (REVIEW_APPROVED,),
    ).fetchall()

    scored = []
    unique_terms = sorted(set(terms))
    for row in rows:
        text_tokens = _tokens(row["chunk_text"])
        if not text_tokens:
            continue
        counts = {term: text_tokens.count(term) for term in unique_terms}
        matched = sum(1 for value in counts.values() if value > 0)
        frequency = sum(counts.values())
        if not matched:
            continue
        coverage = matched / len(unique_terms)
        density = min(1.0, frequency / max(1, len(text_tokens)) * 20.0)
        phrase_bonus = 0.15 if " ".join(terms) in " ".join(text_tokens) else 0.0
        score = min(1.0, 0.70 * coverage + 0.30 * density + phrase_bonus)
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            metadata = {}
        scored.append(
            {
                "chunk_uid": row["chunk_uid"],
                "document_uid": row["document_uid"],
                "ordinal": row["ordinal"],
                "text": row["chunk_text"],
                "lexical_score": round(score, 6),
                "evidence": {
                    "source_id": row["source_id"],
                    "document_title": row["document_title"],
                    "document_url": row["document_url"],
                    "publication_date": row["publication_date"],
                    "version": row["version"],
                    "content_sha256": row["content_sha256"],
                    "chunk_sha256": row["chunk_sha256"],
                    "metadata": metadata,
                },
            }
        )
    scored.sort(key=lambda item: (-item["lexical_score"], item["evidence"]["publication_date"], item["chunk_uid"]), reverse=False)
    return scored[:limit]


def _validated_embedding(values: Any) -> list[float]:
    if not isinstance(values, (list, tuple)):
        raise ValueError("embedding must be a numeric list.")
    if len(values) < 8 or len(values) > 4096:
        raise ValueError("embedding dimensions must be between 8 and 4096.")
    result = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError("embedding must contain only numeric values.") from error
        if not math.isfinite(number):
            raise ValueError("embedding values must be finite.")
        result.append(number)
    return result


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(format(value, ".12g") for value in values) + "]"


def store_medical_chunk_embedding(
    actor: Any,
    *,
    chunk_uid: str,
    embedding_model: str,
    embedding: Any,
) -> dict:
    assert_owner(actor)
    if not ensure_pgvector_schema():
        raise RuntimeError("PGVECTOR_INTEGRATION_REQUIRED")
    model = str(embedding_model or "").strip()
    if not model or len(model) > 160:
        raise ValueError("embedding_model is required and must be at most 160 characters.")
    vector = _validated_embedding(embedding)

    row = get_db().execute(
        """
        SELECT c.chunk_uid,d.review_status
        FROM medical_knowledge_chunks c
        JOIN medical_knowledge_documents d ON d.document_uid=c.document_uid
        WHERE c.chunk_uid=?
        """,
        (str(chunk_uid or "").strip(),),
    ).fetchone()
    if not row or row["review_status"] != REVIEW_APPROVED:
        raise PermissionError("Embedding storage requires a chunk from an approved medical-knowledge document.")

    now = now_iso()
    db = get_db()
    existing = db.execute(
        "SELECT chunk_uid,embedding_model,dimensions FROM medical_knowledge_embeddings WHERE chunk_uid=?",
        (row["chunk_uid"],),
    ).fetchone()
    if existing:
        if existing["embedding_model"] != model or int(existing["dimensions"]) != len(vector):
            raise ValueError("Existing chunk embedding is immutable; create a new ingestion/index version for a different model.")
        return {"chunk_uid": existing["chunk_uid"], "embedding_model": model, "dimensions": len(vector), "status": "EXISTS"}

    db.execute(
        """
        INSERT INTO medical_knowledge_embeddings
        (chunk_uid,embedding_model,dimensions,embedding,created_at,updated_at)
        VALUES (?,?,?,CAST(? AS vector),?,?)
        """,
        (row["chunk_uid"], model, len(vector), _vector_literal(vector), now, now),
    )
    db.commit()
    return {"chunk_uid": row["chunk_uid"], "embedding_model": model, "dimensions": len(vector), "status": "CREATED"}


def _vector_medical_retrieval(query_embedding: Any, *, embedding_model: str, limit: int) -> list[dict]:
    if not ensure_pgvector_schema():
        return []
    vector = _validated_embedding(query_embedding)
    model = str(embedding_model or "").strip()
    if not model:
        raise ValueError("embedding_model is required for vector retrieval.")
    literal = _vector_literal(vector)
    rows = get_db().execute(
        """
        SELECT c.chunk_uid,c.document_uid,c.ordinal,c.chunk_text,c.chunk_sha256,c.metadata_json,
               d.document_title,d.document_url,d.publication_date,d.version,d.source_id,d.content_sha256,
               1 - (e.embedding <=> CAST(? AS vector)) AS vector_score
        FROM medical_knowledge_embeddings e
        JOIN medical_knowledge_chunks c ON c.chunk_uid=e.chunk_uid
        JOIN medical_knowledge_documents d ON d.document_uid=c.document_uid
        WHERE e.embedding_model=? AND e.dimensions=? AND d.review_status=?
        ORDER BY e.embedding <=> CAST(? AS vector)
        LIMIT ?
        """,
        (literal, model, len(vector), REVIEW_APPROVED, literal, int(limit)),
    ).fetchall()
    result = []
    for row in rows:
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            metadata = {}
        result.append(
            {
                "chunk_uid": row["chunk_uid"],
                "document_uid": row["document_uid"],
                "ordinal": row["ordinal"],
                "text": row["chunk_text"],
                "vector_score": max(0.0, min(1.0, float(row["vector_score"] or 0.0))),
                "evidence": {
                    "source_id": row["source_id"],
                    "document_title": row["document_title"],
                    "document_url": row["document_url"],
                    "publication_date": row["publication_date"],
                    "version": row["version"],
                    "content_sha256": row["content_sha256"],
                    "chunk_sha256": row["chunk_sha256"],
                    "metadata": metadata,
                },
            }
        )
    return result


def hybrid_medical_retrieval(
    query: str,
    *,
    query_embedding: Any | None = None,
    embedding_model: str | None = None,
    limit: int = 8,
) -> dict:
    lexical = lexical_medical_retrieval(query, limit=min(25, max(int(limit) * 3, int(limit))))
    capability = pgvector_capability()
    vector = []
    if query_embedding is not None and capability["available"]:
        vector = _vector_medical_retrieval(
            query_embedding,
            embedding_model=str(embedding_model or ""),
            limit=min(25, max(int(limit) * 3, int(limit))),
        )

    merged: dict[str, dict] = {}
    for item in lexical:
        merged[item["chunk_uid"]] = {**item, "vector_score": 0.0}
    for item in vector:
        current = merged.get(item["chunk_uid"])
        if current:
            current["vector_score"] = item["vector_score"]
        else:
            merged[item["chunk_uid"]] = {**item, "lexical_score": 0.0}

    for item in merged.values():
        if vector:
            item["hybrid_score"] = round(0.45 * float(item.get("lexical_score", 0.0)) + 0.55 * float(item.get("vector_score", 0.0)), 6)
        else:
            item["hybrid_score"] = round(float(item.get("lexical_score", 0.0)), 6)
    results = sorted(merged.values(), key=lambda item: (-item["hybrid_score"], item["chunk_uid"]))[: int(limit)]
    return {
        "mode": "HYBRID" if vector else "LEXICAL_ONLY",
        "pgvector": capability,
        "results": results,
        "grounding_required": True,
        "notice": (
            "Vector retrieval was unavailable or not requested; results use approved-document lexical retrieval only."
            if not vector
            else "Results combine lexical and pgvector similarity over approved-document chunks."
        ),
    }
