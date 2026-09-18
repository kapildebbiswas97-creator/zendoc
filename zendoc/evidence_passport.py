"""Truthful AI evidence/provenance passports for recorded ZENDOC interactions."""
from __future__ import annotations

from .db import get_db

PASSPORT_VERSION = "zendoc-ai-evidence-passport-v1"
PROHIBITED_ACTIONS = (
    "autonomous diagnosis",
    "autonomous prescription",
    "claiming emergency dispatch without a real integration",
    "changing medical records without authorization",
    "inventing source citations or clinical evidence",
)


def _value(actor, key, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    if isinstance(actor, dict):
        return actor.get(key, default)
    return default


def _patient_id(actor):
    if str(_value(actor, "role", "")) != "patient":
        raise PermissionError("AI Evidence Passports are available to the patient who owns the interaction.")
    user_id = int(_value(actor, "id", 0) or 0)
    if not user_id:
        raise PermissionError("Authentication is required.")
    return user_id


def _passport(row):
    item = dict(row)
    return {
        "passport_version": PASSPORT_VERSION,
        "interaction_id": int(item["id"]),
        "conversation_id": item.get("conversation_id"),
        "feature": item.get("feature"),
        "intent": item.get("intent"),
        "created_at": item.get("created_at"),
        "risk_level": item.get("risk_level") or "not_recorded",
        "emergency": bool(item.get("emergency")),
        "success": bool(item.get("success")),
        "latency_ms": item.get("latency_ms"),
        "generation": {
            "model_version": item.get("model_version") or "not_recorded",
            "provider": item.get("provider") or "not_recorded",
        },
        "patient_data_used": {
            "recorded": ["current user message"],
            "notice": (
                "The historical interaction log does not prove that any additional Health Memory context was used, "
                "so ZENDOC does not claim it here."
            ),
        },
        "source_level_evidence": {
            "status": "not_recorded",
            "sources": [],
            "notice": (
                "This historical interaction record does not contain source-level citations. "
                "ZENDOC will not invent citations after the fact."
            ),
        },
        "uncertainty": {
            "status": "not_calibrated",
            "notice": "No calibrated confidence score is stored for this historical interaction.",
        },
        "human_review": {
            "state": "not_recorded",
            "notice": (
                "The interaction log does not record a clinician review state unless another workflow explicitly stores one."
            ),
        },
        "policy": {
            "prohibited_actions": list(PROHIBITED_ACTIONS),
            "human_confirmation_required_for_real_world_actions": True,
        },
    }


def list_evidence_passports(actor, limit=25):
    patient_id = _patient_id(actor)
    try:
        limit = max(1, min(int(limit or 25), 100))
    except (TypeError, ValueError):
        limit = 25
    rows = get_db().execute(
        """SELECT id,user_id,conversation_id,feature,intent,risk_level,model_version,
                  provider,emergency,success,latency_ms,created_at
           FROM ai_interactions WHERE user_id=?
           ORDER BY created_at DESC,id DESC LIMIT ?""",
        (patient_id, limit),
    ).fetchall()
    return [_passport(row) for row in rows]


def get_evidence_passport(actor, interaction_id):
    patient_id = _patient_id(actor)
    row = get_db().execute(
        """SELECT id,user_id,conversation_id,feature,intent,risk_level,model_version,
                  provider,emergency,success,latency_ms,created_at
           FROM ai_interactions WHERE id=? AND user_id=?""",
        (int(interaction_id), patient_id),
    ).fetchone()
    if not row:
        raise LookupError("AI interaction not found.")
    return _passport(row)
