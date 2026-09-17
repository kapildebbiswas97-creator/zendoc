from zendoc.agent_autonomy import (
    AUTOMATIC,
    AUTOMATIC_SANDBOX,
    CRITICAL_BLOCKED,
    OWNER_APPROVAL_REQUIRED,
    UNKNOWN_ACTION,
    USER_CONFIRMATION_REQUIRED,
    bounded_autonomy_manifest,
    classify_agent_action,
)


def test_booking_agent_can_research_but_not_finalize_without_confirmation():
    assert classify_agent_action("BookingAgent", "search")["decision"] == AUTOMATIC
    assert classify_agent_action("BookingAgent", "compare")["decision"] == AUTOMATIC
    assert classify_agent_action("BookingAgent", "prepare_booking")["decision"] == AUTOMATIC

    final = classify_agent_action("BookingAgent", "confirm_booking")
    assert final["decision"] == USER_CONFIRMATION_REQUIRED
    assert final["can_execute_now"] is False
    assert final["human_gate"] == "explicit_user_confirmation"


def test_commerce_agent_can_prepare_checkout_but_never_execute_payment():
    assert classify_agent_action("CommerceAgent", "search")["decision"] == AUTOMATIC
    assert classify_agent_action("CommerceAgent", "stage_cart")["decision"] == AUTOMATIC
    assert classify_agent_action("CommerceAgent", "prepare_checkout")["decision"] == AUTOMATIC

    payment = classify_agent_action("CommerceAgent", "execute_payment")
    assert payment["decision"] == CRITICAL_BLOCKED
    assert payment["can_execute_now"] is False


def test_model_improvement_is_sandboxed_and_cannot_self_promote_or_deploy():
    proposal = classify_agent_action("ModelImprovementAgent", "propose_model_candidate")
    assert proposal["decision"] == AUTOMATIC_SANDBOX
    assert proposal["can_execute_now"] is True

    promotion = classify_agent_action("ModelImprovementAgent", "promote_model_candidate")
    assert promotion["decision"] == OWNER_APPROVAL_REQUIRED
    assert promotion["can_execute_now"] is False

    assert classify_agent_action("ModelImprovementAgent", "self_promote_model")["decision"] == CRITICAL_BLOCKED
    assert classify_agent_action("ModelImprovementAgent", "self_modify_production_code")["decision"] == CRITICAL_BLOCKED
    assert classify_agent_action("ModelImprovementAgent", "disable_safety")["decision"] == CRITICAL_BLOCKED
    assert classify_agent_action("ModelImprovementAgent", "deploy_production")["decision"] == CRITICAL_BLOCKED


def test_clinical_and_secret_boundaries_are_hard_blocked():
    for action in (
        "diagnose",
        "prescribe",
        "change_medication",
        "change_dose",
        "substitute_medicine",
        "dispatch_emergency",
        "read_server_secret",
        "expand_own_permissions",
    ):
        decision = classify_agent_action("CareAgent", action)
        assert decision["decision"] == CRITICAL_BLOCKED
        assert decision["can_execute_now"] is False


def test_unknown_action_fails_closed():
    decision = classify_agent_action("BookingAgent", "do_something_new_and_unregistered")
    assert decision["decision"] == UNKNOWN_ACTION
    assert decision["can_execute_now"] is False
    assert decision["human_gate"] == "policy_registration_required"


def test_manifest_exposes_specialized_domain_agents_and_browser_pattern():
    manifest = bounded_autonomy_manifest()
    domains = manifest["domain_agents"]
    assert domains["booking"] == "BookingAgent"
    assert domains["commerce"] == "CommerceAgent"
    assert domains["fitness"] == "FitnessAgent"
    assert domains["prevention"] == "PreventionAgent"
    assert domains["lifecycle"] == "LifecycleAgent"
    assert domains["learning"] == "LearningAgent"
    assert domains["model_improvement"] == "ModelImprovementAgent"
    assert "human gate" in manifest["browser_like_pattern"]
    assert "never execute payment" in manifest["payment_policy"].lower()
