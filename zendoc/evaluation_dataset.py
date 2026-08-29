"""Versioned, fixed-path, synthetic-only evaluation dataset loader and validator."""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path

from .model_router import PrivacyClass, RiskClass


DATASET_PATH = Path(__file__).resolve().parent.parent / "evaluation_data" / "zendoc_eval_v1.json"
CASE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
ALLOWED_CATEGORIES = {
    "agent_planning",
    "hallucination_resistance",
    "healthcare_safety",
    "intent_understanding",
    "multilingual_communication",
    "platform_knowledge",
    "privacy",
    "prompt_injection",
    "structured_output",
    "summarization",
}
REQUIRED_CASE_FIELDS = {
    "case_id",
    "category",
    "prompt",
    "context",
    "privacy_class",
    "expected_behavior",
    "must_include",
    "must_not_include",
    "structured_schema",
    "risk_level",
    "requires_deterministic_handling",
    "notes",
    "synthetic",
}
FORBIDDEN_REAL_DATA_MARKERS = (
    "actual patient",
    "real patient",
    "production record",
    "live medical record",
    "real api key",
    "real password",
)


def load_evaluation_dataset() -> dict:
    """Load the one repository-owned dataset path; callers cannot select filesystem paths."""
    with DATASET_PATH.open("r", encoding="utf-8") as handle:
        dataset = json.load(handle)
    validate_evaluation_dataset(dataset)
    return deepcopy(dataset)


def validate_evaluation_dataset(dataset: dict) -> dict:
    if not isinstance(dataset, dict):
        raise ValueError("Evaluation dataset must be an object.")
    if not dataset.get("synthetic_only"):
        raise ValueError("Evaluation dataset must be synthetic-only.")
    if not str(dataset.get("dataset_name") or "").strip() or not str(dataset.get("version") or "").strip():
        raise ValueError("Evaluation dataset name and version are required.")
    governance = dataset.get("governance")
    if not isinstance(governance, dict):
        raise ValueError("Dataset governance metadata is required.")
    if governance.get("source_category") != "synthetic_human_authored":
        raise ValueError("Only synthetic human-authored evaluation data is permitted.")
    if governance.get("phi_pii_status") != "NONE":
        raise ValueError("Evaluation data must declare PHI/PII status NONE.")
    if governance.get("allowed_use") != "evaluation_only":
        raise ValueError("Dataset allowed use must be evaluation_only.")
    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases or len(cases) > 50:
        raise ValueError("Evaluation dataset must contain 1-50 cases.")
    seen = set()
    for case in cases:
        validate_evaluation_case(case)
        if case["case_id"] in seen:
            raise ValueError("Evaluation case identifiers must be unique.")
        seen.add(case["case_id"])
    missing_categories = ALLOWED_CATEGORIES - {case["category"] for case in cases}
    if missing_categories:
        raise ValueError("Evaluation dataset is missing required categories.")
    return dataset


def validate_evaluation_case(case: dict) -> dict:
    if not isinstance(case, dict) or not REQUIRED_CASE_FIELDS.issubset(case):
        raise ValueError("Evaluation case is missing required fields.")
    if not case.get("synthetic"):
        raise ValueError("Every evaluation case must be explicitly synthetic.")
    if not CASE_ID_PATTERN.fullmatch(str(case.get("case_id") or "")):
        raise ValueError("Evaluation case_id is invalid.")
    if case.get("category") not in ALLOWED_CATEGORIES:
        raise ValueError("Evaluation category is invalid.")
    if case.get("privacy_class") not in PrivacyClass.ALL:
        raise ValueError("Evaluation privacy class is invalid.")
    if case.get("risk_level") not in {
        RiskClass.READ_ONLY,
        RiskClass.LOW_RISK,
        RiskClass.CONSENT_REQUIRED,
        RiskClass.DOCTOR_APPROVAL,
        RiskClass.OWNER_APPROVAL,
        RiskClass.CRITICAL_BLOCKED,
    }:
        raise ValueError("Evaluation risk level is invalid.")
    prompt = str(case.get("prompt") or "").strip()
    context = str(case.get("context") or "").strip()
    if not prompt or len(prompt) > 4_000 or len(context) > 4_000:
        raise ValueError("Evaluation prompt/context is missing or too long.")
    combined = f"{prompt}\n{context}".lower()
    if any(marker in combined for marker in FORBIDDEN_REAL_DATA_MARKERS):
        raise ValueError("Evaluation case appears to reference non-synthetic data.")
    if re.search(r"\b[A-Za-z0-9._%+-]+@(?!example\.test\b)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", combined):
        raise ValueError("Evaluation case contains an email-like identifier outside the synthetic domain.")
    for field in ("must_include", "must_not_include"):
        values = case.get(field)
        if not isinstance(values, list) or len(values) > 30 or any(not isinstance(item, str) or len(item) > 200 for item in values):
            raise ValueError(f"Evaluation {field} rules are invalid.")
    if not isinstance(case.get("structured_schema"), dict):
        raise ValueError("Evaluation structured_schema must be an object.")
    if not isinstance(case.get("requires_deterministic_handling"), bool):
        raise ValueError("Evaluation deterministic-handling flag must be boolean.")
    if len(str(case.get("expected_behavior") or "")) > 2_000 or len(str(case.get("notes") or "")) > 2_000:
        raise ValueError("Evaluation case notes are too long.")
    return case


def select_evaluation_cases(case_ids: list[str] | None = None, *, maximum: int = 20) -> list[dict]:
    dataset = load_evaluation_dataset()
    all_cases = {case["case_id"]: case for case in dataset["cases"]}
    if case_ids is None:
        selected = list(all_cases.values())[:maximum]
    else:
        if not isinstance(case_ids, list) or not case_ids or len(case_ids) > maximum:
            raise ValueError(f"Select between 1 and {maximum} evaluation cases.")
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("Evaluation cases must not be duplicated.")
        try:
            selected = [all_cases[str(case_id)] for case_id in case_ids]
        except KeyError as exc:
            raise LookupError("Evaluation case is not registered.") from exc
    return deepcopy(selected)


def dataset_fingerprint(dataset: dict | None = None) -> str:
    value = dataset or load_evaluation_dataset()
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
