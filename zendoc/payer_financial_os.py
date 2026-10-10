"""
ZENDOC Payer & Financial OS — Phase G.

Manages insurance coverage verification requests, prior authorization workflows,
and non-binding benefit cost estimation.

TRUTHFUL STATUS MODEL:
- Insurance coverage verification requests are SUBMITTED to payer — responses are
  NEVER fabricated. Status stays PENDING_VERIFICATION until a real payer response
  arrives (BLOCKED_EXTERNAL).
- Prior authorization decisions are never auto-generated. Status stays SUBMITTED
  until a payer decision is recorded manually or via payer API integration.
- Benefit estimations are ALWAYS labelled NON_BINDING with full disclaimer.
- ZENDOC never approves or denies insurance claims autonomously.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from .db import get_db, now_iso


# ── Authorization helper ────────────────────────────────────────────────────

def _actor_id(actor: Any) -> int:
    if isinstance(actor, (int, float)):
        return int(actor)
    if isinstance(actor, dict):
        return int(actor.get("id") or 0)
    try:
        return int(actor["id"] or 0)
    except (TypeError, KeyError, IndexError):
        pass
    return int(getattr(actor, "id", 0) or 0)


def _actor_field(actor: Any, field: str, default: Any = None) -> Any:
    if isinstance(actor, dict):
        return actor.get(field, default)
    try:
        val = actor[field]
        return val if val is not None else default
    except (TypeError, KeyError, IndexError):
        pass
    return getattr(actor, field, default)


def _require_role(actor: Any, allowed: set) -> None:
    role = _actor_field(actor, "role", "")
    if role not in allowed:
        raise PermissionError(f"Role '{role}' is not authorized for this Payer OS operation.")


# ── Coverage Verification ────────────────────────────────────────────────────

COVERAGE_TYPES = {
    "outpatient", "inpatient", "emergency", "diagnostics",
    "pharmacy", "maternity", "mental_health", "dental", "vision", "other",
}

ALLOWED_CLAIM_ROLES = {"patient", "doctor", "admin", "hospital"}


def submit_coverage_verification_request(
    actor: Any,
    patient_id: int,
    insurer_name: str,
    coverage_type: str,
    service_type: str,
    policy_number: str | None = None,
    estimated_cost_inr: float | None = None,
) -> dict[str, Any]:
    """
    Submit an insurance coverage verification request.

    WORKING: Request is recorded and queued.
    BLOCKED_EXTERNAL: Actual insurer verification requires external payer API
    integration which is NOT connected. Status stays PENDING_VERIFICATION.
    """
    _require_role(actor, ALLOWED_CLAIM_ROLES)
    actor_id = _actor_id(actor)
    if not actor_id:
        raise PermissionError("Authentication required.")

    coverage_type = str(coverage_type or "").strip().lower()
    if coverage_type not in COVERAGE_TYPES:
        raise ValueError(f"coverage_type must be one of: {sorted(COVERAGE_TYPES)}")

    insurer_name = str(insurer_name or "").strip()
    service_type = str(service_type or "").strip()
    if not insurer_name or not service_type:
        raise ValueError("insurer_name and service_type are required.")

    db = get_db()
    patient = db.execute(
        "SELECT id, name FROM users WHERE id=? AND role='patient' AND active=1",
        (patient_id,),
    ).fetchone()
    if not patient:
        raise LookupError("Patient not found.")

    request_uid = str(uuid.uuid4())
    now = now_iso()

    db.execute(
        """
        INSERT INTO insurance_coverage_requests
        (request_uid, patient_id, insurer_name, policy_number, coverage_type,
         service_type, estimated_cost_inr, requested_by, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING_VERIFICATION', ?, ?)
        """,
        (request_uid, patient_id, insurer_name, policy_number, coverage_type,
         service_type, estimated_cost_inr, actor_id, now, now),
    )
    db.commit()

    return {
        "request_uid": request_uid,
        "patient_id": patient_id,
        "insurer_name": insurer_name,
        "coverage_type": coverage_type,
        "service_type": service_type,
        "policy_number": policy_number,
        "estimated_cost_inr": estimated_cost_inr,
        "status": "PENDING_VERIFICATION",
        "integration_status": "BLOCKED_EXTERNAL",
        "integration_note": (
            "Actual insurer verification requires a live payer API integration "
            "which is not yet connected. This request is recorded and queued for "
            "manual or API-driven follow-up."
        ),
        "created_at": now,
    }


def list_coverage_requests(actor: Any, patient_id: int) -> list[dict]:
    """List all insurance coverage verification requests for a patient."""
    _require_role(actor, ALLOWED_CLAIM_ROLES)
    actor_role = _actor_field(actor, "role", "")
    actor_id_val = _actor_id(actor)

    # Patients can only see their own requests
    if actor_role == "patient" and actor_id_val != patient_id:
        raise PermissionError("You can only view your own coverage requests.")

    db = get_db()
    rows = db.execute(
        """
        SELECT * FROM insurance_coverage_requests
        WHERE patient_id=? ORDER BY created_at DESC
        """,
        (patient_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def update_coverage_request_status(
    actor: Any,
    request_uid: str,
    new_status: str,
    verification_notes: str | None = None,
    response_data: dict | None = None,
) -> dict[str, Any]:
    """
    Record an insurer response for a coverage verification request.
    Only admin/doctor/hospital can update status.
    """
    _require_role(actor, {"admin", "doctor", "hospital"})
    valid_statuses = {
        "PENDING_VERIFICATION", "VERIFIED_COVERED", "VERIFIED_NOT_COVERED",
        "PARTIAL_COVERAGE", "VERIFICATION_FAILED", "CANCELLED",
    }
    if new_status not in valid_statuses:
        raise ValueError(f"status must be one of: {sorted(valid_statuses)}")

    db = get_db()
    row = db.execute(
        "SELECT * FROM insurance_coverage_requests WHERE request_uid=?",
        (request_uid,),
    ).fetchone()
    if not row:
        raise LookupError("Coverage request not found.")

    now = now_iso()
    db.execute(
        """
        UPDATE insurance_coverage_requests
        SET status=?, verification_notes=?, response_json=?, updated_at=?
        WHERE request_uid=?
        """,
        (
            new_status,
            verification_notes,
            json.dumps(response_data) if response_data else None,
            now,
            request_uid,
        ),
    )
    db.commit()

    return {
        "request_uid": request_uid,
        "status": new_status,
        "verification_notes": verification_notes,
        "updated_at": now,
        "truthful_status_note": (
            "Status updated by ZENDOC operator. Verified status reflects what was "
            "recorded from the insurer — not an autonomous ZENDOC determination."
        ),
    }


# ── Prior Authorization ─────────────────────────────────────────────────────

PRIOR_AUTH_ALLOWED_ROLES = {"doctor", "admin", "hospital"}


def submit_prior_authorization(
    actor: Any,
    patient_id: int,
    insurer_name: str,
    treatment_type: str,
    policy_number: str | None = None,
    icd10_codes: list[str] | None = None,
    cpt_codes: list[str] | None = None,
    requesting_provider: str | None = None,
    clinical_notes: str | None = None,
) -> dict[str, Any]:
    """
    Record and submit a prior authorization request.

    WORKING: Request metadata recorded.
    BLOCKED_EXTERNAL: Actual payer submission requires external payer API or
    manual submission. ZENDOC never auto-approves prior auth.
    """
    _require_role(actor, PRIOR_AUTH_ALLOWED_ROLES)
    actor_id_val = _actor_id(actor)

    insurer_name = str(insurer_name or "").strip()
    treatment_type = str(treatment_type or "").strip()
    if not insurer_name or not treatment_type:
        raise ValueError("insurer_name and treatment_type are required.")

    db = get_db()
    patient = db.execute(
        "SELECT id, name FROM users WHERE id=? AND role='patient' AND active=1",
        (patient_id,),
    ).fetchone()
    if not patient:
        raise LookupError("Patient not found.")

    request_uid = str(uuid.uuid4())
    now = now_iso()

    db.execute(
        """
        INSERT INTO prior_authorization_requests
        (request_uid, patient_id, insurer_name, policy_number, treatment_type,
         icd10_codes, cpt_codes, requesting_provider, clinical_notes,
         status, submitted_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'SUBMITTED', ?, ?, ?)
        """,
        (
            request_uid, patient_id, insurer_name, policy_number, treatment_type,
            json.dumps(icd10_codes or []),
            json.dumps(cpt_codes or []),
            requesting_provider, clinical_notes,
            now, now, now,
        ),
    )
    db.commit()

    return {
        "request_uid": request_uid,
        "patient_id": patient_id,
        "insurer_name": insurer_name,
        "treatment_type": treatment_type,
        "status": "SUBMITTED",
        "integration_status": "BLOCKED_EXTERNAL",
        "integration_note": (
            "Prior authorization requires live payer connectivity. "
            "This request has been recorded and must be submitted manually or via "
            "the insurer's provider portal. ZENDOC never auto-approves authorization."
        ),
        "submitted_at": now,
    }


def record_prior_auth_decision(
    actor: Any,
    request_uid: str,
    decision: str,
    payer_response: str | None = None,
    payer_auth_number: str | None = None,
) -> dict[str, Any]:
    """Record insurer decision on a prior authorization request."""
    _require_role(actor, {"admin", "doctor", "hospital"})
    valid_decisions = {"APPROVED", "DENIED", "PARTIAL_APPROVAL", "MORE_INFO_REQUIRED", "CANCELLED"}
    if decision not in valid_decisions:
        raise ValueError(f"decision must be one of: {sorted(valid_decisions)}")

    db = get_db()
    row = db.execute(
        "SELECT * FROM prior_authorization_requests WHERE request_uid=?",
        (request_uid,),
    ).fetchone()
    if not row:
        raise LookupError("Prior authorization request not found.")

    now = now_iso()
    db.execute(
        """
        UPDATE prior_authorization_requests
        SET status=?, payer_response=?, payer_auth_number=?, decided_at=?, updated_at=?
        WHERE request_uid=?
        """,
        (decision, payer_response, payer_auth_number, now, now, request_uid),
    )
    db.commit()

    return {
        "request_uid": request_uid,
        "decision": decision,
        "payer_auth_number": payer_auth_number,
        "decided_at": now,
        "truthful_status_note": (
            "Decision recorded from payer/operator. ZENDOC never autonomously approves or "
            "denies prior authorization. All decisions come from the insurer."
        ),
    }


def list_prior_authorizations(actor: Any, patient_id: int) -> list[dict]:
    """List prior authorization requests for a patient."""
    _require_role(actor, ALLOWED_CLAIM_ROLES)
    actor_role = _actor_field(actor, "role", "")
    actor_id_val = _actor_id(actor)
    if actor_role == "patient" and actor_id_val != patient_id:
        raise PermissionError("You can only view your own prior authorization requests.")

    db = get_db()
    rows = db.execute(
        "SELECT * FROM prior_authorization_requests WHERE patient_id=? ORDER BY created_at DESC",
        (patient_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Non-Binding Benefit Estimation ──────────────────────────────────────────

NON_BINDING_DISCLAIMER = (
    "This is a non-binding estimate only. Actual amounts depend on your "
    "specific insurance policy, insurer verification, applicable deductibles, "
    "co-insurance, and out-of-pocket maximums. ZENDOC does not guarantee, "
    "approve, or represent any insurance benefit or claim."
)


def estimate_patient_benefit(
    actor: Any,
    patient_id: int,
    service_type: str,
    estimated_cost_inr: float,
    estimated_coverage_pct: float | None = None,
    calculation_basis: str = "ILLUSTRATIVE_EXAMPLE",
) -> dict[str, Any]:
    """
    Generate a non-binding benefit cost estimate.

    ALWAYS NON_BINDING. Never represents actual insurer approval or commitment.
    """
    _require_role(actor, ALLOWED_CLAIM_ROLES)

    service_type = str(service_type or "").strip()
    if not service_type:
        raise ValueError("service_type is required.")
    if estimated_cost_inr is None or estimated_cost_inr < 0:
        raise ValueError("estimated_cost_inr must be a non-negative number.")

    coverage_pct = min(max(float(estimated_coverage_pct or 0), 0.0), 100.0)
    coverage_inr = round((coverage_pct / 100.0) * estimated_cost_inr, 2)
    out_of_pocket = round(estimated_cost_inr - coverage_inr, 2)

    db = get_db()
    now = now_iso()
    db.execute(
        """
        INSERT INTO benefit_estimation_records
        (patient_id, service_type, estimated_cost_inr, estimated_coverage_pct,
         estimated_out_of_pocket_inr, calculation_basis, is_binding, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?)
        """,
        (patient_id, service_type, estimated_cost_inr, coverage_pct,
         out_of_pocket, calculation_basis, now),
    )
    db.commit()

    return {
        "patient_id": patient_id,
        "service_type": service_type,
        "estimated_cost_inr": estimated_cost_inr,
        "estimated_coverage_pct": coverage_pct,
        "estimated_coverage_inr": coverage_inr,
        "estimated_out_of_pocket_inr": out_of_pocket,
        "calculation_basis": calculation_basis,
        "is_binding": False,
        "non_binding_disclaimer": NON_BINDING_DISCLAIMER,
        "created_at": now,
    }
