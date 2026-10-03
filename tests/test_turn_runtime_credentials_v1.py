import base64
import hashlib
import hmac
import json

import pytest

from zendoc.call_routes import _ice_servers
from zendoc.turn_credentials import dynamic_turn_ice_servers, dynamic_turn_status
from tests.test_milestone1 import make_app


def test_dynamic_turn_credentials_follow_coturn_rest_api(monkeypatch, tmp_path):
    secret = "a" * 64
    monkeypatch.setenv("ZENDOC_TURN_PUBLIC_HOST", "turn.example.test")
    monkeypatch.setenv("ZENDOC_TURN_SHARED_SECRET", secret)
    monkeypatch.setenv("ZENDOC_TURN_CREDENTIAL_TTL_SECONDS", "1800")
    app = make_app(tmp_path)
    with app.app_context():
        servers = dynamic_turn_ice_servers({"id": 42}, now=1_700_000_000)
    item = servers[0]
    assert item["username"] == "1700001800:zendoc-42"
    expected = base64.b64encode(
        hmac.new(secret.encode(), item["username"].encode(), hashlib.sha1).digest()
    ).decode()
    assert item["credential"] == expected
    assert "turn:turn.example.test:3478?transport=udp" in item["urls"]
    assert "turn:turn.example.test:3478?transport=tcp" in item["urls"]
    assert secret not in repr(item)


def test_dynamic_turn_requires_authenticated_actor_and_strong_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("ZENDOC_TURN_PUBLIC_HOST", "turn.example.test")
    monkeypatch.setenv("ZENDOC_TURN_SHARED_SECRET", "b" * 64)
    app = make_app(tmp_path)
    with app.app_context():
        assert dynamic_turn_ice_servers(None, now=1) == []
    monkeypatch.setenv("ZENDOC_TURN_SHARED_SECRET", "short")
    with app.app_context(), pytest.raises(ValueError):
        dynamic_turn_ice_servers({"id": 1}, now=1)


def test_call_ice_servers_add_dynamic_turn_without_exposing_server_secret(monkeypatch, tmp_path):
    secret = "c" * 64
    monkeypatch.setenv("ZENDOC_TURN_PUBLIC_HOST", "turn.example.test")
    monkeypatch.setenv("ZENDOC_TURN_SHARED_SECRET", secret)
    monkeypatch.setenv(
        "ZENDOC_WEBRTC_ICE_SERVERS_JSON",
        json.dumps([{"urls": "stun:stun.example.test:3478"}]),
    )
    app = make_app(tmp_path)
    with app.app_context():
        servers = _ice_servers({"id": 7})
    assert any(item["urls"] == "stun:stun.example.test:3478" for item in servers)
    assert any(
        isinstance(item["urls"], list)
        and "turn:turn.example.test:3478?transport=udp" in item["urls"]
        for item in servers
    )
    assert secret not in repr(servers)


def test_turn_status_never_discloses_secret(monkeypatch):
    monkeypatch.setenv("ZENDOC_TURN_PUBLIC_HOST", "turn.example.test")
    monkeypatch.setenv("ZENDOC_TURN_SHARED_SECRET", "d" * 64)
    status = dynamic_turn_status()
    assert status["configured"] is True
    assert "d" * 64 not in repr(status)


def test_oci_coturn_secret_is_not_exposed_in_process_arguments():
    compose = open("deploy/oci/compose.yaml", encoding="utf-8").read()
    entrypoint = open("deploy/oci/turn-entrypoint.sh", encoding="utf-8").read()
    assert "coturn/coturn:4.18.0-r0" in compose
    assert 'profiles: ["realtime"]' in compose
    assert "network_mode: host" in compose
    assert "--static-auth-secret=" not in compose
    assert "static-auth-secret=${ZENDOC_TURN_SHARED_SECRET}" in entrypoint
    assert "no-cli" not in entrypoint
    assert "no-dtls" not in entrypoint
