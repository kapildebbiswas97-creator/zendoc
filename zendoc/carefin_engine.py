"""ZENDOC CareFin Engine v1.

CareFin discovers possible healthcare support pathways without claiming personal
eligibility, approval, balance, or payment. Public-source discovery is automatic;
personal coverage confirmation requires authoritative evidence.

The engine is intentionally deterministic and provider-neutral so it works with
zero LLM configuration and can later accept official/partner adapters.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .benefit_sources import get_source, list_sources


DISCOVERED = "DISCOVERED"
POTENTIALLY_ELIGIBLE = "POTENTIALLY_ELIGIBLE"
EVIDENCE_RECEIVED = "EVIDENCE_RECEIVED"
VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED"
CONFIRMED = "CONFIRMED"
APPROVED = "APPROVED"
PAID = "PAID"
REJECTED = "REJECTED"
EXPIRED = "EXPIRED"

CARE_FIN_STATES = {
    DISCOVERED,
    POTENTIALLY_ELIGIBLE,
    EVIDENCE_RECEIVED,
    VERIFICATION_REQUIRED,
    CONFIRMED,
    APPROVED,
    PAID,
    REJECTED,
    EXPIRED,
}

AUTHORITATIVE_EVIDENCE_TYPES = {
    "OFFICIAL_API",
    "GOVERNMENT_RESPONSE",
    "INSURER_RESPONSE",
    "EMPLOYER_RESPONSE",
    "TRUST_APPROVAL",
    "CSR_APPROVAL",
    "HOSPITAL_FINANCIAL_AID_RESPONSE",
}

_ALLOWED_TRANSITIONS = {
    DISCOVERED: {POTENTIALLY_ELIGIBLE, EVIDENCE_RECEIVED, VERIFICATION_REQUIRED, REJECTED, EXPIRED},
    POTENTIALLY_ELIGIBLE: {EVIDENCE_RECEIVED, VERIFICATION_REQUIRED, REJECTED, EXPIRED},
    EVIDENCE_RECEIVED: {VERIFICATION_REQUIRED, CONFIRMED, REJECTED, EXPIRED},
    VERIFICATION_REQUIRED: {CONFIRMED, REJECTED, EXPIRED},
    CONFIRMED: {APPROVED, REJECTED, EXPIRED},
    APPROVED: {PAID, REJECTED, EXPIRED},
    PAID: set(),
    REJECTED: set(),
    EXPIRED: set(),
}


@dataclass(frozen=True)
class CareFinContext:
    geography: str = "INDIA"
    state: str | None = None
    district: str | None = None
    age: int | None = None
    occupation: str | None = None
    employment_type: str | None = None
    income_band: str | None = None
    government_category: str | None = None
    existing_insurer: str | None = None
    employer_name: str | None = None
    needs_charitable_support: bool = False
    desired_categories: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "CareFinContext":
        data = data or {}
        state = _clean(data.get("state"))
        geography = _normalize_geography(data.get("geography") or state or "INDIA")
        try:
            age = int(data["age"]) if data.get("age") not in (None, "") else None
        except (TypeError, ValueError):
            age = None
        return cls(
            geography=geography,
            state=state,
            district=_clean(data.get("district")),
            age=age,
            occupation=_clean(data.get("occupation")),
            employment_type=_clean(data.get("employment_type")),
            income_band=_clean(data.get("income_band")),
            government_category=_clean(data.get("government_category")),
            existing_insurer=_clean(data.get("existing_insurer")),
            employer_name=_clean(data.get("employer_name")),
            needs_charitable_support=_bool(data.get("needs_charitable_support")),
            desired_categories=tuple(
                str(item).strip().lower()
                for item in (data.get("desired_categories") or ())
                if str(item).strip()
            ),
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        data["desired_categories"] = list(self.desired_categories)
        return data


@dataclass(frozen=True)
class BenefitCandidate:
    source_id: str
    source_name: str
    owner: str
    official_url: str
    source_type: str
    integration_status: str
    geography: str
    categories: tuple[str, ...]
    state: str
    score: int
    reasons: tuple[str, ...]
    missing_information: tuple[str, ...]
    evidence_to_verify: tuple[str, ...]
    verification_next_step: str
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in ("categories", "reasons", "missing_information", "evidence_to_verify"):
            data[key] = list(data[key])
        return data


def discover_benefits(context: dict[str, Any] | CareFinContext | None = None) -> dict:
    """Return truthful benefit candidates without asserting eligibility."""
    ctx = context if isinstance(context, CareFinContext) else CareFinContext.from_mapping(context)
    requested_categories = set(ctx.desired_categories)
    sources = list_sources(geography=ctx.geography)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    candidates: list[BenefitCandidate] = []
    for source in sources:
        score, reasons = _score_source(source, ctx, requested_categories)
        if score <= 0:
            continue
        missing = _missing_information(source, ctx)
        evidence = _evidence_requirements(source)
        state = POTENTIALLY_ELIGIBLE if score >= 4 and not missing else DISCOVERED
        candidates.append(
            BenefitCandidate(
                source_id=source["source_id"],
                source_name=source["name"],
                owner=source["owner"],
                official_url=source["official_url"],
                source_type=source["source_type"],
                integration_status=source["integration_status"],
                geography=source["geography"],
                categories=tuple(source["categories"]),
                state=state,
                score=score,
                reasons=tuple(reasons),
                missing_information=tuple(missing),
                evidence_to_verify=tuple(evidence),
                verification_next_step=_verification_next_step(source, missing),
                provenance={
                    "source_registry": "zendoc.benefit_sources",
                    "source_id": source["source_id"],
                    "official_url": source["official_url"],
                    "discovered_at": now,
                    "personal_coverage_confirmed": False,
                },
            )
        )

    candidates.sort(key=lambda item: (-item.score, item.source_name.lower()))
    return {
        "status": "OK",
        "coverage_confirmed": False,
        "context": ctx.to_dict(),
        "candidate_count": len(candidates),
        "candidates": [candidate.to_dict() for candidate in candidates],
        "disclaimer": (
            "These are possible support pathways, not confirmed eligibility or approval. "
            "Personal coverage must be verified through the official authority, insurer, employer, hospital, or funding partner."
        ),
        "generated_at": now,
    }


def transition_coverage_state(
    *,
    source_id: str,
    current_state: str,
    target_state: str,
    evidence_type: str | None = None,
    authoritative_confirmation: bool = False,
    evidence_reference: str | None = None,
) -> dict:
    """Validate a coverage state transition without allowing AI-only approval."""
    source = get_source(source_id)
    if not source:
        raise LookupError(f"Unknown CareFin source '{source_id}'.")

    current = str(current_state or "").strip().upper()
    target = str(target_state or "").strip().upper()
    evidence = str(evidence_type or "").strip().upper() or None
    reference = str(evidence_reference or "").strip() or None

    if current not in CARE_FIN_STATES or target not in CARE_FIN_STATES:
        raise ValueError("Unknown CareFin coverage state.")
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"Invalid CareFin state transition: {current} -> {target}.")

    if target in {CONFIRMED, APPROVED, PAID}:
        if not authoritative_confirmation:
            raise PermissionError(
                f"{target} requires authoritative confirmation; AI reasoning or public discovery is insufficient."
            )
        if evidence not in AUTHORITATIVE_EVIDENCE_TYPES:
            raise PermissionError(
                f"{target} requires an accepted authoritative evidence type."
            )
        if not reference:
            raise PermissionError(
                f"{target} requires an authoritative response/reference identifier for auditability."
            )

    if target == PAID and current != APPROVED:
        raise ValueError("PAID can only follow APPROVED.")

    return {
        "source_id": source_id,
        "source_name": source["name"],
        "previous_state": current,
        "state": target,
        "evidence_type": evidence,
        "evidence_reference": reference,
        "authoritative_confirmation": bool(authoritative_confirmation),
        "coverage_confirmed": target in {CONFIRMED, APPROVED, PAID},
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _score_source(source: dict, ctx: CareFinContext, requested_categories: set[str]) -> tuple[int, list[str]]:
    categories = {str(item).lower() for item in source.get("categories", [])}
    score = 1
    reasons = ["Official/public source is relevant to healthcare support discovery in the selected geography."]

    if source["geography"] != "INDIA":
        if _normalize_geography(ctx.state or ctx.geography) == source["geography"]:
            score += 4
            reasons.append("State-specific source matches the user's selected state.")
        else:
            return 0, []

    if requested_categories and requested_categories.intersection(categories):
        score += 3
        reasons.append("Source category matches the requested support type.")

    source_id = source["source_id"]
    occupation = (ctx.occupation or "").lower()
    employment = (ctx.employment_type or "").lower()
    insurer = (ctx.existing_insurer or "").lower()

    if source_id == "cghs":
        if "government" in occupation or "government" in employment or "central" in employment:
            score += 5
            reasons.append("Government employment context may make CGHS discovery relevant.")
        else:
            score -= 1

    if source_id == "lic":
        if "lic" in insurer:
            score += 5
            reasons.append("User reported an existing LIC relationship; policy verification may be relevant.")
        elif ctx.existing_insurer:
            score += 1
            reasons.append("User reported existing insurance; insurer-specific verification may be relevant.")

    if source_id in {"ngo_darpan", "mca_csr"}:
        if ctx.needs_charitable_support:
            score += 5
            reasons.append("User requested charitable/CSR support discovery.")
        else:
            score -= 1

    if source_id in {"pmjay", "swasthya_sathi", "myscheme"}:
        score += 2
        reasons.append("Government healthcare/scheme discovery is broadly relevant before out-of-pocket payment.")

    if source_id == "abdm":
        score = max(score, 1)
        reasons.append("ABDM is an interoperability/consent source, not itself proof of financial coverage.")

    return max(score, 0), reasons


def _missing_information(source: dict, ctx: CareFinContext) -> list[str]:
    missing: list[str] = []
    source_id = source["source_id"]

    if not ctx.state and source["geography"] != "INDIA":
        missing.append("state")
    if source_id in {"myscheme", "pmjay", "swasthya_sathi"}:
        for name, value in (
            ("age", ctx.age),
            ("occupation", ctx.occupation),
            ("income_band", ctx.income_band),
        ):
            if value in (None, ""):
                missing.append(name)
    if source_id == "cghs" and not (ctx.occupation or ctx.employment_type):
        missing.append("government_employment_status")
    if source_id == "lic" and not ctx.existing_insurer:
        missing.append("existing_insurer_or_policy_evidence")
    if source_id in {"ngo_darpan", "mca_csr"} and not ctx.district:
        missing.append("district")
    return missing


def _evidence_requirements(source: dict) -> list[str]:
    source_id = source["source_id"]
    if source_id in {"pmjay", "swasthya_sathi", "myscheme"}:
        return [
            "official beneficiary/eligibility response when available",
            "identity/residence/income/category documents requested by the official scheme",
        ]
    if source_id == "cghs":
        return ["official CGHS entitlement/card or authorized government response"]
    if source_id == "lic":
        return ["user-authorized policy document or insurer response"]
    if source_id in {"ngo_darpan", "mca_csr"}:
        return ["written acceptance/approval from the funding organization or implementing agency"]
    if source_id == "abdm":
        return ["ABDM-compliant consent and authorized health-information exchange response"]
    return ["authoritative response from the source owner or authorized partner"]


def _verification_next_step(source: dict, missing: list[str]) -> str:
    if missing:
        return "Collect the missing information, then re-run discovery before requesting official verification."
    return (
        f"Use the official source ({source['official_url']}) or an authorized partner integration to verify personal eligibility/coverage."
    )


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _normalize_geography(value: Any) -> str:
    text = str(value or "INDIA").strip().upper().replace(" ", "_")
    aliases = {
        "WB": "WEST_BENGAL",
        "WESTBENGAL": "WEST_BENGAL",
        "WEST_BENGAL": "WEST_BENGAL",
        "INDIA": "INDIA",
    }
    return aliases.get(text, text)
