"""Standardized Prescription Intelligence v2 status projection.

This layer does not re-extract or prescribe. It projects stored prescription
items into explicit safety stages for UI/agent orchestration.
"""
from __future__ import annotations

from typing import Any

from .prescription_service import get_prescription


EXTRACTED = "EXTRACTED"
LOW_CONFIDENCE = "LOW_CONFIDENCE"
AMBIGUOUS = "AMBIGUOUS"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
MATCHED = "MATCHED"
VERIFIED = "VERIFIED"
FULFILMENT_READY = "FULFILMENT_READY"


def prescription_intelligence_state(prescription_id: int, actor: Any = None) -> dict:
    prescription = get_prescription(int(prescription_id), actor=actor)
    projected = [_project_item(item) for item in prescription.get("items", [])]

    if not projected:
        overall = REVIEW_REQUIRED
    elif any(item["stage"] in {LOW_CONFIDENCE, AMBIGUOUS, REVIEW_REQUIRED} for item in projected):
        overall = REVIEW_REQUIRED
    elif all(item["stage"] == FULFILMENT_READY for item in projected):
        overall = FULFILMENT_READY
    elif all(item["stage"] in {VERIFIED, FULFILMENT_READY} for item in projected):
        overall = VERIFIED
    else:
        overall = MATCHED

    return {
        "prescription_id": prescription["id"],
        "overall_stage": overall,
        "needs_review": overall == REVIEW_REQUIRED,
        "fulfilment_ready": overall == FULFILMENT_READY,
        "items": projected,
        "safety": {
            "autonomous_prescribing": False,
            "automatic_substitution": False,
            "automatic_dose_change": False,
            "automatic_frequency_change": False,
            "automatic_form_change": False,
            "automatic_order_submission": False,
        },
    }


def _project_item(item: dict) -> dict:
    confidence = _confidence(item.get("extraction_confidence"))
    review = str(item.get("review_status") or "").strip().lower()
    sku_id = item.get("sku_id")
    medicine_name = str(item.get("medicine_name") or "").strip()

    if not medicine_name:
        stage = AMBIGUOUS
        reason = "Medicine name is empty/ambiguous."
    elif confidence < 0.75:
        stage = LOW_CONFIDENCE
        reason = "Extraction confidence is below the safe review threshold."
    elif review == "item_review_required":
        stage = REVIEW_REQUIRED
        reason = "Stored extraction requires explicit human review."
    elif not sku_id:
        stage = AMBIGUOUS
        reason = "No exact medication SKU is attached; automatic fulfilment is blocked."
    elif review in {"verified", "user_confirmed"}:
        stage = FULFILMENT_READY
        reason = "Exact SKU is attached and review state allows fulfilment staging."
    else:
        stage = MATCHED
        reason = "Exact catalog match exists but final review state is not fulfilment-ready."

    return {
        "item_id": item.get("id"),
        "medicine_name": medicine_name,
        "strength_or_dosage": item.get("dosage"),
        "form": item.get("form"),
        "frequency": item.get("frequency"),
        "extraction_confidence": confidence,
        "review_status": review or None,
        "sku_id": sku_id,
        "stage": stage,
        "reason": reason,
    }


def _confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(number, 1.0))
