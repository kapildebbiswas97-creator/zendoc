from tests.test_milestone1 import make_app, make_client, register_web
from zendoc.email_delivery import email_delivery_status, send_transactional_email


class _FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout, **kwargs):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.kwargs = kwargs
        self.started_tls = False
        self.logged_in = None
        self.messages = []
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def ehlo(self):
        return None

    def starttls(self, context=None):
        self.started_tls = True

    def login(self, username, password):
        self.logged_in = (username, password)

    def send_message(self, message):
        self.messages.append(message)


def test_email_status_fails_truthfully_when_not_configured(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        app.config["EMAIL_PROVIDER"] = "none"
        status = email_delivery_status()
        assert status["transactional_email"] is False
        assert status["status"] == "integration_required"


def test_smtp_delivery_uses_configured_provider(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    _FakeSMTP.instances.clear()

    with app.app_context():
        app.config.update(
            EMAIL_PROVIDER="smtp",
            SMTP_HOST="smtp.example.test",
            SMTP_PORT=587,
            SMTP_USERNAME="mailer",
            SMTP_PASSWORD="secret",
            SMTP_FROM_EMAIL="noreply@example.test",
            SMTP_USE_TLS=True,
            SMTP_USE_SSL=False,
            SMTP_TIMEOUT=10,
        )

        from zendoc import email_delivery
        monkeypatch.setattr(email_delivery.smtplib, "SMTP", _FakeSMTP)

        status = email_delivery_status()
        assert status["transactional_email"] is True
        result = send_transactional_email(
            "patient@example.test",
            "Reset your ZENDOC password",
            "Use the secure reset link.",
        )

        assert result["status"] == "sent"
        instance = _FakeSMTP.instances[-1]
        assert instance.host == "smtp.example.test"
        assert instance.started_tls is True
        assert instance.logged_in == ("mailer", "secret")
        assert len(instance.messages) == 1
        assert instance.messages[0]["To"] == "patient@example.test"


def test_password_recovery_response_does_not_enumerate_account_on_delivery_failure(tmp_path, monkeypatch):
    _app, client = make_client(tmp_path)
    existing_email = "smtp-enumeration@example.com"
    register_web(client, "patient", existing_email, "SMTP Enumeration")

    from zendoc import routes

    monkeypatch.setattr(
        routes,
        "email_delivery_status",
        lambda: {"transactional_email": True, "provider": "smtp", "status": "configured"},
    )

    def fail_delivery(*_args, **_kwargs):
        raise RuntimeError("simulated provider failure")

    monkeypatch.setattr(routes, "send_transactional_email", fail_delivery)

    existing = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": existing_email},
    )
    missing = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "smtp-missing@example.com"},
    )

    assert existing.status_code == 202
    assert missing.status_code == 202
    assert existing.get_json() == missing.get_json()
    assert existing.get_json()["status"] == "accepted"
