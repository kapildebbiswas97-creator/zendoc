from html import unescape

from tests.test_milestone1 import make_app


def test_public_footer_does_not_imply_unverified_corporate_status(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    response = client.get("/showcase")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    decoded = unescape(text)
    assert "ZENDOC Inc." not in decoded
    assert "zendoc inc." not in decoded.lower()
    assert "© 2026 ZENDOC." in decoded
