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
