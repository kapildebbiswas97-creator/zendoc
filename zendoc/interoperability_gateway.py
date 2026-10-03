"""Provider-neutral healthcare interoperability control plane.

This module defines the software boundary for FHIR-based exchange without
claiming that any external EHR, HIE, national network, or cloud health service
is connected. It is intentionally plan-first: external reads/writes remain
disabled until configuration, authorization, consent, and live verification are
proven by the specific adapter.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from typing import Any


VERIFIED_WORKING = "VERIFIED WORKING"
SOFTWARE_COMPLETE_LIVE_VERIFICATION = "SOFTWARE COMPLETE — LIVE EXTERNAL VERIFICATION REQUIRED"
EXTERNAL_CREDENTIAL_REQUIRED = "EXTERNAL CREDENTIAL REQUIRED"
PARTNER_CONTRACT_REQUIRED = "PARTNER/CONTRACT REQUIRED"
BLOCKED_BY_AUTHORIZATION = "BLOCKED BY AUTHORIZATION"
FAILED_VERIFICATION = "FAILED VERIFICATION"

FHIR_VERSIONS = ("R4", "R5")
FHIR_RESOURCE_TYPES = (
    "Patient",
    "Practitioner",
    "Organization",
    "Location",
    "Appointment",
    "CarePlan",
    "ServiceRequest",
    "Observation",
    "DiagnosticReport",
    "MedicationRequest",
    "MedicationStatement",
    "AllergyIntolerance",
    "Consent",
    "Provenance",
    "AuditEvent",
    "Coverage",
    "Claim",
    "Device",
    "DocumentReference",
    "ImagingStudy",
)

_RESOURCE_ALIASES = {item.lower(): item for item in FHIR_RESOURCE_TYPES}
_RESOURCE_ALIASES.update({
    "prescription": "MedicationRequest",
    "medication": "MedicationStatement",
    "diagnostic_report": "DiagnosticReport",
    "diagnostic report": "DiagnosticReport",
    "referral": "ServiceRequest",
    "care plan": "CarePlan",
    "care_plan": "CarePlan",
    "audit": "AuditEvent",
    "insurance": "Coverage",
    "imaging": "ImagingStudy",
})

PATIENT_LEVEL_RESOURCES = {
    "Patient",
    "Appointment",
    "CarePlan",
    "ServiceRequest",
    "Observation",
    "DiagnosticReport",
    "MedicationRequest",
    "MedicationStatement",
    "AllergyIntolerance",
    "Consent",
    "Coverage",
    "Claim",
    "Device",
    "DocumentReference",
    "ImagingStudy",
}


@dataclass(frozen=True)
class InteroperabilityAdapter:
    key: str
    label: str
    standards: tuple[str, ...]
    auth_model: str
    required_config: tuple[str, ...]
    authorization_flag: str
    verification_flag: str
    failed_verification_flag: str
    partner_config: tuple[str, ...] = ()
    jurisdiction_scope: tuple[str, ...] = ("global",)
    resource_types: tuple[str, ...] = FHIR_RESOURCE_TYPES
    notes: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in ("standards", "required_config", "partner_config", "jurisdiction_scope", "resource_types"):
            data[key] = list(data[key])
        return data


ADAPTERS: dict[str, InteroperabilityAdapter] = {
    "generic_fhir": InteroperabilityAdapter(
        key="generic_fhir",
        label="Generic SMART on FHIR Endpoint",
        standards=("FHIR R4", "FHIR R5", "SMART on FHIR", "OAuth 2.0/OIDC"),
        auth_model="SMART on FHIR / OAuth 2.0",
        required_config=("ZENDOC_FHIR_BASE_URL", "ZENDOC_FHIR_CLIENT_ID"),
        authorization_flag="ZENDOC_FHIR_AUTHORIZED",
        verification_flag="ZENDOC_FHIR_VERIFIED",
        failed_verification_flag="ZENDOC_FHIR_FAILED_VERIFICATION",
        notes="Provider-neutral contract for an authorized FHIR endpoint. No endpoint is contacted by this module.",
    ),
    "abdm_abha": InteroperabilityAdapter(
        key="abdm_abha",
        label="ABDM / ABHA Adapter",
        standards=("FHIR R4-compatible profiles", "ABDM consent/authorization boundary"),
        auth_model="ABDM-authorized application credentials and consent",
        required_config=("ZENDOC_ABDM_BASE_URL", "ZENDOC_ABDM_CLIENT_ID"),
        authorization_flag="ZENDOC_ABDM_AUTHORIZED",
        verification_flag="ZENDOC_ABDM_VERIFIED",
        failed_verification_flag="ZENDOC_ABDM_FAILED_VERIFICATION",
        jurisdiction_scope=("India",),
        notes="Architecture only until authorized ABDM onboarding and live verification are evidenced.",
    ),
    "epic_fhir": InteroperabilityAdapter(
        key="epic_fhir",
        label="Epic-compatible FHIR Adapter",
        standards=("FHIR R4", "SMART on FHIR"),
        auth_model="SMART on FHIR application authorization",
        required_config=("ZENDOC_EPIC_FHIR_BASE_URL", "ZENDOC_EPIC_CLIENT_ID"),
        authorization_flag="ZENDOC_EPIC_FHIR_AUTHORIZED",
        verification_flag="ZENDOC_EPIC_FHIR_VERIFIED",
        failed_verification_flag="ZENDOC_EPIC_FHIR_FAILED_VERIFICATION",
        notes="Adapter contract does not imply an Epic customer connection, tenant access, or production approval.",
    ),
    "oracle_health_fhir": InteroperabilityAdapter(
        key="oracle_health_fhir",
        label="Oracle Health-compatible FHIR Adapter",
        standards=("FHIR R4", "OAuth 2.0"),
        auth_model="Authorized Oracle Health tenant/application credentials",
        required_config=("ZENDOC_ORACLE_HEALTH_FHIR_BASE_URL", "ZENDOC_ORACLE_HEALTH_CLIENT_ID"),
        authorization_flag="ZENDOC_ORACLE_HEALTH_AUTHORIZED",
        verification_flag="ZENDOC_ORACLE_HEALTH_VERIFIED",
        failed_verification_flag="ZENDOC_ORACLE_HEALTH_FAILED_VERIFICATION",
        notes="Adapter contract does not imply an Oracle Health customer connection or licensed tenant access.",
    ),
    "aws_healthlake": InteroperabilityAdapter(
        key="aws_healthlake",
        label="AWS HealthLake Adapter",
        standards=("FHIR R4", "AWS IAM authorization"),
        auth_model="Authorized AWS workload identity / IAM",
        required_config=("ZENDOC_AWS_HEALTHLAKE_DATASTORE_ID", "AWS_REGION"),
        authorization_flag="ZENDOC_AWS_HEALTHLAKE_AUTHORIZED",
        verification_flag="ZENDOC_AWS_HEALTHLAKE_VERIFIED",
        failed_verification_flag="ZENDOC_AWS_HEALTHLAKE_FAILED_VERIFICATION",
        notes="Software contract is cloud-neutral; a configured datastore and authorized workload identity are still required.",
    ),
    "azure_health_data_services": InteroperabilityAdapter(
        key="azure_health_data_services",
        label="Azure Health Data Services Adapter",
        standards=("FHIR R4", "OAuth 2.0 / Microsoft Entra ID"),
        auth_model="Authorized Microsoft Entra application/workload identity",
        required_config=("ZENDOC_AZURE_HEALTH_DATA_SERVICES_URL", "ZENDOC_AZURE_TENANT_ID", "ZENDOC_AZURE_CLIENT_ID"),
        authorization_flag="ZENDOC_AZURE_HEALTH_AUTHORIZED",
        verification_flag="ZENDOC_AZURE_HEALTH_VERIFIED",
        failed_verification_flag="ZENDOC_AZURE_HEALTH_FAILED_VERIFICATION",
        notes="No Azure FHIR workspace access is claimed until authorization and a bounded live probe succeed.",
    ),
    "tefca_network": InteroperabilityAdapter(
        key="tefca_network",
        label="TEFCA-connected Network Adapter",
        standards=("FHIR where supported", "TEFCA exchange governance"),
        auth_model="Authorized participant/QHIN network access",
        required_config=("ZENDOC_TEFCA_ENDPOINT",),
        partner_config=("ZENDOC_TEFCA_QHIN",),
        authorization_flag="ZENDOC_TEFCA_AUTHORIZED",
        verification_flag="ZENDOC_TEFCA_VERIFIED",
        failed_verification_flag="ZENDOC_TEFCA_FAILED_VERIFICATION",
        jurisdiction_scope=("United States",),
        notes="Participation/network agreements are external dependencies; software readiness does not create TEFCA access.",
    ),
    "ehds_myhealth_eu": InteroperabilityAdapter(
        key="ehds_myhealth_eu",
        label="EHDS / MyHealth@EU-compatible Adapter",
        standards=("FHIR where applicable", "EU cross-border health exchange"),
        auth_model="Authorized national contact point / approved exchange identity",
        required_config=("ZENDOC_EHDS_ENDPOINT",),
        partner_config=("ZENDOC_EHDS_NCP_ID",),
        authorization_flag="ZENDOC_EHDS_AUTHORIZED",
        verification_flag="ZENDOC_EHDS_VERIFIED",
        failed_verification_flag="ZENDOC_EHDS_FAILED_VERIFICATION",
        jurisdiction_scope=("European Union / EEA",),
        notes="Cross-border access depends on applicable national/EU participation, legal basis, and authorization.",
    ),
}


def _env_present(name: str) -> bool:
    return bool(str(os.environ.get(name) or "").strip())


def _env_bool(name: str) -> bool:
    return str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def adapter_state(adapter: InteroperabilityAdapter) -> dict:
    missing_config = [name for name in adapter.required_config if not _env_present(name)]
    missing_partner = [name for name in adapter.partner_config if not _env_present(name)]
    authorized = _env_bool(adapter.authorization_flag)
    verified = _env_bool(adapter.verification_flag)
    failed = _env_bool(adapter.failed_verification_flag)

    if failed:
        truth_state = FAILED_VERIFICATION
    elif missing_partner:
        truth_state = PARTNER_CONTRACT_REQUIRED
    elif missing_config:
        truth_state = EXTERNAL_CREDENTIAL_REQUIRED
    elif not authorized:
        truth_state = BLOCKED_BY_AUTHORIZATION
    elif not verified:
        truth_state = SOFTWARE_COMPLETE_LIVE_VERIFICATION
    else:
        truth_state = VERIFIED_WORKING

    return {
        **adapter.to_dict(),
        "truth_state": truth_state,
        "configuration_present": not missing_config,
        "partner_or_contract_present": not missing_partner,
        "authorized": authorized,
        "verified": verified and not failed,
        "missing_config": missing_config,
        "missing_partner_config": missing_partner,
        "live_exchange_enabled": bool(truth_state == VERIFIED_WORKING),
        "external_action_executed": False,
    }


def interoperability_readiness_snapshot() -> dict:
    adapters = [adapter_state(adapter) for adapter in ADAPTERS.values()]
    verified = [item for item in adapters if item["truth_state"] == VERIFIED_WORKING]
    configured = [
        item for item in adapters
        if item["configuration_present"] and item["partner_or_contract_present"]
    ]
    return {
        "version": "interoperability-gateway-v1",
        "fhir_versions": list(FHIR_VERSIONS),
        "resource_types": list(FHIR_RESOURCE_TYPES),
        "adapters": adapters,
        "adapter_count": len(adapters),
        "configured_adapter_count": len(configured),
        "verified_adapter_count": len(verified),
        "software_ready": True,
        "live_exchange_enabled": bool(verified),
        "network_neutral": True,
        "provider_neutral": True,
        "truth_notice": (
            "ZENDOC implements provider-neutral interoperability contracts and exchange planning. "
            "No external record exchange is claimed until the selected adapter is configured, authorized, "
            "consented where required, and live-verified."
        ),
    }


def interoperability_manifest() -> dict:
    snapshot = interoperability_readiness_snapshot()
    return {
        **snapshot,
        "authorization_model": "minimum-necessary scope + explicit consent/legal authority + adapter authorization",
        "provenance_required": True,
        "audit_required": True,
        "external_writes_default": "disabled",
        "supported_directions": ["import", "export"],
    }


def _actor_value(actor: Any, key: str, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    return actor.get(key, default) if isinstance(actor, dict) else default


def _canonical_resource(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("resource_type is required.")
    canonical = _RESOURCE_ALIASES.get(raw.lower())
    if not canonical:
        raise ValueError(f"Unsupported FHIR resource type: {raw[:80]}")
    return canonical


def build_exchange_plan(
    actor: Any,
    *,
    adapter_key: str,
    resource_type: str,
    direction: str,
    patient_id: int | None = None,
) -> dict:
    """Build a non-executing, auditable exchange plan.

    This does not contact an external system and cannot expand the actor's
    permissions. A future execution layer must re-check consent/authorization,
    adapter verification, minimum-necessary scope, and idempotency.
    """
    actor_id = int(_actor_value(actor, "id", 0) or 0)
    role = str(_actor_value(actor, "role", "") or "").strip().lower()
    if actor_id <= 0 or role not in {"patient", "doctor", "hospital", "pharmacy", "government", "admin"}:
        raise PermissionError("An authenticated supported ZENDOC role is required.")

    key = str(adapter_key or "").strip().lower()
    adapter = ADAPTERS.get(key)
    if not adapter:
        raise LookupError("Unknown interoperability adapter.")

    canonical_resource = _canonical_resource(resource_type)
    requested_direction = str(direction or "").strip().lower()
    if requested_direction not in {"import", "export"}:
        raise ValueError("direction must be 'import' or 'export'.")

    state = adapter_state(adapter)
    patient_level = canonical_resource in PATIENT_LEVEL_RESOURCES
    target_patient_id = int(patient_id or actor_id) if patient_level else None

    if role == "patient" and target_patient_id not in {None, actor_id}:
        raise PermissionError("A patient interoperability plan cannot target another patient's records.")

    if state["truth_state"] == VERIFIED_WORKING:
        next_gate = "explicit_authorization_and_consent_before_live_exchange"
    elif state["truth_state"] == SOFTWARE_COMPLETE_LIVE_VERIFICATION:
        next_gate = "run_bounded_live_verification_before_exchange"
    elif state["truth_state"] == BLOCKED_BY_AUTHORIZATION:
        next_gate = "complete_external_authorization"
    elif state["truth_state"] == PARTNER_CONTRACT_REQUIRED:
        next_gate = "complete_required_partner_or_network_onboarding"
    elif state["truth_state"] == FAILED_VERIFICATION:
        next_gate = "repair_adapter_and_repeat_live_verification"
    else:
        next_gate = "configure_external_adapter_credentials_or_endpoint"

    return {
        "plan_version": "interop-plan-v1",
        "adapter_key": key,
        "adapter_label": adapter.label,
        "adapter_truth_state": state["truth_state"],
        "resource_type": canonical_resource,
        "direction": requested_direction,
        "actor_id": actor_id,
        "actor_role": role,
        "patient_id": target_patient_id,
        "patient_level_resource": patient_level,
        "minimum_necessary_scope": True,
        "provenance_required": True,
        "audit_required": True,
        "consent_or_legal_authority_required": patient_level,
        "human_confirmation_required": requested_direction == "export",
        "idempotency_required_for_future_write": requested_direction == "export",
        "permission_expansion": False,
        "execution_mode": "PLAN_ONLY",
        "external_action_executed": False,
        "live_exchange_permitted_by_this_plan": False,
        "next_gate": next_gate,
        "truth_notice": (
            "This is an exchange plan only. It does not read from or write to an external EHR/HIE, "
            "does not prove patient consent, and does not grant new access."
        ),
    }
