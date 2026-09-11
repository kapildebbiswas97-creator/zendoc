from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_base_template_loads_additive_ui_polish_and_truth_strip():
    html = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    assert "ui-polish.css" in html
    assert "experience-strip" in html
    assert "Real-world availability shown only when confirmed" in html
    assert "Public Beta" in html


def test_patient_mobile_dock_keeps_core_workflows_one_tap_away():
    html = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    assert "patient-mobile-dock" in html
    for endpoint in (
        "main.dashboard",
        "main.ai_center",
        "main.finder",
        "main.records",
        "main.appointments",
    ):
        assert endpoint in html


def test_mobile_dock_is_mobile_only_and_supports_safe_area():
    css = (ROOT / "static" / "ui-polish.css").read_text(encoding="utf-8")
    assert ".patient-mobile-dock{display:none}" in css
    assert "@media(max-width:900px)" in css
    assert "env(safe-area-inset-bottom)" in css
    assert "prefers-reduced-motion" in css
