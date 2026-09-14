from zendoc import create_app
from tests.test_milestone1 import login_web, register_web


def make_client(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "care-os.db"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "SECRET_KEY": "care-os-test-secret",
            "ADMIN_EMAIL": "owner@zendoc.local",
            "ADMIN_PASSWORD": "OwnerPassword123!",
            "RATE_LIMIT_PER_MINUTE": 1000,
        }
    )
    return app, app.test_client()


def test_care_os_requires_authentication(tmp_path):
    _app, client = make_client(tmp_path)
    response = client.get("/care-os", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_patient_care_os_renders_unified_sections(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "careos@example.com", "Care OS Patient")
    login_web(client, "patient", "careos@example.com")

    response = client.get("/care-os")
    assert response.status_code == 200
    assert b"ZENDOC Care OS" in response.data
    assert b"Next safe actions" in response.data
    assert b"CareLoop" in response.data
    assert b"Consent Wallet" in response.data
    assert b"Family Care Graph" in response.data
    assert b"Personal Baselines" in response.data
    assert b"Evidence Passport" in response.data


def test_non_patient_cannot_open_patient_care_os(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "doctor", "doctor-careos@example.com", "Care OS Doctor")
    login_web(client, "doctor", "doctor-careos@example.com")

    response = client.get("/care-os", follow_redirects=False)
    assert response.status_code == 403
