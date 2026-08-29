"""Fixed, claim-conscious candidate registry for the ZENDOC Model Evaluation Lab."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass


MODEL_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
LOCAL_MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
SUPPORTED_PROVIDERS = {"ollama", "openai_compatible"}
UNVERIFIED = "UNVERIFIED — verify the upstream model card and license before evaluation or adaptation."


@dataclass(frozen=True)
class ModelCandidate:
    model_id: str
    display_name: str
    family: str
    parameter_class: str
    quantization: str
    provider: str
    local_model_name: str
    license_name: str
    license_reference: str
    context_window: int | None
    structured_output_support: str
    tool_call_support: str
    multilingual_notes: str
    hardware_notes: str
    intended_use_notes: str
    medical_claim_status: str
    enabled_for_evaluation: bool
    development_baseline: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


_CANDIDATES = (
    ModelCandidate(
        model_id="phi4-mini-dev-baseline",
        display_name="Phi-4 Mini 3.8B Development Baseline",
        family="Phi",
        parameter_class="3.8B",
        quantization="Operator-selected local runtime artifact; not asserted by ZENDOC",
        provider="ollama",
        local_model_name="phi4-mini:3.8b",
        license_name="Upstream license verification required",
        license_reference=UNVERIFIED,
        context_window=None,
        structured_output_support="Runtime schema supported; candidate adherence not yet evaluated",
        tool_call_support="Not enabled in ZENDOC evaluation",
        multilingual_notes="Unverified; Bengali, Hinglish, and plain-English quality require evaluation",
        hardware_notes="Development baseline only; benchmark one candidate sequentially with conservative limits",
        intended_use_notes="Low-risk evaluation baseline, not diagnosis, prescribing, emergency decision-making, or autonomous execution",
        medical_claim_status="No ZENDOC medical-training, certification, or clinical-validation claim",
        enabled_for_evaluation=True,
        development_baseline=True,
    ),
    ModelCandidate(
        model_id="qwen-small-example",
        display_name="Qwen Small-Family Example",
        family="Qwen",
        parameter_class="Small class — exact artifact unverified",
        quantization="Unverified",
        provider="ollama",
        local_model_name="qwen3:4b",
        license_name="Upstream license verification required",
        license_reference=UNVERIFIED,
        context_window=None,
        structured_output_support="Unverified",
        tool_call_support="Not enabled in ZENDOC evaluation",
        multilingual_notes="Unverified; must be measured rather than assumed",
        hardware_notes="Placeholder only; operator must review model size and laptop suitability",
        intended_use_notes="Potential future base-model comparison only",
        medical_claim_status="No medical-training, certification, or clinical-validation claim",
        enabled_for_evaluation=False,
    ),
    ModelCandidate(
        model_id="gemma-small-example",
        display_name="Gemma Small-Family Example",
        family="Gemma",
        parameter_class="Small class — exact artifact unverified",
        quantization="Unverified",
        provider="ollama",
        local_model_name="gemma3:4b",
        license_name="Upstream license verification required",
        license_reference=UNVERIFIED,
        context_window=None,
        structured_output_support="Unverified",
        tool_call_support="Not enabled in ZENDOC evaluation",
        multilingual_notes="Unverified; must be measured rather than assumed",
        hardware_notes="Placeholder only; operator must review model size and laptop suitability",
        intended_use_notes="Potential future base-model comparison only",
        medical_claim_status="No medical-training, certification, or clinical-validation claim",
        enabled_for_evaluation=False,
    ),
    ModelCandidate(
        model_id="llama-small-example",
        display_name="Llama Small-Family Example",
        family="Llama",
        parameter_class="Small class — exact artifact unverified",
        quantization="Unverified",
        provider="ollama",
        local_model_name="llama3.2:3b",
        license_name="Upstream license verification required",
        license_reference=UNVERIFIED,
        context_window=None,
        structured_output_support="Unverified",
        tool_call_support="Not enabled in ZENDOC evaluation",
        multilingual_notes="Unverified; must be measured rather than assumed",
        hardware_notes="Placeholder only; operator must review model size and laptop suitability",
        intended_use_notes="Potential future base-model comparison only",
        medical_claim_status="No medical-training, certification, or clinical-validation claim",
        enabled_for_evaluation=False,
    ),
)


def validate_candidate(candidate: ModelCandidate) -> ModelCandidate:
    if not MODEL_ID_PATTERN.fullmatch(candidate.model_id):
        raise ValueError("Candidate model_id is invalid.")
    if candidate.provider not in SUPPORTED_PROVIDERS:
        raise ValueError("Candidate provider is not supported.")
    if not LOCAL_MODEL_PATTERN.fullmatch(candidate.local_model_name) or ".." in candidate.local_model_name:
        raise ValueError("Candidate local model name is invalid.")
    if candidate.context_window is not None and not 128 <= candidate.context_window <= 10_000_000:
        raise ValueError("Candidate context window is invalid.")
    for value in (
        candidate.display_name,
        candidate.family,
        candidate.parameter_class,
        candidate.license_name,
        candidate.license_reference,
        candidate.intended_use_notes,
        candidate.medical_claim_status,
    ):
        if not str(value or "").strip() or len(str(value)) > 1_000:
            raise ValueError("Candidate metadata is incomplete or too long.")
    return candidate


def list_model_candidates(*, enabled_only: bool = False) -> list[dict]:
    candidates = [validate_candidate(candidate) for candidate in _CANDIDATES]
    if enabled_only:
        candidates = [candidate for candidate in candidates if candidate.enabled_for_evaluation]
    return [candidate.to_dict() for candidate in candidates]


def get_model_candidate(model_id: str, *, enabled_only: bool = False) -> dict:
    normalized = str(model_id or "").strip().lower()
    if not MODEL_ID_PATTERN.fullmatch(normalized):
        raise ValueError("Candidate identifier is invalid.")
    for candidate in _CANDIDATES:
        if candidate.model_id == normalized:
            validate_candidate(candidate)
            if enabled_only and not candidate.enabled_for_evaluation:
                raise PermissionError("Candidate is not enabled for evaluation.")
            return candidate.to_dict()
    raise LookupError("Candidate model is not registered.")


def development_baseline_candidate() -> dict:
    for candidate in _CANDIDATES:
        if candidate.development_baseline:
            return validate_candidate(candidate).to_dict()
    raise RuntimeError("No development baseline candidate is registered.")
