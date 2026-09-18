from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _template(name: str) -> str:
    return (ROOT / "templates" / name).read_text(encoding="utf-8")


def test_patient_dashboard_surfaces_wellness_and_identity_readiness():
    body = _template("dashboard.html")
    assert "Mental Wellness &amp; Awareness" in body
    assert "Identity &amp; eKYC Readiness" in body
    assert "#mental-awareness" in body
    assert "#identity-trust" in body


def test_mental_wellness_has_four_life_stage_surfaces_and_safety_boundary():
    body = _template("ai.html")
    for label in ("Students", "Professionals", "Adults &amp; Parents", "Older Adults"):
        assert label in body
    assert "Non-diagnostic" in body
    assert "does not perform personality scoring" in body


def test_identity_readiness_does_not_claim_live_ekyc():
    body = _template("health_access.html")
    assert 'id="identity-trust"' in body
    assert "Integration required" in body
    assert "Not verified" in body
    assert "does not" in body and "claim a live Aadhaar" in body
    assert "Identity consent does not grant medical-record access" in body
