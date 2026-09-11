"""Durable document-level approval gate for future medical-knowledge RAG.

No document reaches an embedding/indexing pipeline merely because its publisher
is authoritative. A concrete immutable artifact must be registered, reviewed,
and explicitly approved by the configured owner first.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from .db import get_db, now_iso
from .medical_knowledge_registry import validate_medical_knowledge_document
from .security import assert_owner


REVIEW_PENDING = "PENDING"
REVIEW_APPROVED = "APPROVED"
REVIEW_REJECTED = "REJECTED"
REVIEW_SUPERSEDED = "SUPERSEDED"
REVIEW_STATUSES = {REVIEW_PENDING, REVIEW_APPROVED, REVIEW_REJECTED, REVIEW_SUPERSEDED}


def _actor_id(actor: Any) -> int:
    if actor is None:
        return 0
    if hasattr(actor, "keys") and "id" in actor.keys():
        return int(actor["id"] or 0)
    if isinstance(actor, dict):
        return int(actor.get("id") or 0)
    return int(getattr(actor, "id", 0) or 0)


def ensure_medical_knowledge_document_schema() -> None:
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS medical_knowledge_documents (
            document_uid TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            document_title TEXT NOT NULL,
            document_url TEXT NOT NULL,
            publication_date TEXT NOT NULL,
            retrieved_at TEXT NOT NULL,
            content_sha256 TEXT NOT NULL,
            usage_basis TEXT NOT NULL,
            version TEXT NOT NULL,
            review_status TEXT NOT NULL,
            review_notes TEXT,
            registered_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            reviewed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            reviewed_at TEXT,
            supersedes_document_uid TEXT REFERENCES medical_knowledge_documents(document_uid) ON DELETE SET NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_medical_knowledge_document_artifact "
        "ON medical_knowledge_documents(source_id, content_sha256)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_medical_knowledge_review_status "
        "ON medical_knowledge_documents(review_status, source_id, publication_date)"
    )


def _document_uid(document: dict) -> str:
    canonical = json.dumps(
        {
            "source_id": document["source_id"],
            "document_url": document["document_url"],
            "publication_date": document["publication_date"],
            "content_sha256": document["content_sha256"],
            "version": document["version"],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"mkdoc_{digest[:24]}"


def register_medical_knowledge_document(actor: Any, metadata: dict) -> dict:
    """Register an immutable artifact as PENDING after structural validation."""
    assert_owner(actor)
    actor_id = _actor_id(actor)
    if not actor_id:
        raise PermissionError("A persisted owner identity is required.")

    validated = validate_medical_knowledge_document(metadata)
    document = deepcopy(validated["document"])
    document_uid = _document_uid(document)
    ensure_medical_knowledge_document_schema()
    db = get_db()
    existing = db.execute(
        "SELECT * FROM medical_knowledge_documents WHERE document_uid=?",
        (document_uid,),
    ).fetchone()
    if existing:
        return _serialize(existing)

    duplicate = db.execute(
        "SELECT document_uid FROM medical_knowledge_documents WHERE source_id=? AND content_sha256=?",
        (document["source_id"], document["content_sha256"]),
    ).fetchone()
    if duplicate:
        row = db.execute(
            "SELECT * FROM medical_knowledge_documents WHERE document_uid=?",
            (duplicate["document_uid"],),
        ).fetchone()
        return _serialize(row)

    now = now_iso()
    db.execute(
        """
        INSERT INTO medical_knowledge_documents (
            document_uid,source_id,document_title,document_url,publication_date,retrieved_at,
            content_sha256,usage_basis,version,review_status,review_notes,registered_by,
            reviewed_by,reviewed_at,supersedes_document_uid,created_at,updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,NULL,?,?)
        """,
        (
            document_uid,
            document["source_id"],
            document["document_title"],
            document["document_url"],
            document["publication_date"],
            document["retrieved_at"],
            document["content_sha256"],
            document["usage_basis"],
            document["version"],
            REVIEW_PENDING,
            None,
            actor_id,
            now,
            now,
        ),
    )
    db.commit()
    row = db.execute(
        "SELECT * FROM medical_knowledge_documents WHERE document_uid=?",
        (document_uid,),
    ).fetchone()
    return _serialize(row)


def review_medical_knowledge_document(
    actor: Any,
    document_uid: str,
    *,
    decision: str,
    notes: str,
    supersedes_document_uid: str | None = None,
) -> dict:
    """Explicit owner review. Only APPROVED artifacts may be handed to ingestion."""
    assert_owner(actor)
    actor_id = _actor_id(actor)
    if not actor_id:
        raise PermissionError("A persisted owner identity is required.")
    decision = str(decision or "").strip().upper()
    if decision not in {REVIEW_APPROVED, REVIEW_REJECTED}:
        raise ValueError("decision must be APPROVED or REJECTED.")
    notes = str(notes or "").strip()
    if len(notes) < 12:
        raise ValueError("Review notes must record the usage/content review basis.")

    ensure_medical_knowledge_document_schema()
    db = get_db()
    row = db.execute(
        "SELECT * FROM medical_knowledge_documents WHERE document_uid=?",
        (str(document_uid or "").strip(),),
    ).fetchone()
    if not row:
        raise LookupError("Medical-knowledge document not found.")
    if row["review_status"] in {REVIEW_APPROVED, REVIEW_REJECTED, REVIEW_SUPERSEDED}:
        raise ValueError("Reviewed medical-knowledge documents are immutable; register a new artifact/version instead.")

    supersedes = str(supersedes_document_uid or "").strip() or None
    if supersedes:
        previous = db.execute(
            "SELECT * FROM medical_knowledge_documents WHERE document_uid=?",
            (supersedes,),
        ).fetchone()
        if not previous:
            raise LookupError("Superseded medical-knowledge document not found.")
        if previous["source_id"] != row["source_id"]:
            raise ValueError("A medical-knowledge document may supersede only a document from the same source family.")
        if previous["review_status"] != REVIEW_APPROVED:
            raise ValueError("Only an approved document may be superseded.")
        if supersedes == row["document_uid"]:
            raise ValueError("A document cannot supersede itself.")

    now = now_iso()
    db.execute(
        """
        UPDATE medical_knowledge_documents
        SET review_status=?, review_notes=?, reviewed_by=?, reviewed_at=?,
            supersedes_document_uid=?, updated_at=?
        WHERE document_uid=? AND review_status=?
        """,
        (decision, notes, actor_id, now, supersedes, now, row["document_uid"], REVIEW_PENDING),
    )
    if supersedes and decision == REVIEW_APPROVED:
        db.execute(
            """
            UPDATE medical_knowledge_documents
            SET review_status=?, updated_at=?
            WHERE document_uid=? AND review_status=?
            """,
            (REVIEW_SUPERSEDED, now, supersedes, REVIEW_APPROVED),
        )
    db.commit()
    reviewed = db.execute(
        "SELECT * FROM medical_knowledge_documents WHERE document_uid=?",
        (row["document_uid"],),
    ).fetchone()
    return _serialize(reviewed)


def list_medical_knowledge_documents(*, status: str | None = None, source_id: str | None = None) -> list[dict]:
    ensure_medical_knowledge_document_schema()
    clauses = []
    params: list[Any] = []
    if status:
        normalized_status = str(status).strip().upper()
        if normalized_status not in REVIEW_STATUSES:
            raise ValueError("Unsupported medical-knowledge review status.")
        clauses.append("review_status=?")
        params.append(normalized_status)
    if source_id:
        clauses.append("source_id=?")
        params.append(str(source_id).strip().lower())
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = get_db().execute(
        "SELECT * FROM medical_knowledge_documents" + where + " ORDER BY publication_date DESC, created_at DESC",
        tuple(params),
    ).fetchall()
    return [_serialize(row) for row in rows]


def get_approved_medical_knowledge_document(document_uid: str) -> dict:
    """The only handoff a later indexing pipeline should accept."""
    ensure_medical_knowledge_document_schema()
    row = get_db().execute(
        "SELECT * FROM medical_knowledge_documents WHERE document_uid=? AND review_status=?",
        (str(document_uid or "").strip(), REVIEW_APPROVED),
    ).fetchone()
    if not row:
        raise PermissionError("Document is not approved for medical-knowledge ingestion.")
    return _serialize(row)


def _serialize(row: Any) -> dict:
    if row is None:
        raise LookupError("Medical-knowledge document not found.")
    return {key: row[key] for key in row.keys()}
