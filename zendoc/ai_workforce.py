"""Bounded AI-company workforce for ZENDOC reliability and product operations.

The workforce converts privacy-safe failure events into persistent incident
cases and assigns responsibility across named AI roles. It may automatically
triage, research, reproduce in a sandbox, prepare repair proposals, run tests
and verify read-only evidence. It cannot silently modify production, broaden
permissions, move money, prescribe, dispatch emergencies, or expose secrets.

Production code promotion remains an explicit owner/release gate.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any

from .agent_task_engine import create_agent_task
from .audit_privacy import redact_operational_text
from .db import get_db
from .event_bus import publish_event
from .security import assert_owner


@dataclass(frozen=True)
class WorkforceAgent:
    agent_id: str
    mission: str
    automation_level: str
    outputs: tuple[str, ...]
    human_gates: tuple[str, ...]
    forbidden: tuple[str, ...]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["outputs"] = list(self.outputs)
        data["human_gates"] = list(self.human_gates)
        data["forbidden"] = list(self.forbidden)
        return data


WORKFORCE: tuple[WorkforceAgent, ...] = (
    WorkforceAgent("IncidentAgent", "Classify privacy-safe reliability events and open deduplicated incident cases.", "AUTOMATIC", ("incident_classification", "severity", "owner_attention"), (), ("read_raw_patient_payloads", "hide_incident")),
    WorkforceAgent("EngineeringAgent", "Reproduce an issue in an isolated development/test boundary and describe the failing contract.", "AUTOMATIC_SANDBOX", ("reproduction_steps", "affected_contracts"), (), ("edit_production_directly", "read_production_secrets")),
    WorkforceAgent("RootCauseAgent", "Analyze code, logs and tests to form evidence-backed root-cause hypotheses.", "AUTOMATIC_ANALYSIS", ("root_cause_hypotheses", "evidence"), (), ("invent_evidence", "access_unapproved_private_data")),
    WorkforceAgent("RepairAgent", "Prepare a minimal reviewable repair proposal and regression-test plan.", "PROPOSAL_ONLY", ("patch_proposal", "regression_plan"), ("review_before_repository_write",), ("self_modify_production", "disable_safety", "expand_permissions")),
    WorkforceAgent("SecurityAgent", "Review proposed changes for auth, privacy, secrets, dependency and abuse regressions.", "AUTOMATIC_REVIEW", ("security_findings", "release_blockers"), (), ("approve_own_bypass", "expose_secrets")),
    WorkforceAgent("TestAgent", "Generate and run deterministic regression tests in an isolated test boundary.", "AUTOMATIC_SANDBOX", ("test_results", "coverage_gaps"), (), ("change_expected_results_to_hide_bug", "touch_production_data")),
    WorkforceAgent("QAAgent", "Exercise patient, provider and owner journeys against preview/canary environments.", "AUTOMATIC_PREVIEW", ("journey_results", "ux_regressions"), (), ("fabricate_pass", "use_real_patient_data_without_authorization")),
    WorkforceAgent("InfrastructureAgent", "Monitor OCI, PostgreSQL, Caddy, Vercel, storage, email, TURN and integration health.", "AUTOMATIC_READ_ONLY", ("health_evidence", "capacity_or_connectivity_alerts"), (), ("rotate_secrets_without_gate", "delete_production_state")),
    WorkforceAgent("DataAgent", "Refresh approved public/official datasets with provenance, licensing and schema controls.", "AUTOMATIC_BOUNDED", ("refresh_results", "source_freshness"), (), ("scrape_private_data", "bypass_access_controls", "erase_provenance")),
    WorkforceAgent("IntegrationAgent", "Monitor external API/provider boundaries and prepare adapter remediation.", "AUTOMATIC_READ_ONLY", ("integration_health", "adapter_issue"), (), ("fake_provider_availability", "bypass_provider_auth")),
    WorkforceAgent("ProductAgent", "Analyze aggregate product signals and prepare feature/UX proposals.", "AUTOMATIC_ANALYSIS", ("product_findings", "prioritized_proposals"), (), ("inspect_private_clinical_content_for_growth", "manipulate_clinical_ranking")),
    WorkforceAgent("SupportAgent", "Classify user-reported issues and route them without exposing unrelated account data.", "AUTOMATIC_CLASSIFICATION", ("support_category", "routing"), ("human_support_for_sensitive_cases",), ("impersonate_user", "override_consent")),
    WorkforceAgent("CommunicationsAgent", "Prepare truthful operational/user communications from verified system state.", "DRAFT_OR_VERIFIED_TEMPLATE", ("draft_message", "delivery_candidate"), ("approval_for_broad_or_sensitive_broadcast",), ("send_false_status", "patient_marketing_without_consent")),
    WorkforceAgent("ResearchAgent", "Discover legitimate official, public and licensed healthcare sources and standards.", "AUTOMATIC_READ_ONLY", ("source_candidates", "licensing_notes", "adapter_proposal"), (), ("bypass_terms_or_paywalls", "collect_private_user_data")),
    WorkforceAgent("ManagerAgent", "Prioritize the AI workforce queue using severity, user impact and release risk.", "AUTOMATIC_PRIORITIZATION", ("priority", "assignment", "escalation"), (), ("suppress_critical_incident", "override_safety_gate")),
    WorkforceAgent("ReleaseAgent", "Assemble preview evidence, release gates, rollback plan and production-promotion request.", "OWNER_GATED_PRODUCTION", ("release_candidate", "rollback_plan", "verification_evidence"), ("configured_owner_approval_for_production",), ("unreviewed_production_deploy", "disable_release_gate")),
    WorkforceAgent("KnowledgeAgent", "Record sanitized incident learnings and regression knowledge after verification.", "AUTOMATIC_SAFE", ("knowledge_record", "future_regression_hint"), (), ("store_secrets", "store_raw_health_content_in_ops_memory")),
)


INCIDENT_PIPELINE: tuple[dict, ...] = (
    {"stage": "detect_and_classify", "agent_id": "IncidentAgent", "automatic": True, "gate": None},
    {"stage": "reproduce", "agent_id": "EngineeringAgent", "automatic": True, "gate": "sandbox_only"},
    {"stage": "root_cause", "agent_id": "RootCauseAgent", "automatic": True, "gate": None},
    {"stage": "repair_proposal", "agent_id": "RepairAgent", "automatic": True, "gate": "proposal_only"},
    {"stage": "security_review", "agent_id": "SecurityAgent", "automatic": True, "gate": None},
    {"stage": "regression_tests", "agent_id": "TestAgent", "automatic": True, "gate": "test_environment_only"},
    {"stage": "preview_qa", "agent_id": "QAAgent", "automatic": True, "gate": "preview_or_canary_only"},
    {"stage": "release_evidence", "agent_id": "ReleaseAgent", "automatic": True, "gate": "no_production_promotion"},
    {"stage": "production_approval", "agent_id": "ReleaseAgent", "automatic": False, "gate": "configured_owner_approval"},
    {"stage": "post_release_verify", "agent_id": "InfrastructureAgent", "automatic": True, "gate": "read_only_verification"},
    {"stage": "knowledge_capture", "agent_id": "KnowledgeAgent", "automatic": True, "gate": "sanitized_metadata_only"},
)

SEVERITIES = {"low", "medium", "high", "critical"}


def workforce_manifest() -> dict:
    return {
        "version": "ai-workforce-v1",
        "agents": [agent.to_dict() for agent in WORKFORCE],
        "incident_pipeline": [dict(stage) for stage in INCIDENT_PIPELINE],
        "automatic_until": "production_approval",
        "production_rule": "Production promotion, permission expansion and other consequential changes require deterministic gates and configured-owner approval.",
        "privacy_rule": "Operational cases use sanitized metadata; raw patient content, credentials and payment secrets are excluded.",
    }


def build_incident_plan(
    summary: str,
    *,
    severity: str = "medium",
    source_type: str = "runtime",
    source_event_id: int | None = None,
) -> dict:
    clean_severity = str(severity or "medium").strip().lower()
    if clean_severity not in SEVERITIES:
        raise ValueError("Unsupported incident severity.")
    clean_summary = redact_operational_text(str(summary or "").strip(), 500)
    if not clean_summary:
        raise ValueError("Incident summary is required.")
    return {
        "summary": clean_summary,
        "severity": clean_severity,
        "source_type": str(source_type or "runtime")[:80],
        "source_event_id": int(source_event_id) if source_event_id else None,
        "stages": [dict(stage) for stage in INCIDENT_PIPELINE],
        "current_stage": "detect_and_classify",
        "production_approval_required": True,
        "arbitrary_code_execution": False,
        "secret_access": False,
        "clinical_authority": False,
        "payment_authority": False,
        "emergency_dispatch_authority": False,
    }


def _owner_id(actor: Any) -> int:
    if hasattr(actor, "keys") and "id" in actor.keys():
        return int(actor["id"])
    if isinstance(actor, dict):
        return int(actor.get("id") or 0)
    return 0


def enqueue_incident_case(
    actor: Any,
    summary: str,
    *,
    severity: str = "medium",
    source_type: str = "runtime",
    source_event_id: int | None = None,
) -> dict:
    assert_owner(actor)
    plan = build_incident_plan(
        summary,
        severity=severity,
        source_type=source_type,
        source_event_id=source_event_id,
    )
    if source_event_id:
        idempotency_key = f"ai-workforce:event:{int(source_event_id)}"
    else:
        digest = hashlib.sha256(
            f"{plan['severity']}:{plan['source_type']}:{plan['summary']}".encode("utf-8")
        ).hexdigest()[:24]
        idempotency_key = f"ai-workforce:summary:{digest}"

    existing = get_db().execute(
        "SELECT * FROM agent_tasks WHERE idempotency_key=?",
        (idempotency_key,),
    ).fetchone()
    if existing:
        return {"created": False, "task": dict(existing), "plan": plan}

    priority = {"low": "low", "medium": "normal", "high": "high", "critical": "critical"}[plan["severity"]]
    task = create_agent_task(
        task_type="ai_workforce_incident",
        requested_by=_owner_id(actor),
        assigned_agent="OperationsAgent",
        priority=priority,
        risk_level="low_risk",
        max_attempts=1,
        idempotency_key=idempotency_key,
        metadata={
            "workforce_version": "ai-workforce-v1",
            "case_kind": "reliability_incident",
            "incident_plan": plan,
        },
        actor=actor,
    )
    publish_event(
        "workforce.incident.queued",
        actor=actor,
        entity_type="agent_task",
        entity_id=str(task["id"]),
        status="queued",
        payload={
            "task_id": task["id"],
            "severity": plan["severity"],
            "source_type": plan["source_type"],
            "source_event_id": plan["source_event_id"],
        },
        agent_name="IncidentAgent",
        idempotency_key=f"workforce-event:{idempotency_key}",
    )
    return {"created": True, "task": task, "plan": plan}


def intake_failed_events(actor: Any, *, limit: int = 25) -> dict:
    """Turn recent privacy-safe failed/error platform events into deduplicated cases."""
    assert_owner(actor)
    limit = max(1, min(int(limit or 25), 100))
    rows = get_db().execute(
        """
        SELECT id,event_type,action,entity_type,status,error,created_at
        FROM platform_events
        WHERE status IN ('failed','error')
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    created = []
    existing = []
    for row in rows:
        event_type = str(row["event_type"] or row["action"] or "platform.failure")
        severity = "high" if any(token in event_type for token in ("release", "deployment", "security", "database")) else "medium"
        error = redact_operational_text(str(row["error"] or ""), 240)
        summary = f"{event_type} failed"
        if error:
            summary += f": {error}"
        result = enqueue_incident_case(
            actor,
            summary,
            severity=severity,
            source_type="platform_event",
            source_event_id=int(row["id"]),
        )
        target = created if result["created"] else existing
        target.append({
            "source_event_id": int(row["id"]),
            "task_id": int(result["task"]["id"]),
            "severity": severity,
        })
    return {
        "status": "completed",
        "scanned_count": len(rows),
        "created_count": len(created),
        "existing_count": len(existing),
        "created": created,
        "existing": existing,
        "production_changes_executed": 0,
        "notice": "Cases are triage/repair workflows only; production promotion remains owner-gated.",
    }
