"""Authorized, provenance-preserving Health Memory retrieval for Agent OS.

This is a local, software-only RAG retrieval layer over records already stored in
ZENDOC. It does not call an external vector service, does not create clinical
facts, and does not treat prior AI chat text as medical evidence.

The returned evidence can be used as bounded context by a later language layer,
but this module itself performs retrieval only.
"""
from __future__ import annotations

import re
from typing import Any

from .context_engine import verify_context_authorization
from .db import get_db
from .health_timeline import EVENTS_SQL


MAX_QUERY_CHARS = 500
MAX_CANDIDATES = 100
MAX_RESULTS = 10

_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "i",
    "in", "is", "it", "me", "my", "of", "on", "or", "the", "to", "was",
    "were", "what", "when", "where", "which", "with",
}

_VERBATIM_PROVENANCE = {
    "PROVIDER_RECORDED",
    "OWNER_RECORDED",
    "DOCUMENT_EXTRACTED",
    "DEVICE_RECORDED",
    "USER_REPORTED",
}

_SOURCE_LABELS = {
    "appointments": "ZENDOC_APPOINTMENT_RECORD",
    "medical_records": "ZENDOC_STORED_RECORD",
    "health_metrics": "ZENDOC_MEASUREMENT_RECORD",
}


def _actor_id(actor: Any) -> int:
    if actor is None:
        return 0
    if isinstance(actor, (int, float)):
        return int(actor)
    if hasattr(actor, "keys") and "id" in actor.keys():
        return int(actor["id"] or 0)
    if isinstance(actor, dict):
        return int(actor.get("id") or 0)
    return int(getattr(actor, "id", 0) or 0)


def _limit(value: Any) -> int:
    try:
        parsed = int(value or 5)
    except (TypeError, ValueError):
        parsed = 5
    return max(1, min(parsed, MAX_RESULTS))


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", str(value or "").lower())
        if len(token) > 1 and token not in _STOP_WORDS
    }


def _event_text(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(key) or "")
        for key in ("event_type", "title", "summary", "provider_name", "event_at")
    ).strip()


def _provenance(item: dict[str, Any]) -> str:
    source = str(item.get("source") or "").strip()
    upper = source.upper()
    if upper in _VERBATIM_PROVENANCE:
        return upper
    return _SOURCE_LABELS.get(source.lower(), "ZENDOC_STORED_EVENT")


def _score(query: str, query_tokens: set[str], item: dict[str, Any]) -> int:
    haystack = _event_text(item).lower()
    event_tokens = _tokens(haystack)
    score = len(query_tokens & event_tokens) * 4

    clean_query = " ".join(str(query or "").lower().split())
    if clean_query and len(clean_query) >= 3 and clean_query in haystack:
        score += 8

    title = str(item.get("title") or "").lower()
    if query_tokens and query_tokens & _tokens(title):
        score += 2
    return score


def search_health_memory_evidence(
    actor: Any,
    query: str = "",
    *,
    patient_id: int | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Retrieve authorized patient evidence without inventing facts.

    The caller must already be authenticated. Self-access is permitted; any
    delegated access is validated by the existing context/consent engine.
    Prior AI-interaction rows are deliberately excluded so generated or
    user-entered chat text cannot become circular medical evidence.
    """
    actor_id = _actor_id(actor)
    target_id = int(patient_id or actor_id or 0)
    if not actor_id or not target_id:
        raise PermissionError("Authentication is required.")

    verify_context_authorization(actor, target_id, "health_memory_view")

    clean_query = " ".join(str(query or "").strip().split())[:MAX_QUERY_CHARS]
    query_tokens = _tokens(clean_query)

    rows = get_db().execute(
        EVENTS_SQL
        + " SELECT * FROM events ORDER BY event_at DESC, source_id DESC LIMIT ?",
        tuple([target_id] * 5 + [MAX_CANDIDATES]),
    ).fetchall()

    candidates: list[dict[str, Any]] = []
    excluded_ai_interactions = 0
    for row in rows:
        item = dict(row)
        if str(item.get("source") or "").lower() == "ai_interactions":
            excluded_ai_interactions += 1
            continue
        candidates.append(item)

    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for index, item in enumerate(candidates):
        score = _score(clean_query, query_tokens, item) if query_tokens else 1
        if query_tokens and score <= 0:
            continue
        ranked.append((score, index, item))

    if query_tokens:
        ranked.sort(key=lambda row: (-row[0], row[1]))
    selected = ranked[: _limit(limit)]

    matches = []
    for score, _index, item in selected:
        matches.append(
            {
                "evidence_id": f"{item.get('source')}:{item.get('source_id')}",
                "event_type": str(item.get("event_type") or ""),
                "event_at": str(item.get("event_at") or ""),
                "title": str(item.get("title") or "")[:180],
                "summary": str(item.get("summary") or "")[:600],
                "provider_name": str(item.get("provider_name") or "")[:160] or None,
                "source": str(item.get("source") or ""),
                "provenance": _provenance(item),
                "lexical_score": score if query_tokens else None,
            }
        )

    status = "OK" if matches else "NO_MATCHES"
    context_lines = [
        (
            f"[{item['evidence_id']} | {item['provenance']} | {item['event_at']}] "
            f"{item['title']}"
            + (f" — {item['summary']}" if item["summary"] else "")
        )[:900]
        for item in matches
    ]

    return {
        "status": status,
        "patient_id": target_id,
        "query": clean_query,
        "retrieval_mode": "authorized_lexical_health_memory_rag",
        "model_called": False,
        "candidate_count": len(candidates),
        "match_count": len(matches),
        "matches": matches,
        "context_lines": context_lines,
        "excluded_ai_interaction_count": excluded_ai_interactions,
        "truth_notice": (
            "Results are retrieved only from authorized ZENDOC-stored events. "
            "Prior AI chat interactions are excluded from evidence. Retrieval does not diagnose, "
            "prescribe, verify a user-reported fact, or prove an external event beyond its recorded provenance."
        ),
    }
