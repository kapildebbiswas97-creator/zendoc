from tests.test_milestone1 import make_app


def test_unknown_web_route_returns_branded_recovery_page(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    response = client.get("/old-zendoc-feature-that-no-longer-exists")

    assert response.status_code == 404
    assert b"Page not found" in response.data
    assert b"Search ZENDOC" in response.data
    assert b"Find Care" in response.data
    assert b"/old-zendoc-feature-that-no-longer-exists" in response.data


def test_unknown_api_route_stays_json_404(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    response = client.get("/api/v1/route-that-does-not-exist")

    assert response.status_code == 404
    assert response.is_json
    assert response.get_json() == {
        "error": {
            "code": 404,
            "message": "The requested ZENDOC API route was not found.",
        }
    }
