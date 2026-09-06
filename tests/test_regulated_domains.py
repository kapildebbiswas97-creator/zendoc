from zendoc.regulated_domains import action_policy, get_regulated_domain, list_regulated_domains


def test_core_regulated_domains_are_registered():
    ids = {item["domain_id"] for item in list_regulated_domains()}
    assert {"health_commerce", "payments", "insurance", "investments"} <= ids


def test_payment_system_operation_is_regulatory_gated():
    result = action_policy("payments", "operate_unlicensed_payment_system")
    assert result["allowed"] is False
    assert result["status"] == "REGULATORY_GATE"


def test_embedded_checkout_is_allowed_via_partner_mode():
    result = action_policy("payments", "embedded_checkout")
    assert result["allowed"] is True
    assert result["status"] == "PARTNER_EXECUTION"


def test_investment_advice_without_registration_is_blocked():
    result = action_policy(
        "investments",
        "personalized_buy_sell_recommendations_without_required_registration",
    )
    assert result["allowed"] is False


def test_patient_data_is_separated_from_investment_targeting():
    domain = get_regulated_domain("investments")
    assert "categorically separated" in domain["patient_data_use"].lower()
