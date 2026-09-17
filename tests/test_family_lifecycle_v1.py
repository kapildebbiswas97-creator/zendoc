from zendoc.family_lifecycle import age_band, family_program_catalog, member_lifecycle, payment_readiness


def test_family_lifecycle_age_bands_are_deterministic():
    assert age_band(0)["id"] == "early_childhood"
    assert age_band(5)["id"] == "preschool"
    assert age_band(11)["id"] == "child"
    assert age_band(17)["id"] == "adolescent"
    assert age_band(18)["id"] == "young_adult"
    assert age_band(64)["id"] == "midlife"
    assert age_band(65)["id"] == "older_adult"
    assert age_band(None)["id"] == "unknown"


def test_remote_parent_gets_remote_family_program_without_permission_escalation():
    member = member_lifecycle({
        "id": 1,
        "member_name": "Parent",
        "relationship": "mother",
        "age": 68,
        "gender": "female",
        "is_remote_parent": 1,
    })
    assert "remote_family" in member["care_program_ids"]
    assert "older_adult_support" in member["care_program_ids"]
    assert member["pregnancy_inferred"] is False


def test_pregnancy_is_never_inferred_from_gender_age_or_relationship():
    member = member_lifecycle({
        "relationship": "spouse",
        "age": 28,
        "gender": "female",
    })
    assert "maternity_newborn" not in member["care_program_ids"]
    assert member["explicit_care_context"] is None
    assert member["pregnancy_inferred"] is False


def test_maternity_program_requires_explicit_care_context():
    member = member_lifecycle({
        "relationship": "spouse",
        "age": 28,
        "gender": "female",
        "care_context": "pregnancy",
    })
    assert "maternity_newborn" in member["care_program_ids"]
    assert member["explicit_care_context"] == "pregnancy"
    assert member["pregnancy_inferred"] is False


def test_family_programs_are_catalog_categories_not_fake_paid_subscriptions():
    programs = family_program_catalog()
    assert programs
    assert all(program["subscription_available"] is False for program in programs)


def test_payment_readiness_is_non_executable_until_real_provider_exists():
    payment = payment_readiness()
    assert payment["status"] == "not_configured"
    assert payment["billing_provider"] is None
    assert payment["payment_execution_enabled"] is False
    assert payment["methods"]
    assert all(method["collect_in_zendoc"] is False for method in payment["methods"])
    assert all(method["integration_status"] != "connected" for method in payment["methods"])
