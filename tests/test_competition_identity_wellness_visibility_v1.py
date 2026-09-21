from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _template(name: str) -> str:
    return (ROOT / "templates" / name).read_text(encoding="utf-8")


def test_patient_dashboard_surfaces_one_wellness_and_identity_destination():
    body = _template("dashboard.html")
    assert "Mental Wellness &amp; Awareness" in body
    assert 'mental_wellness.mental_wellness_page' in body
    assert "#mental-awareness" not in body
    assert "Identity &amp; eKYC Readiness" in body
    assert "#identity-trust" in body


def test_mental_wellness_has_life_stage_surfaces_and_safety_boundary():
    body = _template("mental_wellness.html")
    for label in (
        "Children",
        "Teenagers",
        "Students &amp; Young Adults",
        "Working Adults",
        "Parents &amp; Caregivers",
        "Older Adults",
    ):
        assert label in body
    assert "Non-diagnostic" in body
    assert "perform personality scoring" in body
    assert "does not diagnose a mental-health condition" in body
    assert "never asks a child to handle a safety concern alone" in body


def test_ai_keeps_wellness_separate_and_uses_text_plus_voice():
    body = _template("ai.html")
    assert 'id="assistant-message"' in body
    assert 'id="edgecare-voice-input-toggle"' in body
    assert "mental_wellness.mental_wellness_page" in body
    assert 'id="mental-awareness"' not in body


def test_identity_readiness_does_not_claim_live_ekyc():
    body = _template("health_access.html")
    assert 'id="identity-trust"' in body
    assert "Integration required" in body
    assert "Not verified" in body
    assert "does not" in body and "claim a live Aadhaar" in body
    assert "Identity consent does not grant medical-record access" in body
