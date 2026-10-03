from zendoc.personal_agents import (
    personal_agent_manifest,
    personal_agent_snapshot,
    route_personal_agent,
)


def test_patient_personal_agent_delegates_without_permission_expansion():
    actor = {"id": 42, "role": "patient", "active": 1}
    snapshot = personal_agent_snapshot(actor)
    assert snapshot["personal_agent_id"] == "zendoc-personal:patient:42"
    assert snapshot["permission_expansion"] is False
    delegate_ids = {item["identifier"] for item in snapshot["available_delegates"]}
    assert "ProviderDiscoveryAgent" in delegate_ids
    assert "HealthMemoryAgent" in delegate_ids
    assert "OperationsAgent" not in delegate_ids

    route = route_personal_agent(actor, "provider_discovery")
    assert route["delegated_agent"] == "ProviderDiscoveryAgent"
    assert "search_healthcare_providers" in route["candidate_tools"]
    assert "get_platform_summary" not in route["candidate_tools"]
    assert route["permission_expansion"] is False


def test_owner_personal_agent_has_operations_coordinator_metadata():
    actor = {"id": 1, "role": "admin", "active": 1}
    snapshot = personal_agent_snapshot(actor)
    assert snapshot["display_name"] == "My ZENDOC Founder / Owner Agent"
    assert "OperationsAgent" in {item["identifier"] for item in snapshot["available_delegates"]}
    route = route_personal_agent(actor, "operations_automation")
    assert route["delegated_agent"] == "OperationsAgent"
    assert "run_safe_operations_automation" in route["candidate_tools"]


def test_personal_agent_manifest_covers_every_supported_account_role():
    manifest = personal_agent_manifest()
    assert {"patient", "doctor", "hospital", "pharmacy", "government", "admin"} <= set(manifest["roles"])
    assert "never" not in manifest["permission_rule"].lower() or "permissions" in manifest["permission_rule"].lower()


def test_personal_agent_rejects_unauthenticated_or_unknown_role():
    failed = False
    try:
        personal_agent_snapshot({"id": 0, "role": "patient"})
    except PermissionError:
        failed = True
    assert failed is True

    failed = False
    try:
        personal_agent_snapshot({"id": 8, "role": "unknown"})
    except PermissionError:
        failed = True
    assert failed is True
