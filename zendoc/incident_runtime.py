"""Evidence-gated runtime for ZENDOC AI workforce incident cases.

The controller advances only truthfully evidenced stages. It never edits code,
runs shell/SQL supplied by a model, deploys production, rotates secrets, expands
permissions, moves money, prescribes, or dispatches emergency services.
"""
from __future__ import annotations

import json
from typing import Any

from .ai_workforce import INCIDENT_PIPELINE
from .audit_privacy import redact_operational_text
from .db import get_db, now_iso
from .event_bus import get_event, publish_event
from .security import assert_owner


EVIDENCE_STAGES = {
    "reproduce",
    "root_cause",
    "repair_proposal",
    "security_review",
    "regression_tests",
    "preview_qa",
    "post_release_verify",
}
PREPRODUCTION_STAGES = (
    "detect_and_classify",
    "reproduce",
    "root_cause",
    "repair_proposal",
    "security_review",
    "regression_tests",
    "preview_qa",
    "release_evidence",
)


def _owner_id(actor: Any) -> int:
    if hasattr(actor, "keys") and "id" in actor.keys():
        return int(actor["id"])
    if isinstance(actor, dict):
        return int(actor.get("id") or 0)
    return 0


def _task(task_id: int) -> dict:
    row = get_db().execute("SELECT * FROM agent_tasks WHERE id=?", (int(task_id),)).fetchone()
    if not row:
        raise LookupError(f"Agent task #{task_id} not found.")
    task = dict(row)
    if task.get("task_type") != "ai_workforce_incident":
        raise ValueError("Task is not an AI workforce incident case.")
    return task


