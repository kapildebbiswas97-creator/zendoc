from scripts.verify_deployment import is_liveness_response


def test_current_liveness_shape_is_accepted():
    assert is_liveness_response(
        200,
        {"status": "ok", "service": "zendoc", "check": "liveness"},
    ) is True


def test_legacy_liveness_shape_is_accepted_during_rollout():
    assert is_liveness_response(
        200,
        {"status": "ok", "service": "zendoc"},
    ) is True


def test_wrong_service_or_http_status_is_rejected():
    assert is_liveness_response(503, {"status": "ok", "service": "zendoc"}) is False
    assert is_liveness_response(200, {"status": "ok", "service": "other"}) is False
    assert is_liveness_response(200, {"status": "degraded", "service": "zendoc"}) is False


def test_unknown_check_value_is_rejected():
    assert is_liveness_response(
        200,
        {"status": "ok", "service": "zendoc", "check": "readiness"},
    ) is False
