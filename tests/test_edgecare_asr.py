from zendoc.edgecare_asr import EdgeCareASR, EdgeCareASRSettings


def _settings(**overrides):
    values = {
        "enabled": True,
        "provider": "openai_compatible",
        "base_url": "http://127.0.0.1:8001",
        "model": "whisper_small",
        "timeout": 5,
        "max_audio_bytes": 1024,
        "allow_private_network": False,
    }
    values.update(overrides)
    return EdgeCareASRSettings(**values)


def test_disabled_asr_is_truthfully_reported():
    status = EdgeCareASR(_settings(enabled=False)).configuration_status()
    assert status["status"] == "disabled"
    assert status["model"] == "whisper_small"


def test_unsupported_asr_provider_is_rejected():
    status = EdgeCareASR(_settings(provider="browser_cloud")).configuration_status()
    assert status["status"] == "configuration_error"
    assert status["error_category"] == "invalid_provider"


def test_loopback_local_asr_endpoint_is_allowed():
    status = EdgeCareASR(_settings()).configuration_status()
    assert status["status"] == "configured"


def test_empty_audio_is_rejected_without_network_call():
    result = EdgeCareASR(_settings()).transcribe(b"", mimetype="audio/webm")
    assert result.success is False
    assert result.error_category == "empty_audio"


def test_unsupported_audio_type_is_rejected_without_network_call():
    result = EdgeCareASR(_settings()).transcribe(b"abc", mimetype="application/pdf")
    assert result.success is False
    assert result.error_category == "unsupported_audio_type"


def test_oversized_audio_is_rejected_without_network_call():
    result = EdgeCareASR(_settings(max_audio_bytes=4)).transcribe(b"12345", mimetype="audio/webm")
    assert result.success is False
    assert result.error_category == "audio_too_large"


def test_transcript_is_bounded_and_provider_is_local(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, _limit):
            return ('{"text":"' + ('a' * 6000) + '"}').encode("utf-8")

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())
    result = EdgeCareASR(_settings(max_audio_bytes=1024)).transcribe(
        b"audio-bytes",
        filename="clip.webm",
        mimetype="audio/webm",
    )
    assert result.success is True
    assert len(result.text) == 5000
    assert result.provider == "local_openai_compatible_asr"
