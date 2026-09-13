from tests.test_milestone1 import make_app


def test_showcase_is_public_and_renders_core_story(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    response = client.get("/showcase")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "Connected Care Operating System" in text
    assert "DHN HealthTech Innovation Challenge 2026" in text
    assert "IIT Kanpur" in text
    assert "Internet result ≠ verified provider" in text
    assert "Web page ≠ AI knowledge" in text
    assert "Listing ≠ live availability" in text


def test_showcase_does_not_claim_fake_live_operations(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    text = client.get("/showcase").get_data(as_text=True).lower()
    assert "all providers are verified" not in text
    assert "all pharmacy stock is live" not in text
    assert "diagnosis" not in text
