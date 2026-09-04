"""
ZENDOC Central Healthcare Orchestrator — Milestone 11
Trust-First Intelligence & Healthcare Orchestration

Coordinates existing domain capabilities (Safety Engine, Context Engine,
Subject Resolution, Family Care, Pharmacy Fulfilment, Diagnostic Marketplace,
Order Lifecycle, and Care Graph) into structured, permissioned, multi-step workflows.

Invariants:
1. Emergency safety check executes FIRST.
2. Subject resolution and family authorization verified before accessing data.
3. Repetitive user friction minimized via saved locations and active prescriptions.
4. No autonomous consequential actions — AI stages, user explicitly confirms.
5. Absolute truthfulness: No live data fabrication; zero inventory returns truthful explanation.
6. Provenance preserved across all steps and recorded to Care Graph.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from .care_graph import record_care_continuity_event
from .context_engine import verify_context_authorization
from .db import get_db, now_iso
from .diagnostic_service import search_lab_offers
from .fulfilment_optimizer import optimize_prescription_fulfilment
from .health_memory_continuity import determine_next_safe_actions
from .inventory_service import search_pharmacy_offers
from .order_service import get_order_details, submit_order_from_plan
from .prescription_service import get_prescription
from .safety import SafetyEngine
from .subject_resolver import SubjectResolution, resolve_request_subject


STEP_STATUSES = {
    "PLANNED",
    "BLOCKED_PERMISSION",
    "BLOCKED_DATA",
    "READY",
    "AWAITING_CONFIRMATION",
    "EXECUTING",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
}


@dataclass
class OrchestrationStep:
    step_id: str
    name: str
    purpose: str
    status: str
    tool_name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: str | None = None
    requires_confirmation: bool = False
    consequential: bool = False
    provenance_source: str = "PROVIDER_RECORDED"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ActionPreview:
    action_type: str  # "ORDER_MEDICINES" | "BOOK_DIAGNOSTIC" | "SHARE_RECORD"
    summary: str
    plan_id: int | None
    plan_hash: str | None
    patient_id: int
    items: list[dict[str, Any]]
    total_cost_inr: float | None
    delivery_fee_inr: float | None
    provider_name: str | None
    delivery_address: str | None
    requires_user_confirmation: bool = True
    consequential: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OrchestrationPlan:
    plan_id: str
    user_id: int
    subject_id: int | None
    subject_relationship: str
    subject_name: str | None
    intent: str
    urgency: str
    status: str  # "COMPLETED" | "AWAITING_CONFIRMATION" | "BLOCKED_PERMISSION" | "BLOCKED_DATA" | "EMERGENCY" | "FAILED"
    steps: list[OrchestrationStep]
    action_preview: ActionPreview | None = None
    plan_hash: str | None = None
    explanation: str = ""
    provenance_sources: list[str] = field(default_factory=list)
    next_safe_actions: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "user_id": self.user_id,
            "subject_id": self.subject_id,
            "subject_relationship": self.subject_relationship,
            "subject_name": self.subject_name,
            "intent": self.intent,
            "urgency": self.urgency,
            "status": self.status,
            "steps": [s.to_dict() for s in self.steps],
            "action_preview": self.action_preview.to_dict() if self.action_preview else None,
            "plan_hash": self.plan_hash,
            "explanation": self.explanation,
            "provenance_sources": self.provenance_sources,
            "next_safe_actions": self.next_safe_actions,
            "created_at": self.created_at,
        }


def _user_id(actor: Any) -> int:
    if actor is None:
        return 0
    uid = actor["id"] if hasattr(actor, "__getitem__") else getattr(actor, "id", None)
    return int(uid or 0)


def resolve_subject_location(
    actor: Any,
    subject_patient_id: int | None = None,
    relationship: str = "self",
    requested_city: str | None = None,
    requested_lat: float | None = None,
    requested_lon: float | None = None,
) -> dict[str, Any] | None:
    """
    Auto-resolve saved location to minimize repetitive friction.
    Prefers parent_home or family member's saved location if relationship is parent.
    """
    if requested_lat is not None and requested_lon is not None:
        return {
            "address": "Provided Coordinates",
            "city": requested_city or "Local",
            "latitude": float(requested_lat),
            "longitude": float(requested_lon),
            "label": "Current Request Location",
            "source": "INPUT_COORDINATES",
        }

    db = get_db()
    actor_id = _user_id(actor)
    if not actor_id:
        return None

    # 1. If coordinating for a parent, check for saved locations tagged parent_home
    is_parent = relationship in ("mother", "father", "parent", "grandmother", "grandfather")
    if is_parent:
        parent_loc = db.execute(
            """
            SELECT * FROM saved_locations
            WHERE user_id=? AND (
                LOWER(label) LIKE '%parent%' OR
                LOWER(label) LIKE '%mother%' OR
                LOWER(label) LIKE '%father%' OR
                LOWER(label) LIKE '%mom%' OR
                LOWER(label) LIKE '%dad%'
            )
            ORDER BY is_default DESC, id DESC
            """,
            (actor_id,),
        ).fetchone()
        if parent_loc:
            return {
                "id": parent_loc["id"],
                "address": parent_loc["address"],
                "city": parent_loc["city"],
                "latitude": parent_loc["latitude"],
                "longitude": parent_loc["longitude"],
                "label": parent_loc["label"],
                "source": "SAVED_LOCATION_PARENT",
            }

    # 2. Check the subject's own account if distinct from actor
    if subject_patient_id and subject_patient_id != actor_id:
        subj_loc = db.execute(
            """
            SELECT * FROM saved_locations
            WHERE user_id=?
            ORDER BY is_default DESC, id DESC
            """,
            (subject_patient_id,),
        ).fetchone()
        if subj_loc:
            return {
                "id": subj_loc["id"],
                "address": subj_loc["address"],
                "city": subj_loc["city"],
                "latitude": subj_loc["latitude"],
                "longitude": subj_loc["longitude"],
                "label": subj_loc["label"],
                "source": "SAVED_LOCATION_SUBJECT",
            }

    # 3. Fall back to actor's default or most recent saved location
    default_loc = db.execute(
        """
        SELECT * FROM saved_locations
        WHERE user_id=?
        ORDER BY is_default DESC, id DESC
        """,
        (actor_id,),
    ).fetchone()
    if default_loc:
        return {
            "id": default_loc["id"],
            "address": default_loc["address"],
            "city": default_loc["city"],
            "latitude": default_loc["latitude"],
            "longitude": default_loc["longitude"],
            "label": default_loc["label"],
            "source": "SAVED_LOCATION_USER",
        }

    if requested_city:
        return {
            "address": requested_city,
            "city": requested_city,
            "latitude": None,
            "longitude": None,
            "label": f"{requested_city} (City)",
            "source": "INPUT_CITY",
        }

    return None


def resolve_active_prescription(subject_patient_id: int) -> dict[str, Any] | None:
    """Find the most recent active prescription for the subject patient."""
    db = get_db()
    row = db.execute(
        """
        SELECT * FROM prescriptions
        WHERE patient_id=? AND status='active'
        ORDER BY id DESC LIMIT 1
        """,
        (subject_patient_id,),
    ).fetchone()
    if not row:
        return None
    return get_prescription(int(row["id"]))


class HealthcareOrchestrator:
    """
    Central Healthcare Orchestrator.
    Executes trust-first multi-system workflows with structured step transitions.
    """

    def __init__(self):
        self.safety = SafetyEngine()

    def orchestrate(
        self,
        actor: Any,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> OrchestrationPlan:
        context = context or {}
        user_id = _user_id(actor)
        plan_id = f"orch_{user_id}_{int(time.time() * 1000)}"

        # ── Step 0: Emergency Safety Triage (Always First) ───────────────────
        safety_assessment = self.safety.assess(text)
        if safety_assessment.get("emergency"):
            return OrchestrationPlan(
                plan_id=plan_id,
                user_id=user_id,
                subject_id=user_id,
                subject_relationship="self",
                subject_name="Self",
                intent="emergency",
                urgency="emergency",
                status="EMERGENCY",
                steps=[
                    OrchestrationStep(
                        step_id="safety_triage",
                        name="Emergency Safety Triage",
                        purpose="Detect acute clinical red flags and escalate immediately",
                        status="COMPLETED",
                        tool_name="safety_triage",
                        result=safety_assessment,
                        provenance_source="USER_REPORTED",
                    ),
                    OrchestrationStep(
                        step_id="escalation",
                        name="Emergency Medical Escalation",
                        purpose="Provide immediate 108 ambulance and hospital emergency instructions",
                        status="READY",
                        result={"action": "CALL_108", "guidance": safety_assessment.get("guidance")},
                        provenance_source="PROVIDER_RECORDED",
                    ),
                ],
                explanation=(
                    f"EMERGENCY SAFETY ALERT: {safety_assessment.get('reason')}. "
                    f"Please call 108 or proceed to the nearest emergency department immediately. "
                    f"Standard operational scheduling is suspended for patient safety."
                ),
                next_safe_actions=["call_108", "find_nearest_er"],
            )

        # ── Step 1: Subject Resolution & Permission Authorization ───────────
        # Determine intent category: pharmacy / diagnostics / care_coordination
        text_lower = text.lower()
        is_diagnostic = bool(re.search(r"\b(?:lab|labs|diagnostic|diagnostics|blood\s+test|hba1c|lipid|thyroid)\b", text_lower))
        requested_scope = "diagnostics" if is_diagnostic else "pharmacy"

        subject = resolve_request_subject(actor, text, requested_scope=requested_scope)
        subject_patient_id = subject.patient_id or user_id

        steps: list[OrchestrationStep] = []
        provenance_sources: list[str] = ["USER_REPORTED"]

        # Step 1 record
        steps.append(
            OrchestrationStep(
                step_id="subject_resolution",
                name="Resolve Patient & Verify Authorization",
                purpose="Confirm whether care is for self or family member and verify consent grant",
                status="COMPLETED" if subject.authorized else "BLOCKED_PERMISSION",
                tool_name="resolve_subject",
                result=subject.to_dict(),
                error=subject.message if not subject.authorized else None,
                provenance_source="PROVIDER_RECORDED",
            )
        )

        if not subject.authorized:
            return OrchestrationPlan(
                plan_id=plan_id,
                user_id=user_id,
                subject_id=subject.patient_id,
                subject_relationship=subject.relationship,
                subject_name=subject.subject_name,
                intent="family_care_orchestration",
                urgency="routine",
                status="BLOCKED_PERMISSION",
                steps=steps,
                explanation=subject.message,
                provenance_sources=provenance_sources,
                next_safe_actions=["request_family_consent", "view_family_settings"],
            )

        # ── Step 2: Location Resolution (Friction Minimization) ───────────────
        loc = resolve_subject_location(
            actor,
            subject_patient_id=subject.patient_id,
            relationship=subject.relationship,
            requested_city=context.get("city"),
            requested_lat=context.get("latitude"),
            requested_lon=context.get("longitude"),
        )

        loc_status = "COMPLETED" if loc else "BLOCKED_DATA"
        steps.append(
            OrchestrationStep(
                step_id="resolve_location",
                name="Resolve Delivery / Service Location",
                purpose="Look up saved home or parent location to eliminate repetitive input",
                status=loc_status,
                tool_name="resolve_saved_location",
                result=loc,
                error="No saved location found for delivery search" if not loc else None,
                provenance_source="USER_REPORTED",
            )
        )

        # ── Step 3: Branch by Intent (Pharmacy Fulfilment vs Diagnostics) ────
        if is_diagnostic:
            return self._orchestrate_diagnostic(
                actor=actor,
                plan_id=plan_id,
                subject=subject,
                loc=loc,
                text=text,
                steps=steps,
                provenance_sources=provenance_sources,
                context=context,
            )

        return self._orchestrate_pharmacy(
            actor=actor,
            plan_id=plan_id,
            subject=subject,
            loc=loc,
            text=text,
            steps=steps,
            provenance_sources=provenance_sources,
            context=context,
        )

    def _orchestrate_pharmacy(
        self,
        actor: Any,
        plan_id: str,
        subject: SubjectResolution,
        loc: dict[str, Any] | None,
        text: str,
        steps: list[OrchestrationStep],
        provenance_sources: list[str],
        context: dict[str, Any],
    ) -> OrchestrationPlan:
        user_id = _user_id(actor)
        patient_id = subject.patient_id or user_id

        # 1. Retrieve Active Prescription
        rx = resolve_active_prescription(patient_id)
        if not rx:
            steps.append(
                OrchestrationStep(
                    step_id="retrieve_prescription",
                    name="Retrieve Active Prescription",
                    purpose="Fetch verified medications from patient health memory",
                    status="BLOCKED_DATA",
                    error=f"No active prescription found for {subject.subject_name or 'patient'}.",
                    provenance_source="DOCUMENT_EXTRACTED",
                )
            )
            return OrchestrationPlan(
                plan_id=plan_id,
                user_id=user_id,
                subject_id=patient_id,
                subject_relationship=subject.relationship,
                subject_name=subject.subject_name,
                intent="prescription_fulfilment",
                urgency="routine",
                status="BLOCKED_DATA",
                steps=steps,
                explanation=(
                    f"No active prescription was found for {subject.subject_name or 'this patient'}. "
                    f"Please upload a prescription document or request a digital prescription from your doctor."
                ),
                provenance_sources=provenance_sources,
                next_safe_actions=["upload_prescription", "consult_doctor"],
            )

        provenance_sources.append("DOCUMENT_EXTRACTED")
        items = rx.get("items", [])
        uncertain = any(it.get("review_status") == "item_review_required" for it in items)

        steps.append(
            OrchestrationStep(
                step_id="retrieve_prescription",
                name="Retrieve Active Prescription",
                purpose="Fetch verified medications from patient health memory",
                status="COMPLETED",
                result={
                    "prescription_id": rx["id"],
                    "prescriber": rx.get("prescriber_name"),
                    "items_count": len(items),
                    "needs_review": uncertain,
                },
                provenance_source="DOCUMENT_EXTRACTED",
            )
        )

        # 2. Check clinical uncertainty boundary
        if uncertain:
            steps.append(
                OrchestrationStep(
                    step_id="clinical_review_guard",
                    name="Clinical Extraction Safeguard",
                    purpose="Protect patient against autonomous ordering of low-confidence medicine extractions",
                    status="BLOCKED_DATA",
                    error="One or more extracted medicines require human clinical confirmation before fulfilment.",
                    provenance_source="PROVIDER_RECORDED",
                )
            )
            return OrchestrationPlan(
                plan_id=plan_id,
                user_id=user_id,
                subject_id=patient_id,
                subject_relationship=subject.relationship,
                subject_name=subject.subject_name,
                intent="prescription_fulfilment",
                urgency="routine",
                status="BLOCKED_DATA",
                steps=steps,
                explanation=(
                    "One or more medications on this prescription were extracted with lower confidence "
                    "or have not been matched to an exact verified SKU. For safety, please confirm the exact "
                    "medication in the Prescription Review screen before ordering."
                ),
                provenance_sources=provenance_sources,
                next_safe_actions=["review_prescription_items"],
            )

        # 3. Search verified hyperlocal pharmacy inventory & optimize fulfilment
        lat = loc.get("latitude") if loc else None
        lon = loc.get("longitude") if loc else None
        city = loc.get("city") if loc else None
        delivery_addr = loc.get("address") if loc else (city or "Home Delivery")

        fulfilment = optimize_prescription_fulfilment(
            prescription_id=rx["id"],
            patient_id=patient_id,
            actor=actor,
            patient_lat=lat,
            patient_lon=lon,
            city=city,
            radius_km=float(context.get("radius_km", 15)),
            stage_in_db=True,
        )

        provenance_sources.append("PROVIDER_RECORDED")

        # 4. Handle Truthful Zero-Inventory or Unconfirmed state
        if fulfilment.get("status") in ("NO_CONFIRMED_INVENTORY", "NO_CONFIRMED_OPTION") or not fulfilment.get("plan_id"):
            steps.append(
                OrchestrationStep(
                    step_id="inventory_search",
                    name="Search Hyperlocal Pharmacy Inventory",
                    purpose="Match exact prescribed SKUs against confirmed participating pharmacy stock",
                    status="COMPLETED",
                    result=fulfilment,
                    provenance_source="PROVIDER_RECORDED",
                )
            )
            return OrchestrationPlan(
                plan_id=plan_id,
                user_id=user_id,
                subject_id=patient_id,
                subject_relationship=subject.relationship,
                subject_name=subject.subject_name,
                intent="prescription_fulfilment",
                urgency="routine",
                status="COMPLETED",
                steps=steps,
                explanation=fulfilment.get("message", "No confirmed participating pharmacy inventory is currently available for this prescription."),
                provenance_sources=provenance_sources,
                next_safe_actions=["increase_search_radius", "notify_when_available", "view_alternatives_with_doctor"],
            )

        # 5. Staged plan exists: prepare consequential action confirmation preview
        best_option = next(iter(fulfilment.get("options", {}).values()), {})
        plan_db_id = fulfilment.get("plan_id")
        plan_hash = fulfilment.get("plan_hash")
        total_cost = best_option.get("total_inr") or fulfilment.get("total_cost_inr")
        delivery_fee = best_option.get("delivery_fee_inr", 0.0)
        pharmacy_names = best_option.get("pharmacy_names", ["Verified Pharmacy Network"])

        action_preview = ActionPreview(
            action_type="ORDER_MEDICINES",
            summary=f"Order {len(items)} prescribed medications from {', '.join(pharmacy_names)}",
            plan_id=plan_db_id,
            plan_hash=plan_hash,
            patient_id=patient_id,
            items=[
                {
                    "medicine_name": it.get("medicine_name"),
                    "quantity": it.get("quantity_prescribed", 30),
                    "dosage": it.get("dosage"),
                }
                for it in items
            ],
            total_cost_inr=total_cost,
            delivery_fee_inr=delivery_fee,
            provider_name=", ".join(pharmacy_names),
            delivery_address=delivery_addr,
            requires_user_confirmation=True,
            consequential=True,
        )

        steps.append(
            OrchestrationStep(
                step_id="stage_fulfilment_plan",
                name="Stage Fulfilment Options",
                purpose="Calculate optimal single-store or split fulfilment from verified inventory",
                status="COMPLETED",
                result={
                    "plan_id": plan_db_id,
                    "plan_hash": plan_hash,
                    "strategy": best_option.get("strategy_name"),
                    "pharmacies": pharmacy_names,
                    "total_inr": total_cost,
                    "why_explanation": best_option.get("why_explanation", []),
                },
                provenance_source="PROVIDER_RECORDED",
            )
        )

        steps.append(
            OrchestrationStep(
                step_id="order_confirmation_gate",
                name="Explicit User Confirmation Gate",
                purpose="Verify order terms, address, and cost before submitting consequential order",
                status="AWAITING_CONFIRMATION",
                consequential=True,
                requires_confirmation=True,
                result=action_preview.to_dict(),
                provenance_source="PROVIDER_RECORDED",
            )
        )

        explanation = (
            f"Found verified stock for all {len(items)} medications for {subject.subject_name or 'patient'} "
            f"at {', '.join(pharmacy_names)}. "
            f"Total estimated landed cost: INR {total_cost:.2f}. "
            f"Delivery location: {delivery_addr}. "
            f"Review the staged order and confirm to dispatch."
        )

        return OrchestrationPlan(
            plan_id=plan_id,
            user_id=user_id,
            subject_id=patient_id,
            subject_relationship=subject.relationship,
            subject_name=subject.subject_name,
            intent="prescription_fulfilment",
            urgency="routine",
            status="AWAITING_CONFIRMATION",
            steps=steps,
            action_preview=action_preview,
            plan_hash=plan_hash,
            explanation=explanation,
            provenance_sources=provenance_sources,
            next_safe_actions=["confirm_order", "view_fulfilment_details", "change_delivery_address"],
        )

    def _orchestrate_diagnostic(
        self,
        actor: Any,
        plan_id: str,
        subject: SubjectResolution,
        loc: dict[str, Any] | None,
        text: str,
        steps: list[OrchestrationStep],
        provenance_sources: list[str],
        context: dict[str, Any],
    ) -> OrchestrationPlan:
        user_id = _user_id(actor)
        patient_id = subject.patient_id or user_id

        # Search lab offers
        test_query = text
        for kw in ("book", "lab", "test", "for", "my", "mother", "father", "blood", "near", "home"):
            test_query = re.sub(rf"\b{kw}\b", "", test_query, flags=re.IGNORECASE)
        test_query = test_query.strip() or "General Health Checkup"

        city = loc.get("city") if loc else context.get("city")
        lat = loc.get("latitude") if loc else None
        lon = loc.get("longitude") if loc else None

        offers = search_lab_offers(
            test_query,
            city=city,
            user_lat=lat,
            user_lon=lon,
        )
        provenance_sources.append("PROVIDER_RECORDED")

        if not offers:
            steps.append(
                OrchestrationStep(
                    step_id="search_lab_offers",
                    name="Search Diagnostic Providers",
                    purpose="Discover NABL-accredited diagnostic labs with home sample collection",
                    status="COMPLETED",
                    result={"offers": []},
                    provenance_source="PROVIDER_RECORDED",
                )
            )
            return OrchestrationPlan(
                plan_id=plan_id,
                user_id=user_id,
                subject_id=patient_id,
                subject_relationship=subject.relationship,
                subject_name=subject.subject_name,
                intent="diagnostic_booking",
                urgency="routine",
                status="COMPLETED",
                steps=steps,
                explanation=f"No accredited diagnostic laboratory offers matched '{test_query}' in the requested service area.",
                provenance_sources=provenance_sources,
                next_safe_actions=["widen_search_area", "consult_doctor_for_lab_referral"],
            )

        best_offer = offers[0]
        action_preview = ActionPreview(
            action_type="BOOK_DIAGNOSTIC",
            summary=f"Book {best_offer.get('test_name')} with {best_offer.get('lab_name')}",
            plan_id=best_offer.get("test_id"),
            plan_hash=None,
            patient_id=patient_id,
            items=[{"test_name": best_offer.get("test_name"), "code": best_offer.get("test_code")}],
            total_cost_inr=best_offer.get("price_inr"),
            delivery_fee_inr=best_offer.get("home_collection_fee_inr", 0.0),
            provider_name=best_offer.get("lab_name"),
            delivery_address=loc.get("address") if loc else "Home Collection",
            requires_user_confirmation=True,
            consequential=True,
        )

        steps.append(
            OrchestrationStep(
                step_id="stage_diagnostic_offer",
                name="Stage Diagnostic Option",
                purpose="Select verified NABL lab with confirmed pricing and sample collection",
                status="COMPLETED",
                result=best_offer,
                provenance_source="PROVIDER_RECORDED",
            )
        )
        steps.append(
            OrchestrationStep(
                step_id="booking_confirmation_gate",
                name="Booking Confirmation Gate",
                purpose="Verify appointment date, sample address, and test cost before booking",
                status="AWAITING_CONFIRMATION",
                consequential=True,
                requires_confirmation=True,
                result=action_preview.to_dict(),
                provenance_source="PROVIDER_RECORDED",
            )
        )

        return OrchestrationPlan(
            plan_id=plan_id,
            user_id=user_id,
            subject_id=patient_id,
            subject_relationship=subject.relationship,
            subject_name=subject.subject_name,
            intent="diagnostic_booking",
            urgency="routine",
            status="AWAITING_CONFIRMATION",
            steps=steps,
            action_preview=action_preview,
            explanation=(
                f"Found verified test '{best_offer.get('test_name')}' at {best_offer.get('lab_name')} "
                f"for {subject.subject_name or 'patient'}. Standard cost: INR {best_offer.get('price_inr', 0):.2f}. "
                f"Confirm to book home collection."
            ),
            provenance_sources=provenance_sources,
            next_safe_actions=["confirm_booking", "choose_collection_slot"],
        )

    def confirm_and_execute(
        self,
        actor: Any,
        plan_id: int,
        user_confirmed: bool,
        delivery_address: str,
        expected_plan_hash: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute a staged consequential plan once explicit user confirmation is given.
        Enforces plan hash verification, delivery address, and writes to Care Graph.
        """
        if not user_confirmed:
            raise PermissionError("Explicit user confirmation is strictly required before an action can be executed.")
        if not delivery_address or not str(delivery_address).strip():
            raise ValueError("A concrete delivery_address is required before an order can be executed.")

        # Execute through order service
        order_res = submit_order_from_plan(
            plan_id=int(plan_id),
            actor=actor,
            user_confirmed=True,
            delivery_address=str(delivery_address).strip(),
            idempotency_key=idempotency_key,
            expected_plan_hash=expected_plan_hash,
        )

        primary_order_id = int(order_res.get("order_id") or order_res.get("id"))
        details = get_order_details(primary_order_id, actor=None, _internal=True)
        patient_id = int(details.get("patient_id") or _user_id(actor))

        # Record Care Continuity Event in Care Graph
        record_care_continuity_event(
            patient_id=patient_id,
            event_type="ORDER_SUBMITTED",
            title=f"Order #{primary_order_id} placed with {details.get('pharmacy_name', 'Pharmacy')}",
            summary=f"Dispatched {len(details.get('items', []))} prescribed items for total INR {float(details.get('total_amount_inr') or 0.0):.2f}.",
            source="PROVIDER_RECORDED",
            source_ref=f"order:{primary_order_id}",
            metadata={
                "order_id": primary_order_id,
                "order_number": details.get("order_number"),
                "plan_id": plan_id,
                "pharmacy_id": details.get("pharmacy_id"),
                "total_inr": details.get("total_amount_inr"),
            },
        )

        return {
            "status": "EXECUTED",
            "receipt": {
                "order_id": primary_order_id,
                "order_number": details.get("order_number") or f"ORD-{primary_order_id}",
                "status": str(details.get("tracking_status") or order_res.get("status") or "SUBMITTED").upper(),
                "pharmacy_name": details.get("pharmacy_name") or "Pharmacy",
                "total_inr": details.get("total_amount_inr"),
                "delivery_address": delivery_address,
                "created_at": details.get("created_at"),
            },
            "next_safe_actions": ["track_order", "view_order_inbox", "set_refill_reminder"],
        }

