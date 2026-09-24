"""Jev / System One decision adapter for the ZENDOC Agent OS.

Jev is used only as a bounded decision primitive. It never receives tool
credentials, never executes tools, and never overrides deterministic safety,
consent, clinical, payment, or owner-approval policy.

HTTP contract:
    POST /v1/systemone
    {model, state, questions} -> {model, answers, usage}
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://api.typesafe.ai"
DEFAULT_MODEL = "jev-latest"
QUESTION_TYPES = {"noul", "choice", "score"}


class JevError(RuntimeError):
    pass


class JevUnavailable(JevError):
    pass


class JevProtocolError(JevError):
    pass


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _validated_base_url() -> str:
    base_url = str(os.environ.get("ZENDOC_JEV_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme == "https" and parsed.netloc:
        return base_url
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return base_url
    raise JevUnavailable(
        "ZENDOC_JEV_BASE_URL must use HTTPS, except a loopback HTTP endpoint for local development."
    )


def jev_runtime_status() -> dict:
    enabled = _env_bool("ZENDOC_JEV_ENABLED", False)
    base_url = str(os.environ.get("ZENDOC_JEV_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")
    model = str(os.environ.get("ZENDOC_JEV_MODEL") or DEFAULT_MODEL).strip()
    api_key_present = bool(str(os.environ.get("ZENDOC_JEV_API_KEY") or "").strip())
    context_mode = str(os.environ.get("ZENDOC_JEV_CONTEXT_MODE") or "metadata_only").strip().lower()
    trust_mode = str(os.environ.get("ZENDOC_JEV_TRUST_MODE") or "external_unverified").strip().lower()
    parsed = urlparse(base_url)
    loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    configured = enabled and bool(model) and (api_key_present or loopback)
    return {
        "enabled": enabled,
        "configured": configured,
        "status": "configured" if configured else ("integration_required" if enabled else "disabled"),
        "base_url": base_url,
        "model": model,
        "api_key_present": api_key_present,
        "context_mode": context_mode,
        "trust_mode": trust_mode,
        "external_provider": not loopback,
        "confidence_threshold": _env_float(
            "ZENDOC_JEV_CONFIDENCE_THRESHOLD", 0.85, minimum=0.50, maximum=0.99
        ),
        "truth_notice": (
            "Configuration does not prove provider availability or decision quality. "
            "Jev decisions can narrow automation but never broaden ZENDOC permissions."
        ),
    }


def _validate_questions(questions: dict) -> dict:
    if not isinstance(questions, dict) or not questions:
        raise ValueError("Jev questions must be a non-empty mapping.")
    if len(questions) > 64:
        raise ValueError("Jev questions are capped at 64 per request.")

    validated = {}
    for key, question in questions.items():
        qid = str(key or "").strip()
        if not qid or len(qid) > 80:
            raise ValueError("Each Jev question requires a short stable id.")
        if not isinstance(question, dict):
            raise ValueError(f"Jev question {qid} must be an object.")
        qtype = str(question.get("type") or "").strip().lower()
        if qtype not in QUESTION_TYPES:
            raise ValueError(f"Unsupported Jev question type for {qid}: {qtype}.")
        instructions = question.get("instructions")
        if instructions in (None, "", [], {}):
            raise ValueError(f"Jev question {qid} requires instructions.")
        item = {"type": qtype, "instructions": instructions}
        if "criteria" in question:
            item["criteria"] = question["criteria"]
        if qtype == "choice":
            criteria = item.get("criteria")
            if not isinstance(criteria, dict) or not criteria:
                raise ValueError(f"Choice question {qid} requires non-empty criteria.")
        if qtype == "score":
            criteria = item.get("criteria")
            if not isinstance(criteria, list) or len(criteria) < 2:
                raise ValueError(f"Score question {qid} requires at least two ordered levels.")
        validated[qid] = item
    return validated


def _validate_response(payload: dict, questions: dict) -> dict:
    if not isinstance(payload, dict):
        raise JevProtocolError("Jev returned a non-object response.")
    answers = payload.get("answers")
    if not isinstance(answers, dict):
        raise JevProtocolError("Jev response is missing an answers object.")

    for qid, question in questions.items():
        answer = answers.get(qid)
        if not isinstance(answer, dict):
            raise JevProtocolError(f"Jev response is missing answer {qid}.")
        if answer.get("type") != question["type"]:
            raise JevProtocolError(f"Jev answer type mismatch for {qid}.")
        if question["type"] == "noul":
            value = answer.get("noul")
            if not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
                raise JevProtocolError(f"Invalid noul value for {qid}.")
        elif question["type"] == "choice":
            choice = answer.get("choice")
            probabilities = answer.get("probabilities")
            confidence = answer.get("confidence")
            if choice not in question["criteria"]:
                raise JevProtocolError(f"Choice answer for {qid} is outside declared criteria.")
            if not isinstance(probabilities, dict) or not isinstance(confidence, (int, float)):
                raise JevProtocolError(f"Choice answer for {qid} is missing probabilities/confidence.")
        elif question["type"] == "score":
            if not isinstance(answer.get("score"), (int, float)):
                raise JevProtocolError(f"Score answer for {qid} is missing a numeric score.")

    return {
        "model": str(payload.get("model") or ""),
        "answers": answers,
        "usage": payload.get("usage") if isinstance(payload.get("usage"), dict) else {},
    }


def system_one(state, questions: dict, *, transport=None) -> dict:
    """Execute one bounded System One request."""
    status = jev_runtime_status()
    if not status["enabled"]:
        raise JevUnavailable("Jev decision provider is disabled.")
    if not status["configured"]:
        raise JevUnavailable("Jev decision provider is enabled but not fully configured.")

    endpoint = _validated_base_url() + "/v1/systemone"
    questions = _validate_questions(questions)
    payload = {"model": status["model"], "state": state, "questions": questions}
    headers = {"Content-Type": "application/json"}
    api_key = str(os.environ.get("ZENDOC_JEV_API_KEY") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    timeout = _env_int("ZENDOC_JEV_TIMEOUT", 4, minimum=1, maximum=10)
    if transport is not None:
        return _validate_response(transport(endpoint, payload, headers, timeout), questions)

    request = Request(
        endpoint,
        data=json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(1_000_000)
    except HTTPError as exc:
        raise JevUnavailable(f"Jev provider returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise JevUnavailable("Jev provider is currently unreachable.") from exc

    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JevProtocolError("Jev provider returned invalid JSON.") from exc
    return _validate_response(decoded, questions)
