"""Smoke checks for the additive Stitch frontend stylesheet.

These tests deliberately avoid importing the Flask application, external
services or user data; they protect the safe, asset-only integration boundary.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_stitch_stylesheet_is_loaded_after_existing_css():
    base = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    assert (ROOT / "static" / "stitch-refresh.css").is_file()
    existing = "filename='launch-ai.css'"
    added = "filename='stitch-refresh.css'"
    assert base.count(added) == 1
    assert base.index(existing) < base.index(added)


def test_stitch_stylesheet_has_no_prototype_runtime_or_external_dependency():
    css = (ROOT / "static" / "stitch-refresh.css").read_text(encoding="utf-8")
    for forbidden in ("cdn.tailwindcss.com", "lh3.googleusercontent.com",
                      "ABDM Integrated", "GEMINI_API_KEY", "@import url("):
        assert forbidden not in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert ".finder-shell .finder-form" in css
    assert ".landing-page .landing-hero" in css


def test_stitch_refreshed_jinja_templates_parse():
    from jinja2 import Environment
    env = Environment(autoescape=True)
    for name in ("base.html", "dashboard.html", "finder.html", "provider_detail.html"):
        env.parse((ROOT / "templates" / name).read_text(encoding="utf-8"))


def test_stitch_provider_showcase_preserves_live_booking_and_truthful_content():
    html = (ROOT / "templates" / "provider_detail.html").read_text(encoding="utf-8")
    assert 'class="stitch-provider-showcase"' in html
    assert "{{ profile.organization or profile.provider_name }}" in html
    assert "{{ profile.public_phone or 'Not published' }}" in html
    assert 'href="#booking-title"' in html
    assert "url_for('main.appointments')" in html
    assert 'name="csrf_token"' in html
    assert 'name="provider_profile_id"' in html
    assert "not a claim of government accreditation" in html
    for mock in ("Aster CMI", "NABH Golden Seal", "JCI Accredited"):
        assert mock not in html


def test_stitch_patient_dashboard_search_uses_existing_route_and_real_state():
    dashboard = (ROOT / "templates" / "dashboard.html").read_text(encoding="utf-8")
    assert 'class="stitch-patient-intro"' in dashboard
    assert "url_for('ecosystem.search_page')" in dashboard
    assert 'name="q"' in dashboard
    assert "url_for('health_memory.health_summary_page')" in dashboard
    assert "url_for('milestone7.messages_page')" in dashboard
    assert "{% if next_appointment %}" in dashboard
    assert "MOCK_ABHA_PROFILE" not in dashboard
    assert "MOCK_DOCTORS" not in dashboard


def test_stitch_finder_keeps_real_sources_search_and_map():
    finder = (ROOT / "templates" / "finder.html").read_text(encoding="utf-8")
    assert 'class="stitch-finder-intro"' in finder
    assert "url_for('universal_search.search_home')" in finder
    assert 'name="category"' in finder
    assert 'name="radius_km"' in finder
    assert 'id="finder-map"' in finder
    assert 'class="provider-card stitch-care-result"' in finder
    assert 'result.source_health' in finder
    assert "MOCK_HOSPITALS" not in finder


def test_mobile_dock_has_six_real_patient_routes():
    base = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    nav = base.split('<nav class="patient-mobile-dock"', 1)[1].split("</nav>", 1)[0]
    assert nav.count('class="mobile-dock-link') == 6
    assert "url_for('main.finder')" in nav
    assert "url_for('main.ai_center')" in nav
    assert "url_for('main.appointments')" in nav
    assert "url_for('main.records')" in nav
    assert "url_for('health_social.community_page')" in nav
    assert "aria-current=\"page\"" in nav
    assert 'href="#"' not in nav


def test_stitch_styles_cover_accessibility_and_mobile_views():
    css = (ROOT / "static" / "stitch-refresh.css").read_text(encoding="utf-8")
    for selector in (".stitch-patient-intro", ".stitch-finder-intro",
                     ".stitch-provider-showcase", ".patient-mobile-dock",
                     ".stitch-care-result", ":focus-visible"):
        assert selector in css
    assert "@media (max-width: 680px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
