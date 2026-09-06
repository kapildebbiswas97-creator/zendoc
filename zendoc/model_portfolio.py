"""ZENDOC model portfolio and routing policy.

This registry is intentionally capability-based, not hype-based. Exact model
names are configuration, because vendors and versions change. ZENDOC selects a
provider by task, privacy, cost and availability; deterministic logic remains
authoritative for emergency/safety and consequential actions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ModelRole:
    role_id: str
    purpose: str
    preferred_provider_classes: tuple[str, ...]
    local_first: bool
    cloud_allowed: bool
    health_sensitive_cloud_allowed: bool
    max_cost_tier: str
    tasks: tuple[str, ...]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["preferred_provider_classes"] = list(self.preferred_provider_classes)
        data["tasks"] = list(self.tasks)
        return data


MODEL_ROLES: tuple[ModelRole, ...] = (
    ModelRole(
        "safety",
        "Emergency triage and hard policy gates.",
        ("deterministic",),
        True,
        False,
        False,
        "FREE",
        ("emergency", "prescribing_block", "permission_gate", "consent_gate"),
    ),
    ModelRole(
        "fast_router",
        "Intent classification, query rewriting and lightweight orchestration.",
        ("local_open_weight", "small_cloud_llm", "deterministic"),
        True,
        True,
        False,
        "LOW",
        ("intent_classification", "query_rewrite", "navigation", "entity_resolution"),
    ),
    ModelRole(
        "private_assistant",
        "Summaries of user-authorized sensitive health context.",
        ("local_open_weight", "deterministic"),
        True,
        False,
        False,
        "LOW",
        ("health_summary", "record_organization", "private_context_explanation"),
    ),
    ModelRole(
        "reasoning_planner",
        "Complex but non-authoritative planning and explanation.",
        ("strong_cloud_llm", "local_open_weight"),
        False,
        True,
        False,
        "MEDIUM",
        ("care_plan_explanation", "multi_step_planning", "benefits_explanation", "provider_comparison"),
    ),
    ModelRole(
        "document_extractor",
        "Structured extraction from uploaded records with confidence scoring.",
        ("vision_document_model", "local_open_weight", "strong_cloud_llm"),
        True,
        True,
        False,
        "MEDIUM",
        ("ocr_assisted_extraction", "structured_record_extraction", "prescription_item_extraction"),
    ),
    ModelRole(
        "multilingual",
        "Translate and explain healthcare navigation across Indian languages.",
        ("multilingual_local_model", "strong_cloud_llm"),
        True,
        True,
        False,
        "MEDIUM",
        ("translation", "plain_language_explanation", "multilingual_navigation"),
    ),
    ModelRole(
        "coding_ops",
        "Owner-only development and operational assistance; never patient-facing authority.",
        ("coding_model", "strong_cloud_llm", "local_open_weight"),
        False,
        True,
        False,
        "MEDIUM",
        ("code_review", "test_generation", "log_summary", "incident_assistance"),
    ),
)


def list_model_roles() -> list[dict]:
    return [role.to_dict() for role in MODEL_ROLES]


def get_model_role(role_id: str) -> dict | None:
    normalized = str(role_id or "").strip().lower()
    for role in MODEL_ROLES:
        if role.role_id == normalized:
            return role.to_dict()
    return None


def route_policy(
    *,
    role_id: str,
    privacy_class: str,
    cloud_consent: bool = False,
) -> dict:
    role = get_model_role(role_id)
    if not role:
        return {"allowed": False, "reason": "unknown_model_role"}

    privacy = str(privacy_class or "INTERNAL").strip().upper()
    sensitive = privacy in {"HEALTH_SENSITIVE", "HIGH_RISK"}

    if sensitive and not role["health_sensitive_cloud_allowed"]:
        return {
            "allowed": True,
            "cloud_allowed": False,
            "local_first": True,
            "reason": "sensitive_local_or_deterministic_only",
        }

    cloud_allowed = bool(role["cloud_allowed"] and (cloud_consent or privacy in {"PUBLIC", "INTERNAL"}))
    return {
        "allowed": True,
        "cloud_allowed": cloud_allowed,
        "local_first": bool(role["local_first"]),
        "reason": "policy_evaluated",
    }
