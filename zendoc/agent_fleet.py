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
        "BookingAgent",
        "Research connected provider availability, compare slots and prepare booking/reschedule actions without silently finalizing them.",
        ("provider_options", "verified_schedule", "requested_date", "user_preferences"),
        ("slot_options", "booking_preview", "confirmation_required"),
        "AUTOMATIC_UNTIL_CONFIRMATION",
        ("preference_understanding", "option_explanation", "date_rewrite"),
        ("provider_verification", "slot_availability", "atomic_slot_claim", "idempotency"),
        ("explicit_user_confirmation_before_booking", "provider_confirmation_where_required"),
        ("invent_slot", "book_external_unconnected_listing", "finalize_without_confirmation", "execute_payment"),
    ),
    FleetAgent(
        "CommerceAgent",
        "Discover and compare truthful non-medicine health products while keeping commercial ranking separate from clinical care.",
        ("product_query", "category", "user_preferences"),
        ("external_product_handoffs", "truth_state", "checkout_preview"),
        "AUTOMATIC_UNTIL_CHECKOUT",
        ("query_rewrite", "option_explanation", "comparison_summary"),
        ("medicine_query_separation", "commercial_disclosure", "clinical_commerce_separation"),
        ("explicit_user_confirmation_for_order_or_checkout",),
        ("fabricate_price", "fabricate_stock", "hidden_sponsored_ranking", "execute_payment", "collect_payment_secret"),
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
        "PreventionAgent",
        "Turn authorized longitudinal context into non-diagnostic prevention and routine-care reminders with evidence/provenance boundaries.",
        ("authorized_health_memory", "age_stage", "user_selected_goals", "care_history"),
        ("prevention_topics", "routine_followup_candidates", "questions_for_clinician"),
        "AUTOMATIC_READ_ONLY",
        ("plain_language_explanation", "reminder_summary"),
        ("consent_scope", "provenance", "guideline_source_state", "age_stage_rules"),
        ("clinician_review_when_medical_decision_required",),
        ("diagnosis", "prescribing", "infer_sensitive_life_stage", "replace_screening_guideline_with_model_opinion"),
    ),
    FleetAgent(
        "LifecycleAgent",
        "Coordinate explicit user-selected life-stage continuity from family building and childhood through adulthood, caregiving and older age.",
        ("authorized_health_memory", "explicit_life_stage", "family_graph", "care_goals"),
        ("life_stage_journey", "continuity_tasks", "care_learning_topics"),
        "AUTOMATIC_WITH_CONSENT",
        ("journey_explanation", "care_topic_summary"),
        ("consent_scope", "dob_based_child_stage_when_available", "provenance"),
        ("patient_or_guardian_consent",),
        ("infer_pregnancy", "infer_fertility_status", "infer_menopause", "silent_family_surveillance"),
    ),
    FleetAgent(
        "LearningAgent",
        "Provide health-learning journeys and truthful educational resources without converting education into diagnosis or treatment.",
        ("topic", "learning_goal", "verified_educational_sources"),
        ("learning_path", "educational_resource_options", "knowledge_check"),
        "AUTOMATIC_EDUCATION",
        ("explanation", "summarization", "question_generation"),
        ("source_provenance", "scope_separation"),
        ("clinician_review_for_personal_medical_decision",),
        ("diagnosis", "prescribing", "fabricate_citation", "fabricate_video"),
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
        "CareAgent",
        "Coordinate multi-step care across appointments, records, diagnostics, pharmacy and follow-up while preserving consent boundaries.",
        ("authorized_care_state", "appointments", "records", "diagnostic_options", "pharmacy_options"),
        ("care_coordination_summary", "staged_followup", "next_safe_actions"),
        "AUTOMATIC_WITH_CONSENT",
        ("care_summary", "option_explanation", "followup_planning"),
        ("authorization_scope", "record_provenance", "appointment_truth_state"),
        ("patient_consent_for_record_sharing", "clinician_review_for_medical_decisions"),
        ("diagnose", "prescribe", "share_record_without_consent", "execute_payment"),
    ),
    FleetAgent(
        "CommunicationAgent",
        "Coordinate permissioned ZENDOC Connect messaging, calls and media/report sharing through the communication policy layer.",
        ("actor", "target", "conversation", "channel", "communication_policy"),
        ("permission_decision", "conversation_action", "message_or_call_request"),
        "AUTOMATIC_POLICY_BOUND",
        ("intent_understanding", "message_drafting", "conversation_summary"),
        ("communication_policy", "conversation_membership", "record_share_consent"),
        ("fresh_consent_for_record_sharing", "doctor_acceptance_where_required"),
        ("bypass_communication_policy", "read_unpermitted_chat", "share_record_without_consent"),
    ),
    FleetAgent(
        "FitnessAgent",
        "Provide authenticated-patient workout planning, session support and general fitness coaching without replacing clinical exercise advice.",
        ("fitness_goal", "session_history", "authorized_activity_context", "user_constraints"),
        ("workout_plan", "session_guidance", "progress_summary"),
        "AUTOMATIC_EDUCATION",
        ("workout_generation", "progress_explanation", "non_clinical_coaching"),
        ("patient_scope", "declared_constraint_checks"),
        ("clinician_review_for_medical_exercise_restrictions",),
        ("diagnose", "prescribe_exercise_as_treatment", "ignore_declared_medical_restriction"),
    ),
    FleetAgent(
        "VideoAgent",
        "Find and share truthful educational video resources with source/provider availability clearly separated from clinical advice.",
        ("topic", "learning_goal", "video_provider_state", "conversation_target"),
        ("educational_video_options", "source_state", "share_preview"),
        "AUTOMATIC_EDUCATION",
        ("query_rewrite", "resource_summary"),
        ("provider_availability", "source_truth", "communication_permission"),
        ("user_confirmation_when_sharing_to_another_person",),
        ("fabricate_video", "fabricate_transcript", "convert_video_to_diagnosis"),
    ),
    FleetAgent(
        "HomeHealthAgent",
        "Prepare and track home-care intake for nursing, physiotherapy and elder-care services without inventing provider fulfilment.",
        ("care_need", "location", "authorized_patient_context", "provider_options"),
        ("intake_summary", "staged_home_care_request", "fulfilment_truth_state"),
        "AUTOMATIC_UNTIL_CONFIRMATION",
        ("intake_understanding", "option_explanation"),
        ("authorization_scope", "provider_connection_state", "service_truth_state"),
        ("explicit_user_confirmation_for_service_request", "provider_acceptance_for_fulfilment"),
        ("invent_provider", "claim_unconfirmed_fulfilment", "execute_payment"),
    ),
    FleetAgent(
        "TransportAgent",
        "Prepare non-emergency medical transport requests and compare connected options without autonomously dispatching vehicles.",
        ("transport_need", "pickup", "destination", "mobility_requirements", "provider_options"),
        ("transport_options", "staged_transport_request", "dispatch_truth_state"),
        "AUTOMATIC_UNTIL_CONFIRMATION",
        ("request_understanding", "option_explanation"),
        ("emergency_screen", "provider_connection_state", "location_validation"),
        ("explicit_user_confirmation_for_request", "provider_acceptance_for_dispatch"),
        ("dispatch_emergency", "invent_vehicle", "claim_unconfirmed_dispatch", "execute_payment"),
    ),
    FleetAgent(
        "SearchAgent",
        "Run universal read-only search across only the actor's permitted ZENDOC data and truthful external discovery sources.",
        ("query", "actor_role", "authorized_scope", "source_availability"),
        ("search_results", "source_state", "next_safe_action"),
        "AUTOMATIC_READ_ONLY",
        ("query_rewrite", "result_grouping", "relevance_explanation"),
        ("role_filtering", "authorization_scope", "source_provenance"),
        (),
        ("cross_user_data_leak", "fabricate_result", "convert_search_result_to_verified_provider_state"),
    ),
    FleetAgent(
        "ModelImprovementAgent",
        "Generate and evaluate prompt/routing/model candidates inside the isolated evaluation boundary without self-modifying production.",
        ("synthetic_eval_cases", "candidate_configuration", "evaluation_policy"),
        ("candidate_report", "eval_scores", "promotion_recommendation_for_owner_review"),
        "AUTOMATIC_SANDBOX_ONLY",
        ("candidate_generation", "failure_clustering", "evaluation_summary"),
        ("offline_eval_boundary", "tool_free_evaluation", "immutable_production_policy", "audit"),
        ("configured_owner_review_before_promotion",),
        (
            "self_modify_production_code",
            "self_promote_model",
            "deploy_production",
            "change_tool_permissions",
            "disable_safety",
            "disable_audit",
            "read_secrets",
        ),
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
