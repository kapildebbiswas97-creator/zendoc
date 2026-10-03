from types import SimpleNamespace

import pytest

from zendoc import agent_executor


def _plan(agent, tool_name, *, intent="test", risk_level="read_only", fallback="safe_read_only_fallback"):
    step = SimpleNamespace(sequence=1, tool_name=tool_name, arguments={})
    return SimpleNamespace(
        authorization_error=None,
        assigned_agent=agent,
        steps=(step,),
        plan_id="test-plan",
        intent=intent,
        requires_confirmation=False,
        risk_level=risk_level,
        fallback_strategy=fallback,
    )


def test_idempotent_read_only_tool_retries_once_then_succeeds(monkeypatch):
    calls = {"count": 0}

    def flaky(_actor, _arguments):
        calls["count"] += 1
        if calls["count"] == 1:
            raise TimeoutError("temporary timeout with sensitive details that must not escape")
        return {"status": "OK", "results": []}

    monkeypatch.setitem(agent_executor.TOOL_HANDLERS, "search_healthcare_providers", flaky)
    result = agent_executor.execute_plan(
        _plan("ProviderDiscoveryAgent", "search_healthcare_providers", intent="provider_discovery"),
        {"id": 7, "role": "patient"},
        retry_read_only=True,
        degrade_on_transient=True,
    )

    assert calls["count"] == 2
    assert result["status"] == "completed"
    assert result["retry_count"] == 1
    assert result["degraded"] is False
    assert result["tool_results"][0]["attempts"] == 2


def test_exhausted_read_only_transient_failure_degrades_without_raw_error(monkeypatch):
    calls = {"count": 0}

    def unavailable(_actor, _arguments):
        calls["count"] += 1
        raise ConnectionError("provider token=do-not-leak is temporarily unavailable")

    monkeypatch.setitem(agent_executor.TOOL_HANDLERS, "search_healthcare_providers", unavailable)
    result = agent_executor.execute_plan(
        _plan("ProviderDiscoveryAgent", "search_healthcare_providers", intent="provider_discovery"),
        {"id": 8, "role": "patient"},
        retry_read_only=True,
        degrade_on_transient=True,
    )

    assert calls["count"] == 2
    assert result["status"] == "degraded"
    assert result["degraded"] is True
    assert result["failure_category"] == "provider_unavailable"
    assert result["fallback_strategy"] == "safe_read_only_fallback"
    assert "do-not-leak" not in str(result)


def test_read_only_permission_denial_is_never_retried_or_degraded(monkeypatch):
    calls = {"count": 0}

    def denied(_actor, _arguments):
        calls["count"] += 1
        raise PermissionError("patient target access denied")

    monkeypatch.setitem(agent_executor.TOOL_HANDLERS, "search_healthcare_providers", denied)
    with pytest.raises(PermissionError, match="patient target access denied"):
        agent_executor.execute_plan(
            _plan("ProviderDiscoveryAgent", "search_healthcare_providers", intent="provider_discovery"),
            {"id": 11, "role": "patient"},
            retry_read_only=True,
            degrade_on_transient=True,
        )

    assert calls["count"] == 1


def test_non_idempotent_write_is_never_retried_or_silently_degraded(monkeypatch):
    calls = {"count": 0}

    def failing_write(_actor, _arguments):
        calls["count"] += 1
        raise TimeoutError("write outcome is uncertain")

    monkeypatch.setitem(agent_executor.TOOL_HANDLERS, "send_message", failing_write)
    with pytest.raises(TimeoutError):
        agent_executor.execute_plan(
            _plan("CommunicationAgent", "send_message", risk_level="low_risk"),
            {"id": 9, "role": "patient"},
            retry_read_only=True,
            degrade_on_transient=True,
        )

    assert calls["count"] == 1


def test_consent_required_tool_still_stops_before_handler(monkeypatch):
    called = {"value": False}

    def should_not_run(_actor, _arguments):
        called["value"] = True
        return {"unexpected": True}

    monkeypatch.setitem(agent_executor.TOOL_HANDLERS, "confirm_provider_booking", should_not_run)
    with pytest.raises(PermissionError, match="explicit human authorization"):
        agent_executor.execute_plan(
            _plan("BookingAgent", "confirm_provider_booking", risk_level="consent_required"),
            {"id": 10, "role": "patient"},
            retry_read_only=True,
            degrade_on_transient=True,
        )

    assert called["value"] is False
