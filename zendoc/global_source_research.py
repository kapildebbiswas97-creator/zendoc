"""Bounded source-gap research automation for the Global Health Intelligence Fabric.

The operations worker does not crawl the open web or bypass protected portals.
Instead it turns truthful jurisdiction source gaps into one deduplicated,
persistent ResearchAgent work batch. Known machine-readable connectors continue
to refresh through public_data_refresh; unknown jurisdictions remain explicit
research work until an authoritative permitted source is reviewed.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from .agent_task_engine import create_agent_task
from .continental_coverage import install_continental_coverage
from .db import get_db
from .global_source_registry import country_coverage_manifest
from .security import assert_owner


def global_source_gap_report() -> dict:
    install_continental_coverage()
    countries = country_coverage_manifest()
    gaps = [
        {
            "country_code": item["country_code"],
            "country_name": item["country_name"],
            "continent": item.get("continent") or "Other",
            "coverage_status": item.get("coverage_status"),
        }
        for item in countries
        if int(item.get("source_count") or 0) == 0
    ]
    by_continent = Counter(item["continent"] for item in gaps)
    return {
        "country_count": len(countries),
        "source_registered_country_count": len(countries) - len(gaps),
        "source_gap_count": len(gaps),
        "source_gaps_by_continent": dict(sorted(by_continent.items())),
        "gaps": sorted(gaps, key=lambda item: (item["continent"], item["country_name"])),
        "truth_notice": (
            "A source gap means no reviewed country-specific public healthcare source is registered yet. "
            "It does not mean the country lacks healthcare data, and ZENDOC must not fill the gap with guessed or unauthorized data."
        ),
    }


def _owner_id(actor: Any) -> int:
    if hasattr(actor, "keys") and "id" in actor.keys():
        return int(actor["id"])
    if isinstance(actor, dict):
        return int(actor.get("id") or 0)
    return 0


def enqueue_source_research_batch(actor: Any, *, max_countries: int = 12) -> dict:
    assert_owner(actor)
    max_countries = max(1, min(int(max_countries or 12), 25))
    report = global_source_gap_report()
    selected = report["gaps"][:max_countries]
    if not selected:
        return {
            "created": False,
            "task": None,
            "source_gap_count": 0,
            "selected_countries": [],
            "notice": "All represented jurisdictions currently have at least one reviewed source registration.",
        }

    all_gap_codes = ",".join(item["country_code"] for item in report["gaps"])
    gap_hash = hashlib.sha256(all_gap_codes.encode("utf-8")).hexdigest()[:20]
    key = f"global-source-research:{gap_hash}"
    metadata = {
        "workforce_owner": "ResearchAgent",
        "manager_agent": "ManagerAgent",
        "task_kind": "authoritative_health_source_discovery",
        "selected_countries": selected,
        "source_gap_count": report["source_gap_count"],
        "required_evidence": [
            "official_or_authoritative_owner",
            "https_source_url",
            "access_mode_and_auth_requirements",
            "machine_readability_or_snapshot_format",
            "terms_or_public_use_basis",
            "refresh_cadence",
            "stable_source_identifier",
            "personal_data_boundary",
        ],
        "forbidden": [
            "private_user_data_collection",
            "captcha_or_auth_bypass",
            "paywall_bypass",
            "robots_or_terms_bypass",
            "fabricated_api_or_dataset",
            "automatic_ingestion_before_source_review",
        ],
    }
    existing = get_db().execute(
        "SELECT * FROM agent_tasks WHERE idempotency_key=?",
        (key,),
    ).fetchone()
    if existing:
        return {
            "created": False,
            "task": dict(existing),
            "source_gap_count": report["source_gap_count"],
            "selected_countries": selected,
            "idempotency_key": key,
            "production_changes_executed": 0,
            "notice": "Existing bounded ResearchAgent source-gap batch reused; no duplicate task created.",
        }

    task = create_agent_task(
        task_type="global_source_research",
        requested_by=_owner_id(actor),
        assigned_agent="OperationsAgent",
        priority="normal",
        risk_level="low_risk",
        max_attempts=1,
        idempotency_key=key,
        metadata=metadata,
        actor=actor,
    )
    stored_meta = json.loads(task.get("metadata_json") or "{}")
    return {
        "created": stored_meta == metadata,
        "task": task,
        "source_gap_count": report["source_gap_count"],
        "selected_countries": selected,
        "idempotency_key": key,
        "production_changes_executed": 0,
        "notice": "The ResearchAgent work batch is discovery/review only. It cannot authorize ingestion or access protected/private systems.",
    }
