from zendoc.model_portfolio import get_model_role, list_model_roles, route_policy


def test_model_portfolio_has_separate_roles():
    ids = {item["role_id"] for item in list_model_roles()}
    assert {"safety", "fast_router", "private_assistant", "reasoning_planner", "document_extractor", "multilingual"} <= ids


def test_safety_role_is_deterministic_only():
    role = get_model_role("safety")
    assert role["preferred_provider_classes"] == ["deterministic"]
    assert role["cloud_allowed"] is False


def test_sensitive_health_context_never_routes_to_cloud():
    decision = route_policy(
        role_id="reasoning_planner",
        privacy_class="HEALTH_SENSITIVE",
        cloud_consent=True,
    )
    assert decision["allowed"] is True
    assert decision["cloud_allowed"] is False
    assert decision["local_first"] is True


def test_public_reasoning_can_use_cloud():
    decision = route_policy(
        role_id="reasoning_planner",
        privacy_class="PUBLIC",
        cloud_consent=False,
    )
    assert decision["cloud_allowed"] is True
