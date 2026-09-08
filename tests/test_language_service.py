from zendoc.language_service import (
    detect_language,
    safe_template,
    translation_capability,
)
from tests.test_milestone1 import api_token, make_app


def test_detects_bengali_and_hindi_scripts():
    assert detect_language("আমি ডাক্তার খুঁজছি").language == "bn"
    assert detect_language("मुझे डॉक्टर चाहिए").language == "hi"
    assert detect_language("I need a doctor").language == "en"


def test_user_preference_overrides_detection():
    result = detect_language("I need help", preferred="bn")
    assert result.language == "bn"
    assert result.source == "user_preference"


def test_safe_templates_exist_in_all_supported_languages():
    assert safe_template("not_diagnosis", "en")
    assert safe_template("not_diagnosis", "bn")
    assert safe_template("not_diagnosis", "hi")


def test_free_form_translation_is_truthful():
    same = translation_capability("en", "en")
    assert same["status"] == "WORKING"

    cross = translation_capability("bn", "en")
    assert cross["status"] == "INTEGRATION_REQUIRED"
    assert cross["provider"] is None


def test_language_preference_api_persists(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    token = api_token(client, "language-user@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    updated = client.post(
        "/api/v1/language/preference",
        json={"language": "bn"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.get_json()["language"] == "bn"

    caps = client.get("/api/v1/language/capabilities", headers=headers)
    assert caps.status_code == 200
    assert caps.get_json()["preferred_language"] == "bn"


def test_language_detect_api_does_not_require_translation_provider(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    token = api_token(client, "language-detect@example.com")
    response = client.post(
        "/api/v1/language/detect",
        json={"text": "আমি হাসপাতাল খুঁজছি"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["language"] == "bn"
    assert payload["canonical_structured_language"] == "en"