def _metadata(task: dict) -> dict:
    try:
        data = json.loads(task.get("metadata_json") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        data = {}
    return data if isinstance(data, dict) else {}


def _pipeline_stage_names() -> list[str]:
    return [str(item["stage"]) for item in INCIDENT_PIPELINE]


def _initial_runtime(task: dict, metadata: dict) -> dict:
    plan = metadata.get("incident_plan") if isinstance(metadata.get("incident_plan"), dict) else {}
    return {
        "version": "incident-runtime-v1",
        "task_id": int(task["id"]),
        "current_stage": "detect_and_classify",
        "stages": {
            stage: {"status": "pending", "updated_at": None}
            for stage in _pipeline_stage_names()
        },
        "source_type": str(plan.get("source_type") or "runtime")[:80],
        "source_event_id": plan.get("source_event_id"),
        "severity": str(plan.get("severity") or "medium")[:20],
        "blocked_stage": None,
        "blocker": None,
        "owner_approval_recorded": False,
        "production_promotion_executed": False,
        "post_release_verified": False,
        "knowledge_record": None,
        "updated_at": now_iso(),
    }


def _save(task_id: int, metadata: dict, runtime: dict, *, status: str | None = None, summary: str | None = None):
    runtime["updated_at"] = now_iso()
    metadata["incident_runtime"] = runtime
    sets = ["metadata_json=?", "updated_at=?"]
    values = [json.dumps(metadata, sort_keys=True, separators=(",", ":")), now_iso()]
    if status is not None:
        sets.append("status=?")
        values.append(status)
        if status in {"completed", "failed", "cancelled"}:
            sets.append("completed_at=?")
            values.append(now_iso())
    if summary is not None:
        sets.append("result_summary=?")
        values.append(redact_operational_text(summary, 300))
    values.append(int(task_id))
    get_db().execute(
        f"UPDATE agent_tasks SET {', '.join(sets)} WHERE id=?",
        tuple(values),
    )
    get_db().commit()


def _stage_event(actor: Any, task_id: int, stage: str, status: str, detail: str = ""):
    publish_event(
        "workforce.incident.stage",
        actor=actor,
        entity_type="agent_task",
        entity_id=str(task_id),
        status=status,
        payload={
            "task_id": int(task_id),
            "stage": stage,
            "detail": redact_operational_text(detail, 240),
        },
        agent_name=next(
            (str(item["agent_id"]) for item in INCIDENT_PIPELINE if item["stage"] == stage),
            "OperationsAgent",
        ),
        idempotency_key=f"workforce-stage:{int(task_id)}:{stage}:{status}",
    )


def _complete_stage(runtime: dict, stage: str, *, summary: str, source_ref: str | None = None, details: dict | None = None):
    record = {
        "status": "completed",
        "summary": redact_operational_text(summary, 500),
        "source_ref": str(source_ref or "")[:300] or None,
        "details": details if isinstance(details, dict) else {},
        "updated_at": now_iso(),
    }
    runtime["stages"][stage] = record
    runtime["blocked_stage"] = None
    runtime["blocker"] = None


def _block_stage(runtime: dict, stage: str, blocker: str, summary: str):
    runtime["stages"][stage] = {
        "status": "blocked",
        "summary": redact_operational_text(summary, 500),
        "source_ref": None,
        "details": {},
        "updated_at": now_iso(),
    }
    runtime["blocked_stage"] = stage
    runtime["blocker"] = str(blocker or "EVIDENCE_REQUIRED")[:80]


def _next_stage(stage: str) -> str | None:
    names = _pipeline_stage_names()
    try:
        index = names.index(stage)
    except ValueError:
        return None
    return names[index + 1] if index + 1 < len(names) else None


def _classification(task: dict, metadata: dict) -> dict:
    plan = metadata.get("incident_plan") if isinstance(metadata.get("incident_plan"), dict) else {}
    source_event_id = plan.get("source_event_id")
    evidence = {
        "severity": str(plan.get("severity") or "medium")[:20],
        "source_type": str(plan.get("source_type") or "runtime")[:80],
        "summary": redact_operational_text(str(plan.get("summary") or "Operational incident"), 500),
    }
    source_ref = None
    if source_event_id:
        try:
            event = get_event(int(source_event_id))
            evidence.update({
                "event_type": str(event.get("event_type") or "")[:120],
                "event_status": str(event.get("status") or "")[:40],
                "event_error": redact_operational_text(str(event.get("error") or ""), 300),
            })
            source_ref = f"platform_event:{int(source_event_id)}"
        except (LookupError, TypeError, ValueError):
            source_ref = f"platform_event:{int(source_event_id)}:missing"
    return {"source_ref": source_ref, "details": evidence}


def _validated_evidence(stage: str, raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise ValueError(f"{stage} evidence must be a JSON object.")
    source_ref = str(raw.get("source_ref") or "").strip()[:300]
    summary = redact_operational_text(str(raw.get("summary") or "").strip(), 500)
    if not source_ref or not summary:
        raise ValueError(f"{stage} evidence requires source_ref and summary.")

    base = {
        "source_ref": source_ref,
        "summary": summary,
        "details": {},
    }

    if stage == "reproduce":
        if raw.get("verified") is not True:
            raise ValueError("Reproduction evidence must be explicitly verified.")
        if raw.get("reproduced") is not True:
            raise ValueError("The incident must be reproduced before root-cause automation can advance.")
        base["details"] = {"verified": True, "reproduced": True}
    elif stage == "root_cause":
        root_cause = redact_operational_text(str(raw.get("root_cause") or "").strip(), 700)
        if raw.get("verified") is not True or not root_cause:
            raise ValueError("Root-cause evidence requires verified=true and a root_cause.")
        base["details"] = {"verified": True, "root_cause": root_cause}
    elif stage == "repair_proposal":
        change_ref = str(raw.get("change_ref") or "").strip()[:300]
        regression_plan = redact_operational_text(str(raw.get("regression_plan") or "").strip(), 700)
        if not change_ref or not regression_plan:
            raise ValueError("Repair proposal evidence requires change_ref and regression_plan.")
        base["details"] = {
            "change_ref": change_ref,
            "regression_plan": regression_plan,
            "production_write_executed_by_runtime": False,
        }
    elif stage in {"security_review", "regression_tests", "preview_qa"}:
        if raw.get("passed") is not True:
            raise ValueError(f"{stage} must explicitly pass before the incident can advance.")
        base["details"] = {"passed": True}
    elif stage == "post_release_verify":
        commit = str(raw.get("deployed_commit") or "").strip()[:80]
        if raw.get("health_ok") is not True or raw.get("ready_ok") is not True or not commit:
            raise ValueError(
                "Post-release verification requires health_ok=true, ready_ok=true and deployed_commit."
            )
        base["details"] = {
            "health_ok": True,
            "ready_ok": True,
            "deployed_commit": commit,
            "deployment_url": str(raw.get("deployment_url") or "").strip()[:300] or None,
        }
    return base


def incident_runtime_snapshot(actor: Any, task_id: int) -> dict:
    assert_owner(actor)
    task = _task(task_id)
    metadata = _metadata(task)
    runtime = metadata.get("incident_runtime")
    if not isinstance(runtime, dict):
        runtime = _initial_runtime(task, metadata)
    return {
        "task_id": int(task["id"]),
        "task_status": task["status"],
        "assigned_agent": task["assigned_agent"],
        "runtime": runtime,
        "safety": {
            "production_promotion_executed": False,
            "arbitrary_execution": False,
            "secret_access": False,
            "permission_expansion": False,
            "clinical_authority": False,
            "payment_authority": False,
            "emergency_dispatch_authority": False,
        },
    }


def list_incident_runtimes(actor: Any, *, limit: int = 50) -> list[dict]:
    assert_owner(actor)
    limit = max(1, min(int(limit or 50), 200))
    rows = get_db().execute(
        """
        SELECT id FROM agent_tasks
        WHERE task_type='ai_workforce_incident'
        ORDER BY updated_at DESC,id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [incident_runtime_snapshot(actor, int(row["id"])) for row in rows]


def advance_incident_case(actor: Any, task_id: int, *, evidence: dict | None = None) -> dict:
    """Advance an incident only through stages with truthful evidence.

    The function can automatically classify a case and assemble release evidence.
    It cannot create proof for reproduction, root cause, security, tests, preview,
    production approval, or post-release health.
    """
    assert_owner(actor)
    task = _task(task_id)
    metadata = _metadata(task)
    runtime = metadata.get("incident_runtime")
    if not isinstance(runtime, dict):
        runtime = _initial_runtime(task, metadata)
    evidence = evidence if isinstance(evidence, dict) else {}

    while True:
        stage = str(runtime.get("current_stage") or "detect_and_classify")

        if stage == "detect_and_classify":
            classified = _classification(task, metadata)
            _complete_stage(
                runtime,
                stage,
                summary="Incident classified from privacy-safe operational metadata.",
                source_ref=classified["source_ref"],
                details=classified["details"],
            )
            _stage_event(actor, int(task_id), stage, "completed", "Privacy-safe incident classification recorded.")
            runtime["current_stage"] = _next_stage(stage)
            continue

        if stage in {"reproduce", "root_cause", "repair_proposal", "security_review", "regression_tests", "preview_qa"}:
            raw = evidence.get(stage)
            if raw is None:
                _block_stage(
                    runtime,
                    stage,
                    "EVIDENCE_REQUIRED",
                    f"{stage.replace('_', ' ').title()} requires external/sandbox evidence before this case can advance.",
                )
                _save(
                    int(task_id),
                    metadata,
                    runtime,
                    status="waiting_human",
                    summary=f"Incident waiting for {stage.replace('_', ' ')} evidence.",
                )
                _stage_event(actor, int(task_id), stage, "waiting_human", "Evidence required; no success fabricated.")
                return incident_runtime_snapshot(actor, int(task_id))
            validated = _validated_evidence(stage, raw)
            _complete_stage(
                runtime,
                stage,
                summary=validated["summary"],
                source_ref=validated["source_ref"],
                details=validated["details"],
            )
            _stage_event(actor, int(task_id), stage, "completed", validated["summary"])
            runtime["current_stage"] = _next_stage(stage)
            continue

        if stage == "release_evidence":
            evidence_refs = []
            for prior in PREPRODUCTION_STAGES:
                row = runtime["stages"].get(prior) or {}
                if row.get("source_ref"):
                    evidence_refs.append(row["source_ref"])
            _complete_stage(
                runtime,
                stage,
                summary="Pre-production incident evidence bundle assembled; production remains owner-gated.",
                source_ref=f"incident-runtime:{int(task_id)}:release-evidence",
                details={
                    "evidence_refs": evidence_refs,
                    "production_approval_required": True,
                    "production_promotion_executed": False,
                },
            )
            _stage_event(actor, int(task_id), stage, "completed", "Release evidence assembled without deployment.")
            runtime["current_stage"] = "production_approval"
            _save(
                int(task_id),
                metadata,
                runtime,
                status="waiting_approval",
                summary="Pre-production evidence complete; explicit owner production approval is required.",
            )
            return incident_runtime_snapshot(actor, int(task_id))

        if stage == "production_approval":
            _block_stage(
                runtime,
                stage,
                "OWNER_APPROVAL_REQUIRED",
                "Production promotion cannot be approved or executed by the incident runtime.",
            )
            _save(
                int(task_id),
                metadata,
                runtime,
                status="waiting_approval",
                summary="Incident waiting for explicit owner production approval.",
            )
            return incident_runtime_snapshot(actor, int(task_id))

        if stage == "post_release_verify":
            raw = evidence.get(stage)
            if raw is None:
                _block_stage(
                    runtime,
                    stage,
                    "LIVE_HEALTH_EVIDENCE_REQUIRED",
                    "Post-release closure requires live /health and /ready evidence for the deployed commit.",
                )
                _save(
                    int(task_id),
                    metadata,
                    runtime,
                    status="waiting_human",
                    summary="Incident waiting for live post-release health verification.",
                )
                return incident_runtime_snapshot(actor, int(task_id))
            validated = _validated_evidence(stage, raw)
            _complete_stage(
                runtime,
                stage,
                summary=validated["summary"],
                source_ref=validated["source_ref"],
                details=validated["details"],
            )
            runtime["post_release_verified"] = True
            _stage_event(actor, int(task_id), stage, "completed", validated["summary"])
            runtime["current_stage"] = "knowledge_capture"
            continue

        if stage == "knowledge_capture":
            root = runtime["stages"].get("root_cause") or {}
            repair = runtime["stages"].get("repair_proposal") or {}
            verify = runtime["stages"].get("post_release_verify") or {}
            runtime["knowledge_record"] = {
                "incident_task_id": int(task_id),
                "root_cause_summary": redact_operational_text(
                    str((root.get("details") or {}).get("root_cause") or root.get("summary") or ""),
                    500,
                ),
                "repair_reference": str((repair.get("details") or {}).get("change_ref") or "")[:300] or None,
                "post_release_reference": verify.get("source_ref"),
                "captured_at": now_iso(),
                "contains_raw_health_content": False,
                "contains_secrets": False,
            }
            _complete_stage(
                runtime,
                stage,
                summary="Sanitized incident learning captured after verified post-release health.",
                source_ref=f"incident-runtime:{int(task_id)}:knowledge",
                details={"sanitized_metadata_only": True},
            )
            runtime["current_stage"] = None
            _save(
                int(task_id),
                metadata,
                runtime,
                status="completed",
                summary="Incident closed after evidence-gated post-release verification.",
            )
            _stage_event(actor, int(task_id), stage, "completed", "Sanitized knowledge record captured.")
            return incident_runtime_snapshot(actor, int(task_id))

        raise ValueError(f"Unsupported incident runtime stage: {stage}")


def record_owner_production_approval(actor: Any, task_id: int, *, approval_reference: str) -> dict:
    """Record owner approval only; this function never performs a deployment."""
    assert_owner(actor)
    task = _task(task_id)
    metadata = _metadata(task)
    runtime = metadata.get("incident_runtime")
    if not isinstance(runtime, dict):
        raise ValueError("Incident runtime has not reached a production approval gate.")
    if runtime.get("current_stage") != "production_approval":
        raise ValueError("Incident is not waiting at the production approval stage.")
    reference = str(approval_reference or "").strip()[:300]
    if not reference:
        raise ValueError("approval_reference is required.")

    _complete_stage(
        runtime,
        "production_approval",
        summary="Configured owner approval recorded. Deployment/promotion must occur through the external release workflow.",
        source_ref=reference,
        details={
            "approved_by": _owner_id(actor),
            "approved_at": now_iso(),
            "production_promotion_executed_by_runtime": False,
        },
    )
    runtime["owner_approval_recorded"] = True
    runtime["production_promotion_executed"] = False
    runtime["current_stage"] = "post_release_verify"
    _save(
        int(task_id),
        metadata,
        runtime,
        status="waiting_human",
        summary="Owner approval recorded; waiting for external deployment and live health verification.",
    )
    _stage_event(actor, int(task_id), "production_approval", "completed", "Owner approval recorded; no deployment executed.")
    return incident_runtime_snapshot(actor, int(task_id))


def advance_new_incident_cases(actor: Any, *, limit: int = 25) -> dict:
    """Automatically classify newly queued incidents and stop at the first evidence gate."""
    assert_owner(actor)
    limit = max(1, min(int(limit or 25), 100))
    rows = get_db().execute(
        """
        SELECT id FROM agent_tasks
        WHERE task_type='ai_workforce_incident' AND status='queued'
        ORDER BY created_at ASC,id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    advanced = []
    errors = []
    for row in rows:
        try:
            snapshot = advance_incident_case(actor, int(row["id"]))
            advanced.append({
                "task_id": int(row["id"]),
                "task_status": snapshot["task_status"],
                "current_stage": snapshot["runtime"].get("current_stage"),
                "blocker": snapshot["runtime"].get("blocker"),
            })
        except (LookupError, PermissionError, TypeError, ValueError) as exc:
            errors.append({"task_id": int(row["id"]), "error": redact_operational_text(str(exc), 300)})
    return {
        "status": "completed",
        "advanced_count": len(advanced),
        "advanced": advanced,
        "errors": errors,
        "production_promotions_executed": 0,
    }
