"""Bounded deterministic planner for the ZENDOC Core Agent."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from .agent_registry import choose_agent_for_intent
from .safety import SafetyEngine


@dataclass(frozen=True)
class PlanStep:
    sequence: int
    tool_name: str
    arguments: dict = field(default_factory=dict)
    purpose: str = ""

    def to_dict(self):
        return {
            "sequence": self.sequence,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "purpose": self.purpose,
        }


@dataclass(frozen=True)
class AgentPlan:
    plan_id: str
    command: str
    intent: str
    urgency: str
    assigned_agent: str
    risk_level: str
    steps: tuple[PlanStep, ...]
    requires_confirmation: bool = False
    authorization_error: str | None = None
    safety: dict = field(default_factory=dict)
    user_id: int | None = None
    subject_id: int | None = None
    action_preview: dict | None = None
    privacy_class: str = "INTERNAL"
    required_context: tuple[str, ...] = ()
    human_gate: str | None = None
    expected_output: str = "structured_result"
    fallback_strategy: str = "safe_read_only_fallback"

    def to_dict(self):
        data = {
            "plan_id": self.plan_id,
            "intent": self.intent,
            "urgency": self.urgency,
            "assigned_agent": self.assigned_agent,
            "risk_level": self.risk_level,
            "privacy_class": self.privacy_class,
            "required_context": list(self.required_context),
            "steps": [step.to_dict() for step in self.steps],
            "requires_confirmation": self.requires_confirmation,
            "human_gate": self.human_gate,
            "expected_output": self.expected_output,
            "fallback_strategy": self.fallback_strategy,
            "authorization_error": self.authorization_error,
        }
        if self.user_id is not None:
            data["user_id"] = self.user_id
        if self.subject_id is not None:
            data["subject_id"] = self.subject_id
        if self.action_preview is not None:
            data["action_preview"] = self.action_preview
        return data


def build_plan(actor, command_text: str) -> AgentPlan:
    command = str(command_text or "").strip()
    if not command:
        raise ValueError("Agent command is required.")
    if len(command) > 2000:
        raise ValueError("Agent command is too long.")

    safety = SafetyEngine().assess(command)
    if safety["emergency"]:
        return _plan(
            command,
            "emergency",
            "SafetyAgent",
            "read_only",
            (),
            safety=safety,
            urgency="emergency",
            privacy_class="HIGH_RISK",
            required_context=("user_message",),
            expected_output="emergency_safe_next_action",
            fallback_strategy="deterministic_emergency_guidance",
        )

    lower = command.lower()
    from .security import is_owner
    owner = is_owner(actor)

    if any(text in lower for text in ("summary", "platform health", "operations summary", "today")) and owner:
        return _plan(
            command,
            "platform_health",
            "OperationsAgent",
            "read_only",
            (PlanStep(1, "get_platform_summary", {}, "Read aggregate operational health."),),
            required_context=("owner_identity",),
            expected_output="platform_health_summary",
        )
    if "failed" in lower and owner:
        return _plan(
            command,
            "failed_operations",
            "OperationsAgent",
            "read_only",
            (PlanStep(1, "get_failed_operations", {}, "Read failed operational events."),),
            required_context=("owner_identity",),
            expected_output="failed_operation_summary",
        )
    if any(text in lower for text in ("run alert check", "scan alerts", "check operational alerts")):
        if not owner:
            return _unauthorized(command, "platform_health")
        return _plan(
            command,
            "platform_health",
            "OperationsAgent",
            "low_risk",
            (PlanStep(1, "run_proactive_alert_check", {}, "Run bounded deterministic operational checks."),),
            required_context=("owner_identity",),
            expected_output="operational_alerts",
        )
    if any(text in lower for text in (
        "run operations automation", "safe operations automation", "auto retry safe tasks",
        "retry safe failures", "operations maintenance",
    )):
        if not owner:
            return _unauthorized(command, "operations_automation")
        return _plan(
            command,
            "operations_automation",
            "OperationsAgent",
            "low_risk",
            (PlanStep(1, "run_safe_operations_automation", {"retry_limit": 10}, "Re-queue retriable failures and create deterministic alerts only."),),
            required_context=("owner_identity", "agent_task_state", "platform_events"),
            expected_output="safe_maintenance_summary",
            fallback_strategy="alerts_only_no_execution",
        )

    if any(text in lower for text in (
        "improve model", "model improvement", "evaluate model", "model candidate",
        "prompt candidate", "routing candidate", "offline eval",
    )):
        if not owner:
            return _unauthorized(command, "model_improvement")
        return _plan(
            command,
            "model_improvement",
            "ModelImprovementAgent",
            "owner_approval",
            (),
            requires_confirmation=True,
            privacy_class="INTERNAL",
            required_context=("synthetic_eval_cases", "evaluation_policy"),
            human_gate="configured_owner_review_before_production_promotion",
            expected_output="offline_candidate_evaluation_plan",
            fallback_strategy="no_production_change",
        )

    if any(text in lower for text in (
        "government scheme", "health scheme", "insurance coverage", "insurance benefit",
        "carefin", "financial help", "medical funding", "csr", "charity", "trust support",
        "who can pay", "reduce hospital cost", "reduce treatment cost",
    )):
        return _plan(
            command,
            "carefin",
            "CareFinAgent",
            "read_only",
            (PlanStep(1, "discover_carefin_benefits", {"query": command}, "Discover possible support pathways without claiming eligibility."),),
            privacy_class="PERSONAL",
            required_context=("location", "age_optional", "occupation_optional", "income_optional", "authorized_policy_evidence_optional"),
            expected_output="benefit_candidates_with_truth_states",
            fallback_strategy="public_source_discovery_only",
        )

    if any(text in lower for text in ("prescription", "medicine name", "medicine strength", "drug order")):
        return _plan(
            command,
            "prescription",
            "MedicationSafetyAgent",
            "read_only",
            (PlanStep(1, "get_latest_prescription_review", {}, "Read the latest authorized prescription safety/review state."),),
            privacy_class="HEALTH_SENSITIVE",
            required_context=("authorized_prescription",),
            human_gate="pharmacist_or_doctor_review_if_ambiguous",
            expected_output="prescription_review_state",
            fallback_strategy="require_human_review",
        )

    if any(text in lower for text in (
        "medicine stock", "pharmacy stock", "medicine availability", "find medicine",
        "find prescribed medicine", "nearby medicine", "buy medicine",
    )):
        return _plan(
            command,
            "pharmacy",
            "PharmacyAgent",
            "read_only",
            (PlanStep(1, "search_nearby_pharmacy_inventory", {"query": command}, "Search truthful pharmacy inventory for the authenticated patient."),),
            privacy_class="HEALTH_SENSITIVE",
            required_context=("authenticated_patient", "medicine_query"),
            expected_output="pharmacy_inventory_with_freshness_state",
            fallback_strategy="unknown_inventory_not_available",
        )

    if any(text in lower for text in ("diagnostic", "blood test", "lab test", "laboratory", "home collection")):
        return _plan(
            command,
            "diagnostics",
            "DiagnosticsAgent",
            "read_only",
            (PlanStep(1, "get_diagnostic_options", {"query": command}, "Search verified diagnostic offers with freshness states."),),
            privacy_class="HEALTH_SENSITIVE",
            required_context=("test_query", "location_optional"),
            human_gate="user_confirmation_for_booking",
            expected_output="diagnostic_options_with_availability_state",
            fallback_strategy="unknown_availability_not_available",
        )

    if any(text in lower for text in (
        "book appointment", "appointment booking", "doctor appointment", "appointment slot",
        "request a consultation", "request consultation", "consultation request", "schedule consultation",
        "available appointment", "available slot", "reschedule appointment", "change appointment date",
    )):
        return _plan(
            command,
            "appointment_booking",
            "BookingAgent",
            "consent_required",
            (PlanStep(1, "search_healthcare_providers", {"query": command}, "Find truthful provider options before any booking action."),),
            requires_confirmation=True,
            privacy_class="PERSONAL",
            required_context=("provider_or_specialty", "location_optional", "preferred_date_optional"),
            human_gate="explicit_user_confirmation_before_booking",
            expected_output="provider_shortlist_then_verified_slot_selection",
            fallback_strategy="discovery_only_no_booking",
        )

    if any(text in lower for text in (
        "health product", "wellness product", "fitness equipment", "recovery equipment",
        "eyewear", "vision accessory", "home health device", "baby wellness product",
        "child wellness product", "buy fitness", "buy wellness", "shop health",
    )):
        return _plan(
            command,
            "health_commerce",
            "CommerceAgent",
            "read_only",
            (PlanStep(1, "search_health_products", {"query": command, "category": _commerce_category(lower)}, "Search truthful external health-product handoffs without claiming stock or price."),),
            privacy_class="PERSONAL",
            required_context=("product_query",),
            human_gate="explicit_user_confirmation_for_any_future_checkout",
            expected_output="external_product_handoffs_with_truth_state",
            fallback_strategy="external_search_handoff_only",
        )

    if any(text in lower for text in ("hospital near", "find hospital", "doctor near", "find doctor", "clinic near", "pharmacy near", "medical store near", "chemist near")):
        return _plan(
            command,
            "provider_discovery",
            "ProviderDiscoveryAgent",
            "read_only",
            (PlanStep(1, "search_healthcare_providers", {"query": command}, "Search verified ZENDOC providers and truthful external locations."),),
            privacy_class="PERSONAL",
            required_context=("provider_category", "location"),
            expected_output="provider_options_with_source_state",
            fallback_strategy="registered_provider_network_only",
        )

    if any(text in lower for text in (
        "preventive care", "prevention", "routine checkup", "routine check-up",
        "screening reminder", "prevent disease", "health maintenance",
    )):
        return _plan(
            command,
            "preventive_care",
            "PreventionAgent",
            "read_only",
            (PlanStep(1, "get_health_memory_context", {}, "Read only the authorized minimum-necessary longitudinal context."),),
            privacy_class="HEALTH_SENSITIVE",
            required_context=("authorized_patient_context", "explicit_prevention_goal_optional"),
            human_gate="clinician_review_for_medical_decisions",
            expected_output="non_diagnostic_prevention_context",
            fallback_strategy="general_prevention_education_only",
        )

    if any(text in lower for text in (
        "life stage", "life-stage", "pregnancy journey", "postpartum journey", "newborn journey",
        "child growth journey", "menopause journey", "older adult journey", "elder care journey",
        "family building journey",
    )):
        return _plan(
            command,
            "lifecycle",
            "LifecycleAgent",
            "consent_required",
            (PlanStep(1, "get_health_memory_context", {}, "Use authorized context only after the user explicitly selected the life-stage journey."),),
            privacy_class="HEALTH_SENSITIVE",
            required_context=("explicit_user_selected_life_stage", "authorized_patient_context"),
            human_gate="patient_or_guardian_consent",
            expected_output="life_stage_continuity_context",
            fallback_strategy="do_not_infer_sensitive_life_stage",
        )

    if any(text in lower for text in ("nutrition", "diet", "food label", "protein", "sugar", "sodium", "hydration", "healthy drink")):
        return _plan(
            command,
            "nutrition",
            "NutritionAgent",
            "read_only",
            (),
            privacy_class="PERSONAL",
            required_context=("goal_optional", "allergies_optional", "product_label_optional"),
            human_gate="clinician_or_dietitian_for_medical_diet",
            expected_output="general_nutrition_guidance",
            fallback_strategy="general_wellness_only",
        )

    if any(text in lower for text in ("workout", "fitness", "exercise plan", "exercise instruction", "my progress")):
        generate_requested = any(
            phrase in lower
            for phrase in ("create workout plan", "generate workout plan", "make workout plan", "new workout plan")
        )
        steps = [
            PlanStep(1, "get_fitness_snapshot", {}, "Read the authenticated patient's current fitness profile, plan and recent progress.")
        ]
        if generate_requested:
            steps.append(
                PlanStep(2, "generate_fitness_plan", {}, "Generate a general-wellness plan only when the saved profile supports safe automatic generation.")
            )
        return _plan(
            command,
            "fitness",
            "FitnessAgent",
            "low_risk" if generate_requested else "read_only",
            tuple(steps),
            privacy_class="PERSONAL",
            required_context=("fitness_profile_optional", "authenticated_patient"),
            human_gate="clinician_or_fitness_professional_when_medical_restrictions_apply",
            expected_output="fitness_snapshot_or_general_wellness_plan",
            fallback_strategy="general_wellness_only",
        )

    if any(text in lower for text in (
        "family care", "parent care", "care for my parent", "care for my mother", "care for my father",
        "family member care", "dependent care", "family care task",
    )):
        return _plan(
            command,
            "family_care",
            "FamilyCareAgent",
            "read_only",
            (PlanStep(1, "get_family_care_snapshot", {}, "Read only family relationships, scoped care tasks and consent grants visible to this actor."),),
            privacy_class="HEALTH_SENSITIVE",
            required_context=("authenticated_actor", "active_family_grants"),
            human_gate="adult_patient_consent_for_cross_patient_actions",
            expected_output="authorized_family_care_snapshot",
            fallback_strategy="self_care_only_without_grant",
        )

    if any(text in lower for text in (
        "home health", "home healthcare", "home care nurse", "home nurse", "physiotherapy at home",
        "physio at home", "elder care at home", "caregiver at home",
    )):
        return _plan(
            command,
            "home_health",
            "HomeHealthAgent",
            "read_only",
            (PlanStep(1, "get_home_health_options", {}, "List real ZENDOC home-health service categories and existing request truth states."),),
            privacy_class="HEALTH_SENSITIVE",
            required_context=("authenticated_actor", "location_optional", "family_grant_if_other_patient"),
            human_gate="explicit_user_confirmation_before_service_request",
            expected_output="home_health_options_and_request_truth_state",
            fallback_strategy="service_intake_only_no_fulfilment_claim",
        )

    if any(text in lower for text in (
        "medical transport", "wheelchair van", "patient transport", "ride to hospital",
        "transport to hospital", "ambulance request", "ambulance option",
    )):
        return _plan(
            command,
            "medical_transport",
            "TransportAgent",
            "read_only",
            (PlanStep(1, "get_transport_options", {}, "List medical-transport categories and existing request truth states without dispatching anything."),),
            privacy_class="HEALTH_SENSITIVE",
            required_context=("authenticated_actor", "pickup_optional", "destination_optional"),
            human_gate="explicit_user_confirmation_before_transport_request",
            expected_output="transport_options_without_dispatch_claim",
            fallback_strategy="no_dispatch_emergency_guidance_if_urgent",
        )

    if any(text in lower for text in ("learn about health", "health education", "teach me about", "understand health", "learning journey")):
        return _plan(
            command,
            "health_learning",
            "LearningAgent",
            "read_only",
            (PlanStep(1, "search_educational_video", {"query": command, "category": "patient_education"}, "Find truthful educational resources for the requested topic."),),
            privacy_class="INTERNAL",
            required_context=("learning_topic",),
            human_gate="clinician_review_for_personal_medical_decision",
            expected_output="educational_resource_options",
            fallback_strategy="written_education_without_fabricated_citations",
        )

    if any(text in lower for text in ("find contact", "search contact", "discover contact", "who can i message", "search doctor")):
        query = lower
        for phrase in ("find contact", "search contact", "discover contact", "who can i message"):
            query = query.replace(phrase, "")
        return _plan(
            command,
            "contact_discovery",
            "CommunicationAgent",
            "read_only",
            (PlanStep(1, "find_contact", {"query": query.strip() or "doctor"}, "Find policy-permitted contacts."),),
            required_context=("authenticated_actor",),
            expected_output="permitted_contacts",
        )
    if any(text in lower for text in ("share report", "send report", "share medical record")):
        return _plan(
            command,
            "record_share_request",
            "CommunicationAgent",
            "consent_required",
            (),
            requires_confirmation=True,
            privacy_class="HEALTH_SENSITIVE",
            required_context=("record_id", "recipient", "patient_consent"),
            human_gate="patient_consent",
            expected_output="record_share_preview",
        )
    if "share video" in lower:
        return _plan(
            command,
            "video_share",
            "CommunicationAgent",
            "low_risk",
            (),
            requires_confirmation=True,
            required_context=("conversation_id", "video"),
            human_gate="user_confirmation",
            expected_output="share_preview",
        )
    if any(text in lower for text in ("unread message", "check message", "my message", "inbox")):
        return _plan(
            command,
            "messages_inbox",
            "CommunicationAgent",
            "read_only",
            (PlanStep(1, "get_unread_summary", {}, "Count unread messages without reading clinical content."),),
            privacy_class="PERSONAL",
            required_context=("authenticated_actor",),
            expected_output="unread_count",
        )
    if any(text in lower for text in ("video consultation", "doctor video", "consultation", "telehealth")):
        return _plan(
            command,
            "telehealth_request",
            "DoctorAgent",
            "low_risk",
            (),
            privacy_class="HEALTH_SENSITIVE",
            required_context=("doctor_or_specialty", "consultation_type"),
            human_gate="doctor_acceptance",
            expected_output="consultation_request_state",
        )
    if "video" in lower:
        return _plan(
            command,
            "video_intelligence",
            "VideoAgent",
            "read_only",
            (PlanStep(1, "search_educational_video", {"query": command, "category": _video_category(lower)}, "Search truthful educational guidance."),),
            expected_output="educational_video_options",
        )
    if any(text in lower for text in (
        "health memory", "health record", "medical history", "health history",
        "health timeline", "my records", "my reports",
    )):
        return _plan(
            command,
            "health_records",
            "HealthMemoryAgent",
            "read_only",
            (
                PlanStep(1, "get_health_memory_context", {}, "Build minimum-necessary authorized Health Memory context with provenance."),
                PlanStep(
                    2,
                    "search_health_memory_evidence",
                    {"query": command, "limit": 5},
                    "Retrieve only matching stored evidence; exclude prior AI chat from medical evidence.",
                ),
            ),
            privacy_class="HEALTH_SENSITIVE",
            required_context=("authorized_patient_context", "timeline_scope"),
            expected_output="authorized_health_memory_summary_with_retrieval_evidence",
            fallback_strategy="deny_without_context_authorization",
        )
    if any(text in lower for text in ("device", "iot", "blood pressure", "heart rate")):
        return _plan(
            command,
            "iot_status",
            "IoTAgent",
            "read_only",
            (PlanStep(1, "get_iot_devices", {}, "List the authenticated user's device records."),),
            privacy_class="HEALTH_SENSITIVE",
            required_context=("authenticated_actor",),
            expected_output="authorized_device_status",
        )
    if any(text in lower for text in ("home care", "nurse", "parent")):
        return _plan(
            command,
            "care_coordination",
            "CareAgent",
            "consent_required",
            (),
            privacy_class="HEALTH_SENSITIVE",
            required_context=("patient_or_family_member", "consent_scope"),
            human_gate="family_access_grant_if_other_adult",
            expected_output="care_coordination_next_step",
        )

    return _plan(
        command,
        "general_agent",
        "SearchAgent",
        "read_only",
        (),
        required_context=("user_message",),
        expected_output="safe_navigation_or_search_guidance",
    )


def _plan(
    command,
    intent,
    agent,
    risk,
    steps,
    *,
    requires_confirmation=False,
    safety=None,
    urgency="routine",
    privacy_class="INTERNAL",
    required_context=(),
    human_gate=None,
    expected_output="structured_result",
    fallback_strategy="safe_read_only_fallback",
):
    definition = choose_agent_for_intent(intent)
    assigned_agent = definition.identifier if definition else agent
    return AgentPlan(
        plan_id=uuid.uuid4().hex,
        command=command,
        intent=intent,
        urgency=urgency,
        assigned_agent=assigned_agent,
        risk_level=risk,
        steps=tuple(steps),
        requires_confirmation=requires_confirmation,
        safety=safety or {},
        privacy_class=privacy_class,
        required_context=tuple(required_context),
        human_gate=human_gate,
        expected_output=expected_output,
        fallback_strategy=fallback_strategy,
    )


def _unauthorized(command, intent):
    return AgentPlan(
        plan_id=uuid.uuid4().hex,
        command=command,
        intent=intent,
        urgency="routine",
        assigned_agent="OperationsAgent",
        risk_level="owner_approval",
        steps=(),
        authorization_error="This operation is restricted to the ZENDOC owner.",
        privacy_class="INTERNAL",
        required_context=("owner_identity",),
        human_gate="owner_authentication",
        expected_output="authorization_error",
        fallback_strategy="deny",
    )


def _video_category(text):
    if "device" in text or "iot" in text:
        return "device_setup"
    if "nutrition" in text or "diet" in text:
        return "nutrition"
    if "rehab" in text or "mobility" in text:
        return "rehabilitation"
    if "staff" in text or "training" in text:
        return "staff_training"
    if "doctor" in text or "patient education" in text:
        return "patient_education"
    return "fitness"


def _commerce_category(text):
    if "eyewear" in text or "vision" in text or "glasses" in text:
        return "eyewear"
    if "fitness" in text or "recovery" in text or "workout" in text:
        return "fitness"
    if "nutrition" in text or "food" in text or "protein" in text:
        return "nutrition"
    if "baby" in text or "child" in text:
        return "baby_child"
    if "device" in text or "home health" in text:
        return "home_health"
    return "general_wellness"
