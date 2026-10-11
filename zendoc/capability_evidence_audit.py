"""Evidence-gated inventory for the ZENDOC release review.

Software capability labels are not evidence of a live provider, a successful
payment, an authorized clinical action, or a working production deployment.
The audit never sends patient information, invokes external integrations,
auto-approves providers, or changes a capability's execution permissions.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping


GROUP_STATUSES = {
    "merged_current_main_working": "WORKING",
    "merged_current_main_beta": "BETA",
    "external_integration_required": "INTEGRATION_REQUIRED",
    "planned_future_features": "FUTURE",
}

# A connection probe is proof only of its tested boundary. A payment account
# handshake, for example, cannot prove that real money was captured.
EXTERNAL_EVIDENCE_REQUIREMENTS = {
    "community_media_public_durability": ("object_storage", True, "Durable media upload/read/delete and retention review"),
    "affiliate_referral_revenue": (None, True, "Authorized merchant conversion and commission reconciliation"),
    "connected_payments_gateway": ("razorpay", True, "Signed live webhook and human-approved settlement reconciliation"),
    "local_slm": ("ai_runtime", True, "Local inference model and clinical safety evaluation"),
    "cloud_llm": ("ai_runtime", True, "Provider model response, privacy/DPA and safety evaluation"),
    "real_local_model_evaluation": ("ai_runtime", True, "Owner-reviewed evaluation on approved non-patient dataset"),
    "carefin_live_verification": (None, True, "Authorized payer/agency agreement and signed decision evidence"),
    "free_form_translation": (None, True, "Verified language support and safety evaluation"),
    "official_live_connectors": ("official_public_data", True, "Jurisdiction-specific official provenance and licensing"),
    "live_external_fhir_exchange": (None, True, "Partner authorization, consent and two-way FHIR interoperability"),
    "external_ekyc": (None, True, "Authorized identity provider, purpose and consent audit"),
    "external_places_discovery": ("places", True, "Real location accuracy, attribution and rate-limit review"),
    "external_notifications": ("smtp", True, "SMS/WhatsApp/push opt-in and delivery receipts separately"),
    "postgresql": ("database", False, "Durable production PostgreSQL readiness and restoration"),
}

# WORKING is a software claim; it does not by itself certify external/live
# infrastructure or end-to-end patient journeys.
EVIDENCE_TTL = timedelta(hours=24)


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def _fresh_probe(
    result: Mapping[str, Any] | None,
    *,
    now: datetime,
    max_age: timedelta = EVIDENCE_TTL,
) -> bool:
    if not isinstance(result, Mapping) or result.get("status") != "working":
        return False
    stamp = _timestamp(result.get("checked_at"))
    return bool(
        stamp
        and stamp <= now
        and now - stamp <= max_age
        and isinstance(result.get("evidence_code"), str)
        and bool(result["evidence_code"].strip())
    )


def build_capability_evidence_audit(
    manifest: Mapping[str, Any],
    registry: Mapping[str, Mapping[str, Any]],
    *,
    latest_probes: Mapping[str, Mapping[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Audit all capabilities without automatically promoting a single status.

    A recently passing probe is only PARTIAL evidence until specific approval
    requirements are met. Infrastructure can be automatically recognized as
    runtime-verified only when its probe also confirms the required engine.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Audit timestamp must be timezone-aware.")
    now = now.astimezone(timezone.utc)
    categories = manifest.get("feature_classification")
    if not isinstance(categories, Mapping):
        raise ValueError("Capability categories are missing.")

    errors: list[str] = []
    catalog: dict[str, dict[str, Any]] = {}
    actual_counts: Counter[str] = Counter()
    for group, required_status in GROUP_STATUSES.items():
        entries = categories.get(group)
        if not isinstance(entries, list):
            errors.append(f"missing category: {group}")
            continue
        for item in entries:
            if not isinstance(item, Mapping):
                errors.append(f"invalid entry in {group}")
                continue
            key = item.get("key")
            status = item.get("status")
            if not isinstance(key, str) or not key:
                errors.append(f"entry lacks a valid key in {group}")
                continue
            if key in catalog:
                errors.append(f"duplicate capability: {key}")
                continue
            if status != required_status:
                errors.append(f"{key}: expected {required_status}, found {status}")
            actual_counts[status or "MISSING"] += 1
            catalog[key] = {
                "key": key,
                "label": str(item.get("label") or key),
                "baseline_status": status,
                "runtime_status": registry.get(key, {}).get("status", "MISSING"),
                "external_evidence": "NOT_APPLICABLE",
                "required_review": None,
                "probe": None,
            }

    for key in sorted(set(registry) - set(catalog)):
        errors.append(f"registry capability not documented: {key}")
    for key in sorted(set(catalog) - set(registry)):
        errors.append(f"manifest capability missing from registry: {key}")

    summary = manifest.get("summary_metrics", {})
    declared = {
        "total_registered_capabilities": len(catalog),
        "working_capabilities": actual_counts["WORKING"],
        "beta_capabilities": actual_counts["BETA"],
        "integration_required_capabilities": actual_counts["INTEGRATION_REQUIRED"],
        "future_capabilities": actual_counts["FUTURE"],
    }
    for label, real_count in declared.items():
        if summary.get(label) != real_count:
            errors.append(f"manifest {label}: declared {summary.get(label)}, actual {real_count}")

    required_keys = set(EXTERNAL_EVIDENCE_REQUIREMENTS)
    catalog_external = {key for key, row in catalog.items() if row["baseline_status"] == "INTEGRATION_REQUIRED"}
    if catalog_external != required_keys:
        errors.append(
            "External evidence mapping mismatch: "
            f"missing={sorted(catalog_external - required_keys)}, "
            f"extra={sorted(required_keys - catalog_external)}"
        )
    if registry.get("autonomous_prescribing", {}).get("status") not in {"FUTURE", "DISABLED"}:
        errors.append("Autonomous prescribing must remain FUTURE/DISABLED")
    if registry.get("zendoc_proprietary_slm", {}).get("status") != "FUTURE":
        errors.append("Untrained proprietary SLM must remain FUTURE")

    latest_probes = latest_probes or {}
    for key, (probe_key, needs_manual_evidence, required_review) in EXTERNAL_EVIDENCE_REQUIREMENTS.items():
        if key not in catalog:
            continue
        entry = catalog[key]
        entry["probe"] = probe_key
        entry["required_review"] = required_review
        result = latest_probes.get(probe_key) if probe_key else None
        fresh = _fresh_probe(result, now=now)
        entry["external_evidence"] = (
            "PROBE_PASSED_PARTIAL" if fresh else
            "PROBE_NOT_VERIFIED" if probe_key else
            "MANUAL_EVIDENCE_REQUIRED"
        )
        # A successful SQLite readiness probe is *not* PostgreSQL evidence.
        # Production persistence must also be independently confirmed.
        if key == "postgresql" and fresh:
            detail = result.get("detail") if isinstance(result, Mapping) else None
            entry["external_evidence"] = (
                "RUNTIME_VERIFIED" if (
                    isinstance(detail, Mapping)
                    and str(detail.get("engine") or "").lower() in {"postgres", "postgresql"}
                    and detail.get("persistence_verified") is True
                ) else "PROBE_PASSED_PARTIAL"
            )
        if needs_manual_evidence and entry["external_evidence"] == "RUNTIME_VERIFIED":
            entry["external_evidence"] = "PROBE_PASSED_PARTIAL"

    return {
        "status": "INVENTORY_VALID" if not errors else "INVENTORY_INVALID",
        "inventory_errors": errors,
        "counts": declared,
        "external_evidence_counts": dict(Counter(
            catalog[key]["external_evidence"]
            for key in sorted(catalog_external)
            if key in catalog
        )),
        "live_complete": False,  # Requires separate owner-gated release evidence.
        "capabilities": [catalog[key] for key in sorted(catalog)],
        "notice": (
            "Software labels and repository tests are not proof of external-provider "
            "service, clinical authority, live deployment, or successful payments."
        ),
    }
