from zendoc.ai_types import IntelligenceResult
from zendoc.evaluation_dataset import load_evaluation_dataset
from zendoc.intelligence import ZendocIntelligence
from zendoc.model_evaluation import EvaluationInference, aggregate_scores, score_evaluation_case
from zendoc.model_router import ModelResponse, RoutingReason
from zendoc.slm import (
    KNOWLEDGE_LAYER_VERSION,
    SLM_VERSION,
    classify_privacy,
    knowledge_layer_status,
    retrieve_approved_knowledge,
    run_slm_product_layer,
)


class FakeRouter:
    def __init__(self, output):
        self.output = output
        self.calls = 0

    def route(self, *args, **kwargs):
        self.calls += 1
        return ModelResponse(
            text=self.output.get("text", ""),
            provider="local_ollama",
            model="synthetic-local-model",
            latency_ms=2,
            success=True,
            routing_reason=RoutingReason.LOCAL_SLM,
            output=self.output,
            task_type=kwargs.get("task_type", "general"),
            privacy_class=kwargs.get("privacy_class", "INTERNAL"),
        )


def test_approved_knowledge_is_local_and_provenance_bearing():
    records = retrieve_approved_knowledge("Where is my appointment and health timeline?", "appointment")
    assert records
    assert all(record["knowledge_layer"] == KNOWLEDGE_LAYER_VERSION for record in records)
    assert all(record["provenance"] for record in records)
    status = knowledge_layer_status()
    assert status["external_web_retrieval"] is False
    assert status["provenance_required"] is True


def test_privacy_classification_is_conservative():
    assert classify_privacy("I have chest pain", "general_assistant") == "HIGH_RISK"
    assert classify_privacy("Explain my latest report", "report_intelligence") == "HEALTH_SENSITIVE"
    assert classify_privacy("Where is my appointments page?", "general_platform_question") == "PERSONAL"


def test_emergency_gate_prevents_model_call():
    router = FakeRouter({"text": "unsafe", "data": {}})
    result = run_slm_product_layer("I have chest pain and shortness of breath", router=router)
    assert result.emergency is True
    assert result.provider_route["provider"] == "deterministic_safety"
    assert result.model_metadata["model_called"] is False
    assert router.calls == 0


def test_malformed_and_action_like_model_outputs_use_safe_fallback():
    malformed = run_slm_product_layer("What does the dashboard do?", router=FakeRouter({"text": "", "data": {}}))
    assert malformed.summary
    assert malformed.model_metadata["structured_output_validated"] is False
    assert malformed.provider_route["fallback_used"] is True

    action = run_slm_product_layer(
        "What does the dashboard do?",
        router=FakeRouter({"text": "I booked your appointment.", "data": {"tool_calls": []}}),
    )
    assert "booked" not in action.summary.lower()
    assert action.model_metadata["safety_validated"] is False


def test_general_intelligence_exposes_slm_product_metadata_without_changing_legacy_fields():
    result, _latency = ZendocIntelligence().respond("What does the ZENDOC dashboard help me navigate?")
    assert isinstance(result, IntelligenceResult)
    payload = result.to_dict()
    assert payload["message"]
    assert payload["summary"]
    assert payload["provider_route"]["layer"] == SLM_VERSION
    assert payload["model_metadata"]["product_layer"] == SLM_VERSION
    assert payload["recommended_actions"]


def test_m9_scorecard_is_safety_dominant_and_persistable_shape():
    case = next(item for item in load_evaluation_dataset()["cases"] if item["case_id"] == "injection.tool.001")
    score = score_evaluation_case(
        case,
        EvaluationInference(True, {"text": "Done", "data": {"tool_calls": []}}, 2, "synthetic", "synthetic"),
    )
    assert score.scores["action_validity"] == 0
    assert score.scores["overall"] == 0
    summary = aggregate_scores([score], mode="real_local")
    assert summary["overall_score"] == 0
    assert "relevance_score" in summary
    assert "privacy_penalty" in summary
