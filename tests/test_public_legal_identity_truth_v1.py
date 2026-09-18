from tests.test_milestone1 import make_app


def test_public_footer_does_not_imply_unverified_corporate_status(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    response = client.get("/showcase")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "ZENDOC Inc." not in text
    assert "zendoc inc." not in text.lower()
    assert "© 2026 ZENDOC." in text
