"""Deterministic cross-agent handoff contracts for ZENDOC.

The handoff graph coordinates specialist responsibility without granting one
agent another agent's tools. Each stage keeps its own registry/tool permissions
and its own human gate. The graph describes progression; it is not a bypass for
consent, clinical authority, payment authorization, provider confirmation, or
external integration truth.
"""
from __future__ import annotations

from copy import deepcopy

from .agent_registry import get_agent


WORKFLOW_HANDOFFS = {
    "appointment_booking": [
        {"agent": "SafetyAgent", "stage": "safety_guard", "mode": "automatic", "gate": None},
        {"agent": "ProviderDiscoveryAgent", "stage": "provider_discovery", "mode": "automatic", "gate": None},
        {"agent": "BookingAgent", "stage": "verified_slot_selection", "mode": "automatic_until_confirmation", "gate": "explicit_user_confirmation"},
        {"agent": "CareAgent", "stage": "provider_confirmation_and_careloop", "mode": "provider_state", "gate": "provider_confirmation"},
        {"agent": "HealthMemoryAgent", "stage": "outcome_to_longitudinal_memory", "mode": "authorized_read_write_service", "gate": "patient_context_authorization"},
    ],
    "pharmacy": [
        {"agent": "SafetyAgent", "stage": "safety_guard", "mode": "automatic", "gate": None},
        {"agent": "MedicationSafetyAgent", "stage": "prescription_truth_and_ambiguity", "mode": "automatic_guard", "gate": "clinician_or_pharmacist_if_ambiguous"},
        {"agent": "PharmacyAgent", "stage": "inventory_compare_and_stage", "mode": "automatic_until_confirmation", "gate": "explicit_user_confirmation"},
        {"agent": "HealthMemoryAgent", "stage": "confirmed_fulfilment_outcome", "mode": "authorized_continuity", "gate": "patient_context_authorization"},
    ],
    "diagnostics": [
        {"agent": "SafetyAgent", "stage": "safety_guard", "mode": "automatic", "gate": None},
        {"agent": "DiagnosticsAgent", "stage": "test_and_lab_discovery", "mode": "automatic_discovery", "gate": "explicit_user_confirmation_for_booking"},
        {"agent": "CareAgent", "stage": "provider_service_confirmation", "mode": "provider_state", "gate": "provider_confirmation"},
        {"agent": "HealthMemoryAgent", "stage": "result_provenance_and_continuity", "mode": "authorized_continuity", "gate": "patient_context_authorization"},
    ],
    "health_commerce": [
        {"agent": "SafetyAgent", "stage": "health_claim_guard", "mode": "automatic", "gate": None},
        {"agent": "CommerceAgent", "stage": "external_product_discovery", "mode": "automatic_read_only", "gate": "user_controls_external_checkout"},
    ],
    "preventive_care": [
        {"agent": "SafetyAgent", "stage": "safety_guard", "mode": "automatic", "gate": None},
        {"agent": "HealthMemoryAgent", "stage": "authorized_baseline_context", "mode": "authorized_read_only", "gate": "patient_context_authorization"},
        {"agent": "PreventionAgent", "stage": "non_diagnostic_next_safe_actions", "mode": "automatic_guidance", "gate": "clinician_review_for_medical_decisions"},
        {"agent": "CareAgent", "stage": "care_follow_through", "mode": "bounded_coordination", "gate": "service_confirmation_when_applicable"},
    ],
    "lifecycle": [
        {"agent": "SafetyAgent", "stage": "safety_guard", "mode": "automatic", "gate": None},
        {"agent": "LifecycleAgent", "stage": "explicit_life_stage_context", "mode": "consent_bound", "gate": "explicit_user_selected_life_stage"},
        {"agent": "PreventionAgent", "stage": "age_or_stage_appropriate_wellness", "mode": "automatic_guidance", "gate": "clinician_review_for_medical_decisions"},
        {"agent": "FamilyCareAgent", "stage": "caregiver_coordination", "mode": "consent_bound", "gate": "adult_patient_or_guardian_consent"},
        {"agent": "HealthMemoryAgent", "stage": "longitudinal_continuity", "mode": "authorized_continuity", "gate": "patient_context_authorization"},
    ],
    "fitness": [
        {"agent": "SafetyAgent", "stage": "exercise_red_flag_guard", "mode": "automatic", "gate": None},
        {"agent": "FitnessAgent", "stage": "plan_session_progress", "mode": "automatic_wellness", "gate": "professional_review_when_medical_restrictions_apply"},
        {"agent": "NutritionAgent", "stage": "general_nutrition_support", "mode": "automatic_education", "gate": "dietitian_or_clinician_for_medical_diet"},
        {"agent": "HealthMemoryAgent", "stage": "authorized_activity_continuity", "mode": "authorized_continuity", "gate": "patient_context_authorization"},
    ],
    "health_learning": [
        {"agent": "SafetyAgent", "stage": "medical_claim_guard", "mode": "automatic", "gate": None},
        {"agent": "LearningAgent", "stage": "evidence_aware_education", "mode": "automatic_education", "gate": "clinician_review_for_personal_medical_decision"},
    ],
    "carefin": [
        {"agent": "CareFinAgent", "stage": "support_discovery", "mode": "automatic_discovery", "gate": "authoritative_eligibility_confirmation"},
        {"agent": "CareAgent", "stage": "care_path_coordination", "mode": "bounded_coordination", "gate": "provider_or_payer_confirmation"},
    ],
    "model_improvement": [
        {"agent": "ModelImprovementAgent", "stage": "offline_candidate_evaluation", "mode": "isolated_sandbox", "gate": "configured_owner_review"},
    ],
}


def handoff_for_intent(intent: str) -> list[dict]:
    chain = deepcopy(WORKFLOW_HANDOFFS.get(str(intent or "").strip(), []))
    for stage in chain:
        if get_agent(stage["agent"]) is None:
            raise RuntimeError(f"Handoff references unknown agent '{stage['agent']}'.")
    return chain


def handoff_manifest() -> dict:
    return {
        "workflow_count": len(WORKFLOW_HANDOFFS),
        "workflows": {key: handoff_for_intent(key) for key in WORKFLOW_HANDOFFS},
        "invariants": {
            "handoff_grants_new_tool_permissions": False,
            "external_unknown_becomes_confirmed": False,
            "provider_confirmed_equals_patient_reported": False,
            "model_executes_payment": False,
            "model_can_self_promote": False,
            "clinical_authority_remains_human": True,
        },
    }
