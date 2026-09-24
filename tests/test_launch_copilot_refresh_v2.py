from pathlib import Path

from tests.test_milestone1 import login_web, make_client, register_web


ROOT = Path(__file__).resolve().parents[1]


def test_refreshed_copilot_keeps_business_and_referral_surfaces(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "copilot-business@example.com", "Copilot Business")
    login_web(client, "patient", "copilot-business@example.com")

    shop = client.get("/health-shop")

    assert shop.status_code == 200
    assert b"ZENDOC for Business" in shop.data
    assert b"Referral model" in shop.data
    assert b"Attribution without fake revenue" in shop.data


def test_base_shell_keeps_business_navigation_while_adding_copilot():
    base = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")

    assert "business.business_page" in base
    assert 'components/_copilot.html' in base
    assert "launch-ai.css" in base
    assert "copilot.js" in base
