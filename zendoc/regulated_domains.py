"""Regulatory expansion map for ZENDOC's post-healthcare ecosystem.

The registry prevents product code and agents from treating regulated domains as
ordinary marketplace features. ZENDOC may provide education, discovery and
partner hand-offs before it holds the licences/authorisations required to execute
regulated activities itself.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


DISCOVERY_ONLY = "DISCOVERY_ONLY"
PARTNER_EXECUTION = "PARTNER_EXECUTION"
LICENSE_REQUIRED = "LICENSE_REQUIRED"
ZENDOC_OWNED_ALLOWED = "ZENDOC_OWNED_ALLOWED"


@dataclass(frozen=True)
class RegulatedDomain:
    domain_id: str
    name: str
    regulator: str
    initial_mode: str
    long_term_mode: str
    allowed_now: tuple[str, ...]
    blocked_without_authority: tuple[str, ...]
    patient_data_use: str
    notes: str

    def to_dict(self) -> dict:
        data = asdict(self)
        data["allowed_now"] = list(self.allowed_now)
        data["blocked_without_authority"] = list(self.blocked_without_authority)
        return data


DOMAINS: tuple[RegulatedDomain, ...] = (
    RegulatedDomain(
        domain_id="health_commerce",
        name="Nutrition, Food, Water & Health Commerce",
        regulator="FSSAI + consumer protection authorities",
        initial_mode=ZENDOC_OWNED_ALLOWED,
        long_term_mode=ZENDOC_OWNED_ALLOWED,
        allowed_now=(
            "evidence_based_product_discovery",
            "price_comparison",
            "ingredient_and_nutrition_comparison",
            "general_fitness_nutrition_guidance",
            "marketplace_checkout_via_authorized_payment_partner",
        ),
        blocked_without_authority=(
            "unsupported_health_claims",
            "diagnosis_or_treatment_claims_for_food",
            "paid_ranking_that_changes_medical_suitability",
            "hidden_sponsorship",
        ),
        patient_data_use="Only with explicit consent; minimum necessary data. Medical data must not be sold to food or beverage advertisers.",
        notes="Recommendations must distinguish general wellness from clinical nutrition and preserve evidence/provenance for health-related claims.",
    ),
    RegulatedDomain(
        domain_id="payments",
        name="ZENDOC Pay",
        regulator="Reserve Bank of India / NPCI",
        initial_mode=PARTNER_EXECUTION,
        long_term_mode=LICENSE_REQUIRED,
        allowed_now=(
            "embedded_checkout",
            "upi_intent_or_collect_via_authorized_partner",
            "hospital_and_pharmacy_payment_orchestration",
            "refund_status_and_receipt_tracking",
            "scheme_insurance_patient_split_payment_display",
        ),
        blocked_without_authority=(
            "operate_unlicensed_payment_system",
            "hold_customer_funds_as_wallet",
            "payment_aggregation_without_required_authorization",
            "misrepresent_zendoc_as_bank",
        ),
        patient_data_use="Payments receive the minimum transaction context; clinical records are not exposed to payment partners unless strictly necessary and consented.",
        notes="Make payments feel native while settlement and regulated money movement remain with authorized banks/PSPs/PAs until ZENDOC obtains the relevant approvals.",
    ),
    RegulatedDomain(
        domain_id="insurance",
        name="Insurance & Coverage Marketplace",
        regulator="IRDAI",
        initial_mode=PARTNER_EXECUTION,
        long_term_mode=LICENSE_REQUIRED,
        allowed_now=(
            "policy_document_organization",
            "coverage_discovery",
            "public_product_education",
            "claim_readiness_checklist",
            "authorized_partner_handoff",
        ),
        blocked_without_authority=(
            "unlicensed_solicitation",
            "unlicensed_policy_comparison_for_lead_sale",
            "false_coverage_confirmation",
            "claims_approval_impersonation",
        ),
        patient_data_use="User-authorized policy and claim data only; no insurer may receive unrelated medical history.",
        notes="Choose an IRDAI-compliant partner model first. A future corporate-agent/web-aggregator/broker route requires separate legal structure and approval analysis.",
    ),
    RegulatedDomain(
        domain_id="investments",
        name="Health & Public-Sector Investing",
        regulator="SEBI + RBI for Government Securities",
        initial_mode=PARTNER_EXECUTION,
        long_term_mode=LICENSE_REQUIRED,
        allowed_now=(
            "financial_education",
            "health_sector_market_information",
            "government_security_education",
            "rbi_retail_direct_guidance",
            "sebi_registered_partner_handoff",
        ),
        blocked_without_authority=(
            "personalized_buy_sell_recommendations_without_required_registration",
            "execute_stock_trades_without_registered_intermediary",
            "use_patient_health_data_for_trading_or_investment_targeting",
            "guaranteed_return_claims",
            "market_manipulation",
        ),
        patient_data_use="Patient health data is categorically separated from investment profiling and must never drive securities recommendations.",
        notes="ZENDOC may later support regulated investing through a SEBI-registered partner or its own approved entity. Government securities should use RBI-authorized rails such as Retail Direct or approved intermediaries.",
    ),
)


def list_regulated_domains() -> list[dict]:
    return [domain.to_dict() for domain in DOMAINS]


def get_regulated_domain(domain_id: str) -> dict | None:
    normalized = str(domain_id or "").strip().lower()
    for domain in DOMAINS:
        if domain.domain_id == normalized:
            return domain.to_dict()
    return None


def action_policy(domain_id: str, action: str) -> dict:
    domain = get_regulated_domain(domain_id)
    if not domain:
        return {"allowed": False, "status": "UNKNOWN_DOMAIN"}

    normalized_action = str(action or "").strip().lower()
    if normalized_action in {item.lower() for item in domain["blocked_without_authority"]}:
        return {
            "allowed": False,
            "status": "REGULATORY_GATE",
            "domain_id": domain_id,
            "regulator": domain["regulator"],
        }
    if normalized_action in {item.lower() for item in domain["allowed_now"]}:
        return {
            "allowed": True,
            "status": domain["initial_mode"],
            "domain_id": domain_id,
        }
    return {
        "allowed": False,
        "status": "UNREVIEWED_ACTION",
        "domain_id": domain_id,
    }
