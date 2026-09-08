"""ZENDOC Agent Fleet — specialized no-capital automation layer.

This registry describes what each software agent is responsible for and what it
must never claim or execute. It is intentionally model-agnostic: deterministic
logic, local open-weight models, cloud LLMs, retrieval tools, and human review can
all participate behind the same safety/permission contract.

The fleet exists to make domain responsibility explicit and testable rather than
letting one generic assistant answer every healthcare request.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class FleetAgent:
    agent_id: str
    mission: str
    primary_inputs: tuple[str, ...]
    primary_outputs: tuple[str, ...]
    automation_level: str
    preferred_model_tasks: tuple[str, ...]
    deterministic_first: tuple[str, ...]
    human_gates: tuple[str, ...]
    forbidden: tuple[str, ...]

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in (
            "primary_inputs",
            "primary_outputs",
            "preferred_model_tasks",
            "deterministic_first",
            "human_gates",
            "forbidden",
        ):
            data[key] = list(data[key])
        return data


AGENT_FLEET: tuple[FleetAgent, ...] = (
    FleetAgent(
        "SafetyAgent",
        "Detect emergencies and policy-critical risk before every other workflow.",
        ("user_text", "known_red_flags"),
        ("urgency", "safe_next_action"),
        "AUTOMATIC",
        (),
        ("emergency_triage", "red_flag_rules"),
        ("licensed_clinical_judgement_when_required",),
        ("diagnosis", "prescribing", "delay_emergency_escalation"),
    ),
    FleetAgent(
        "CareFinAgent",
        "Discover and organize government schemes, insurance, employer, CSR and trust support while preserving coverage truth states.",
        ("location", "demographics", "employment", "user_authorized_policy_evidence"),
        ("candidate_support_paths", "missing_documents", "coverage_truth_state", "next_verification_step"),
        "AUTOMATIC_DISCOVERY",
        ("scheme_query_rewrite", "benefit_explanation", "document_summarization"),
        ("source_provenance", "coverage_state_machine", "eligibility_rule_checks"),
        ("official_or_partner_confirmation_for_coverage",),
        ("fabricate_eligibility", "fabricate_approval", "sell_patient_data"),
    ),
    FleetAgent(
        "ProviderDiscoveryAgent",
        "Find verified ZENDOC providers and truthful external healthcare locations.",
        ("category", "specialty", "location", "coordinates"),
        ("provider_options", "source", "verification_state"),
        "AUTOMATIC",
        ("query_normalization",),
        ("role_filtering", "distance_filtering", "source_labelling"),
        (),
        ("invent_provider", "invent_booking_availability"),
    ),
    FleetAgent(
        "HealthMemoryAgent",
        "Organize authorized longitudinal records and produce minimum-necessary context bundles.",
        ("authorized_records", "timeline", "measurements"),
        ("timeline_summary", "context_bundle", "provenance"),
        "AUTOMATIC_READ_ONLY",
        ("summarization", "non_critical_extraction"),
        ("authorization", "provenance", "minimum_context"),
        ("patient_or_caregiver_consent",),
        ("cross_patient_access", "train_on_patient_data_without_separate_consent"),
    ),
    FleetAgent(
        "MedicationSafetyAgent",
        "Validate prescription extraction and block unsafe medicine automation.",
        ("prescription_items", "extraction_confidence", "catalog_matches"),
        ("review_flags", "exact_match_state", "safe_next_action"),
        "AUTOMATIC_GUARD",
        ("non_critical_extraction",),
        ("exact_strength_form_match", "confidence_thresholds"),
        ("pharmacist_or_doctor_review_for_ambiguity",),
        ("substitution", "dose_change", "prescribing"),
    ),
    FleetAgent(
        "PharmacyAgent",
        "Compare confirmed pharmacy fulfilment and stage orders without autonomous purchasing.",
        ("verified_prescription", "location", "inventory_observations"),
        ("ranked_fulfilment_options", "plan_hash", "cost_unknowns"),
        "AUTOMATIC_UNTIL_CONFIRMATION",
        ("option_explanation",),
        ("freshness_rules", "eligibility", "idempotency"),
        ("explicit_user_confirmation", "provider_acknowledgement"),
        ("fabricate_stock", "submit_without_confirmation"),
    ),
    FleetAgent(
        "DiagnosticsAgent",
        "Find truthful lab/test options and organize diagnostic workflows.",
        ("test_code", "location", "authorized_context"),
        ("verified_offers", "availability_state", "next_action"),
        "AUTOMATIC_DISCOVERY",
        ("query_normalization",),
        ("offer_verification",),
        ("user_confirmation_for_booking",),
        ("invent_test_availability", "interpret_result_as_diagnosis"),
    ),
    FleetAgent(
        "DoctorAgent",
        "Coordinate doctor discovery, appointments and telehealth requests while doctors retain clinical authority.",
        ("specialty", "provider", "schedule", "consultation_request"),
        ("available_slots", "consultation_state"),
        "AUTOMATIC_COORDINATION",
        ("intent_understanding",),
        ("schedule_rules", "permission_policy"),
        ("doctor_acceptance",),
        ("impersonate_doctor", "prescribe"),
    ),
    FleetAgent(
        "FamilyCareAgent",
        "Coordinate care for authorized family members using scoped, revocable consent.",
        ("relationship", "consent_grant", "care_tasks"),
        ("authorized_actions", "blocked_actions", "next_action"),
        "AUTOMATIC_WITH_CONSENT",
        ("relationship_resolution",),
        ("scope_check", "revocation_check"),
        ("adult_patient_consent",),
        ("silent_family_surveillance",),
    ),
    FleetAgent(
        "IoTAgent",
        "Normalize authorized device measurements with provenance and detect operational anomalies.",
        ("device_measurements", "device_identity"),
        ("normalized_measurements", "provenance", "alerts"),
        "AUTOMATIC",
        ("non_critical_summarization",),
        ("range_validation", "device_ownership"),
        ("clinical_review_for_medical_interpretation",),
        ("claim_unvalidated_device_diagnosis",),
    ),
    FleetAgent(
        "NutritionAgent",
        "Give evidence-based general nutrition, hydration and fitness guidance without paid medical ranking.",
        ("goal", "food_label", "ingredients", "activity_context"),
        ("comparison", "reasoning_summary", "cheaper_safe_options"),
        "AUTOMATIC_EDUCATION",
        ("comparison_explanation", "meal_idea_generation"),
        ("allergy_rules", "claim_provenance", "sponsorship_separation"),
        ("dietitian_or_clinician_for_medical_diets",),
        ("unsupported_health_claim", "hidden_sponsored_ranking"),
    ),
    FleetAgent(
        "OperationsAgent",
        "Run owner-only system health, queue monitoring, safe retries and escalation.",
        ("platform_events", "agent_tasks", "integration_status"),
        ("alerts", "retries", "escalations", "operational_summary"),
        "AUTOMATIC_SAFE_OPERATIONS",
        ("operational_summary",),
        ("retry_policy", "owner_authorization", "audit"),
        ("owner_approval_for_high_risk_changes",),
        ("arbitrary_shell", "arbitrary_sql", "secret_exposure"),
    ),
)


def list_fleet_agents() -> list[dict]:
    return [agent.to_dict() for agent in AGENT_FLEET]


def get_fleet_agent(agent_id: str) -> dict | None:
    normalized = str(agent_id or "").strip().lower()
    for agent in AGENT_FLEET:
        if agent.agent_id.lower() == normalized:
            return agent.to_dict()
    return None


def automation_manifest() -> dict:
    agents = list_fleet_agents()
    return {
        "agent_count": len(agents),
        "automatic_agents": [a["agent_id"] for a in agents if a["automation_level"].startswith("AUTOMATIC")],
        "human_gated_agents": [a["agent_id"] for a in agents if a["human_gates"]],
        "principle": "Automate reversible/read-only work; gate clinical, financial and consequential actions.",
    }
