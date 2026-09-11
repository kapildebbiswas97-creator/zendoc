"""Deterministic, provenance-bound ingestion foundation for medical RAG.

Only an explicitly APPROVED immutable medical-knowledge document may enter this
pipeline. This stage stores normalized extracted text chunks and provenance; it
does not create embeddings or expose patient-facing medical answers.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .db import get_db, now_iso
from .medical_knowledge_documents import get_approved_medical_knowledge_document
from .security import assert_owner


DEFAULT_MAX_WORDS = 220
DEFAULT_OVERLAP_WORDS = 30
MAX_EXTRACTED_TEXT_CHARS = 5_000_000


def _actor_id(actor: Any) -> int:
    if actor is None:
        return 0
    if hasattr(actor, "keys") and "id" in actor.keys():
        return int(actor["id"] or 0)
    if isinstance(actor, dict):
        return int(actor.get("id") or 0)
    return int(getattr(actor, "id", 0) or 0)


def ensure_medical_rag_schema() -> None:
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS medical_knowledge_ingestions (
            ingestion_uid TEXT PRIMARY KEY,
            document_uid TEXT NOT NULL REFERENCES medical_knowledge_documents(document_uid) ON DELETE RESTRICT,
            parser_name TEXT NOT NULL,
            parser_version TEXT NOT NULL,
            extraction_sha256 TEXT NOT NULL,
            chunking_strategy TEXT NOT NULL,
            max_words INTEGER NOT NULL,
            overlap_words INTEGER NOT NULL,
            chunk_count INTEGER NOT NULL,
            created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_medical_ingestion_identity "
        "ON medical_knowledge_ingestions(document_uid, extraction_sha256, parser_name, parser_version, max_words, overlap_words)"
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS medical_knowledge_chunks (
            chunk_uid TEXT PRIMARY KEY,
            ingestion_uid TEXT NOT NULL REFERENCES medical_knowledge_ingestions(ingestion_uid) ON DELETE CASCADE,
            document_uid TEXT NOT NULL REFERENCES medical_knowledge_documents(document_uid) ON DELETE RESTRICT,
            ordinal INTEGER NOT NULL,
            chunk_text TEXT NOT NULL,
            chunk_sha256 TEXT NOT NULL,
            word_count INTEGER NOT NULL,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_medical_chunk_ordinal "
        "ON medical_knowledge_chunks(ingestion_uid, ordinal)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_medical_chunks_document "
        "ON medical_knowledge_chunks(document_uid, ordinal)"
    )


def normalize_extracted_text(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("extracted_text must be a string.")
    if len(value) > MAX_EXTRACTED_TEXT_CHARS:
        raise ValueError("extracted_text exceeds the bounded ingestion limit.")
    # Preserve paragraph boundaries while removing unstable whitespace.
    paragraphs = []
    for raw in re.split(r"\n\s*\n", value.replace("\r\n", "\n").replace("\r", "\n")):
        cleaned = " ".join(raw.split())
        if cleaned:
            paragraphs.append(cleaned)
    normalized = "\n\n".join(paragraphs).strip()
    if not normalized:
        raise ValueError("extracted_text cannot be empty.")
    return normalized


def chunk_medical_text(
    normalized_text: str,
    *,
    max_words: int = DEFAULT_MAX_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
) -> list[str]:
    try:
        max_words = int(max_words)
        overlap_words = int(overlap_words)
    except (TypeError, ValueError) as error:
        raise ValueError("Chunk sizes must be integers.") from error
    if max_words < 40 or max_words > 1000:
        raise ValueError("max_words must be between 40 and 1000.")
    if overlap_words < 0 or overlap_words >= max_words:
        raise ValueError("overlap_words must be non-negative and smaller than max_words.")

    words = normalized_text.split()
    chunks: list[str] = []
    step = max_words - overlap_words
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += step
    return chunks


def ingest_approved_medical_text(
    actor: Any,
    *,
    document_uid: str,
    extracted_text: str,
    parser_name: str,
    parser_version: str,
    max_words: int = DEFAULT_MAX_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
) -> dict:
    """Persist deterministic chunks for one approved immutable artifact."""
    assert_owner(actor)
    actor_id = _actor_id(actor)
    if not actor_id:
        raise PermissionError("A persisted owner identity is required.")
    document = get_approved_medical_knowledge_document(document_uid)
    parser_name = str(parser_name or "").strip().lower()
    parser_version = str(parser_version or "").strip()
    if not parser_name or len(parser_name) > 80:
        raise ValueError("parser_name is required and must be at most 80 characters.")
    if not parser_version or len(parser_version) > 80:
        raise ValueError("parser_version is required and must be at most 80 characters.")

    normalized = normalize_extracted_text(extracted_text)
    chunks = chunk_medical_text(normalized, max_words=max_words, overlap_words=overlap_words)
    extraction_sha256 = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    identity = json.dumps(
        {
            "document_uid": document["document_uid"],
            "extraction_sha256": extraction_sha256,
            "parser_name": parser_name,
            "parser_version": parser_version,
            "max_words": int(max_words),
            "overlap_words": int(overlap_words),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    ingestion_uid = "mkingest_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]

    ensure_medical_rag_schema()
    db = get_db()
    existing = db.execute(
        "SELECT * FROM medical_knowledge_ingestions WHERE ingestion_uid=?",
        (ingestion_uid,),
    ).fetchone()
    if existing:
        return _serialize_ingestion(existing)

    now = now_iso()
    db.execute(
        """
        INSERT INTO medical_knowledge_ingestions (
            ingestion_uid,document_uid,parser_name,parser_version,extraction_sha256,
            chunking_strategy,max_words,overlap_words,chunk_count,created_by,created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            ingestion_uid,
            document["document_uid"],
            parser_name,
            parser_version,
            extraction_sha256,
            "WORD_WINDOW_V1",
            int(max_words),
            int(overlap_words),
            len(chunks),
            actor_id,
            now,
        ),
    )
    for ordinal, text in enumerate(chunks):
        chunk_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        chunk_uid = f"mkchunk_{hashlib.sha256(f'{ingestion_uid}:{ordinal}:{chunk_sha}'.encode('utf-8')).hexdigest()[:24]}"
        metadata = {
            "source_id": document["source_id"],
            "document_uid": document["document_uid"],
            "document_title": document["document_title"],
            "document_url": document["document_url"],
            "publication_date": document["publication_date"],
            "version": document["version"],
            "content_sha256": document["content_sha256"],
            "extraction_sha256": extraction_sha256,
            "parser_name": parser_name,
            "parser_version": parser_version,
            "ordinal": ordinal,
        }
        db.execute(
            """
            INSERT INTO medical_knowledge_chunks (
                chunk_uid,ingestion_uid,document_uid,ordinal,chunk_text,chunk_sha256,
                word_count,metadata_json,created_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                chunk_uid,
                ingestion_uid,
                document["document_uid"],
                ordinal,
                text,
                chunk_sha,
                len(text.split()),
                json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
                now,
            ),
        )
    db.commit()
    row = db.execute(
        "SELECT * FROM medical_knowledge_ingestions WHERE ingestion_uid=?",
        (ingestion_uid,),
    ).fetchone()
    return _serialize_ingestion(row)


def list_medical_knowledge_chunks(document_uid: str) -> list[dict]:
    # Fail closed if the document has since been rejected/superseded.
    get_approved_medical_knowledge_document(document_uid)
    ensure_medical_rag_schema()
    rows = get_db().execute(
        """
        SELECT * FROM medical_knowledge_chunks
        WHERE document_uid=? ORDER BY ingestion_uid, ordinal
        """,
        (str(document_uid or "").strip(),),
    ).fetchall()
    result = []
    for row in rows:
        item = {key: row[key] for key in row.keys()}
        try:
            item["metadata"] = json.loads(item.pop("metadata_json"))
        except (TypeError, ValueError, json.JSONDecodeError):
            item["metadata"] = {}
        result.append(item)
    return result


def _serialize_ingestion(row: Any) -> dict:
    if row is None:
        raise LookupError("Medical-knowledge ingestion not found.")
    return {key: row[key] for key in row.keys()}
