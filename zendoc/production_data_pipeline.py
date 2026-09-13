"""Owner-only readiness view for ZENDOC's four production data tracks.

This module never fabricates facility, provider, medical, stock, price, or slot
records. It reports what is actually persisted and the next truthful action
required to advance each track.
"""
from __future__ import annotations

from typing import Any

from flask import current_app

from .db import get_db
from .public_source_registry import list_public_ingestion_sources
from .security import assert_owner


def production_data_pipeline_status(actor: Any) -> dict:
    assert_owner(actor)
    db = get_db()

    official_rows = _count(db, "public_healthcare_entities", "active=1")
    completed_imports = _count(
        db,
        "data_ingestion_batches",
        "dry_run=0 AND status='completed' AND ingestion_type='public_healthcare_entities'",
    )
    importable_sources = [
        source for source in list_public_ingestion_sources()
        if "public_healthcare_entities" in (source.get("ingestion_types") or [])
    ]

    provider_profiles = _count(db, "provider_profiles")
    verified_providers = _count(db, "provider_profiles", "verification_status='verified'")
    pending_evidence = _count(db, "provider_verification_evidence", "status='pending'")
    verified_evidence = _count(db, "provider_verification_evidence", "status='verified'")
    active_schedules = _count(db, "provider_schedules", "active=1")

    rag_documents = _count(db, "medical_knowledge_documents")
    approved_rag_documents = _count(db, "medical_knowledge_documents", "review_status='APPROVED'")
    rag_chunks = _count(db, "medical_knowledge_chunks")
    rag_embeddings = _count(db, "medical_knowledge_embeddings")

    pharmacy_profiles = _count(
        db,
        "provider_profiles",
        "provider_type='pharmacy' AND verification_status='verified'",
    )
    inventory_observations = _count(db, "inventory_observations")
    medicine_orders = _count(db, "medicine_orders")
    appointments = _count(db, "appointments")

    tracks = [
        {
            "track": "official_healthcare_dataset_ingestion",
            "label": "Official healthcare dataset ingestion",
            "status": "ready" if official_rows > 0 and completed_imports > 0 else "needs_data",
            "persisted_records": official_rows,
            "proof_count": completed_imports,
            "available_source_families": len(importable_sources),
            "next_action": (
                "Refresh stale/aging official sources with dated artifacts and preserve provenance."
                if official_rows > 0 and completed_imports > 0
                else "Acquire a dated official facility artifact, run dry-run validation, then apply an owner-approved import."
            ),
            "truth_rule": "Official/public rows remain discovery/reference data until a separate provider claim/onboarding is approved.",
        },
        {
            "track": "real_provider_onboarding",
            "label": "Real provider onboarding",
            "status": "ready" if verified_providers > 0 else ("in_progress" if provider_profiles > 0 else "needs_data"),
            "persisted_records": provider_profiles,
            "verified_records": verified_providers,
            "pending_evidence": pending_evidence,
            "verified_evidence": verified_evidence,
            "active_schedules": active_schedules,
            "next_action": (
                "Expand verified provider schedules and operational connectivity."
                if verified_providers > 0
                else "Onboard real doctors/hospitals/pharmacies, collect official evidence, and complete owner verification."
            ),
            "truth_rule": "A web listing or official directory row never becomes a ZENDOC-verified provider automatically.",
        },
        {
            "track": "ai_medical_corpus_ingestion",
            "label": "AI medical corpus ingestion",
            "status": "ready" if approved_rag_documents > 0 and rag_chunks > 0 else ("in_progress" if rag_documents > 0 else "needs_data"),
            "persisted_records": rag_documents,
            "approved_documents": approved_rag_documents,
            "chunks": rag_chunks,
            "embeddings": rag_embeddings,
            "next_action": (
                "Continue versioned corpus refresh and retrieval evaluation."
                if approved_rag_documents > 0 and rag_chunks > 0
                else "Register immutable WHO/MoHFW/ICMR/NCDC artifacts, review them, approve explicitly, then ingest chunks."
            ),
            "truth_rule": "Raw live web pages are not trusted medical evidence and cannot bypass document review.",
        },
        {
            "track": "operational_pharmacy_appointment_data",
            "label": "Operational pharmacy & appointment data",
            "status": "ready" if (appointments > 0 or inventory_observations > 0) else "needs_data",
            "appointments": appointments,
            "verified_pharmacies": pharmacy_profiles,
            "inventory_observations": inventory_observations,
            "medicine_orders": medicine_orders,
            "next_action": (
                "Keep provider schedules, inventory observations, and order state fresh from connected operators."
                if (appointments > 0 or inventory_observations > 0)
                else "Connect verified provider schedules and pharmacy observations; do not infer stock, prices, or slots from the internet."
            ),
            "truth_rule": "Only connected/recorded operational data may claim live slots, stock, prices, or fulfilment state.",
        },
    ]

    counts = {"ready": 0, "in_progress": 0, "needs_data": 0}
    for track in tracks:
        counts[track["status"]] = counts.get(track["status"], 0) + 1

    return {
        "database_engine": str(current_app.config.get("DATABASE_ENGINE") or "sqlite"),
        "tracks": tracks,
        "status_counts": counts,
        "all_ready": all(track["status"] == "ready" for track in tracks),
        "truth_notice": (
            "Pipeline readiness is based only on records persisted in this ZENDOC database. "
            "Internet discovery never upgrades itself into verified, clinical, stock, price, or booking truth."
        ),
    }


def _table_exists(db: Any, table: str) -> bool:
    engine = str(current_app.config.get("DATABASE_ENGINE") or "sqlite").lower()
    if engine == "postgresql":
        row = db.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema='public' AND table_name=?
            ) AS present
            """,
            (table,),
        ).fetchone()
        return bool(row and row["present"])
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def _count(db: Any, table: str, where: str | None = None) -> int:
    if not _table_exists(db, table):
        return 0
    sql = f"SELECT COUNT(*) AS c FROM {table}"
    if where:
        sql += f" WHERE {where}"
    row = db.execute(sql).fetchone()
    return int(row["c"] if row else 0)
