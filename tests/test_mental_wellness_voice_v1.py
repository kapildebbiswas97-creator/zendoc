from pathlib import Path

from tests.test_milestone1 import login_web, make_app, register_web


ROOT = Path(__file__).resolve().parents[1]


def test_patient_mental_wellness_exposes_voice_without_auto_submit(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "wellness-voice@example.com", "Wellness Voice")
    login_web(client, "patient", "wellness-voice@example.com")

    response = client.get("/mental-wellness")

    assert response.status_code == 200
    body = response.data.decode()
    assert 'id="wellness-guidance-context"' in body
    assert 'id="wellness-voice-input-toggle"' in body
    assert 'id="wellness-voice-input-status"' in body
    assert "mental_wellness_voice.js" in body
    assert "Voice creates editable text only" in body
    assert 'href="/community"' in body
    assert "Do not post private medical or crisis details publicly." in body


def test_mental_wellness_voice_reuses_bounded_edgecare_asr_and_never_submits_form():
    script = (ROOT / "static" / "mental_wellness_voice.js").read_text(encoding="utf-8")

    assert 'const endpoint = "/edgecare/asr/transcribe"' in script
    assert "maxClientBytes = 8 * 1024 * 1024" in script
    assert "maxRecordingMs = 30 * 1000" in script
    assert 'credentials: "same-origin"' in script
    assert "BrowserSpeechRecognition" in script
    assert "appendTranscript" in script
    assert ".requestSubmit(" not in script
    assert ".submit(" not in script
    assert "Nothing is submitted automatically" in script


def test_wellness_voice_fallback_preserves_existing_typed_text():
    script = (ROOT / "static" / "mental_wellness_voice.js").read_text(encoding="utf-8")

    assert 'const existing = input.value.trim();' in script
    assert 'const combined =' in script
    assert 'existing ? " " : ""' in script
    assert "input.value = combined.slice(0, limit);" in script
