"""Truthful transactional email delivery for ZENDOC.

SMTP is considered available only when explicitly configured. The module never
pretends an email was delivered when credentials/provider configuration are
missing or when the SMTP transaction fails.
"""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app


def email_delivery_status() -> dict:
    provider = str(current_app.config.get("EMAIL_PROVIDER") or "none").strip().lower()
    if provider != "smtp":
        return {
            "provider": provider or "none",
            "status": "integration_required",
            "transactional_email": False,
        }

    required = {
        "SMTP_HOST": current_app.config.get("SMTP_HOST"),
        "SMTP_FROM_EMAIL": current_app.config.get("SMTP_FROM_EMAIL"),
    }
    missing = [key for key, value in required.items() if not str(value or "").strip()]
    if missing:
        return {
            "provider": "smtp",
            "status": "integration_required",
            "transactional_email": False,
            "missing": missing,
        }
    return {
        "provider": "smtp",
        "status": "configured",
        "transactional_email": True,
        "host": str(current_app.config.get("SMTP_HOST") or ""),
        "port": int(current_app.config.get("SMTP_PORT") or 587),
        "tls": bool(current_app.config.get("SMTP_USE_TLS")),
        "ssl": bool(current_app.config.get("SMTP_USE_SSL")),
    }


def send_transactional_email(to_email: str, subject: str, text_body: str) -> dict:
    status = email_delivery_status()
    if not status.get("transactional_email"):
        raise RuntimeError("Transactional email delivery is not configured.")

    recipient = str(to_email or "").strip()
    if not recipient or "@" not in recipient:
        raise ValueError("A valid email recipient is required.")

    message = EmailMessage()
    message["From"] = str(current_app.config.get("SMTP_FROM_EMAIL"))
    message["To"] = recipient
    message["Subject"] = str(subject or "ZENDOC notification")[:180]
    message.set_content(str(text_body or "")[:12000])

    host = str(current_app.config.get("SMTP_HOST"))
    port = int(current_app.config.get("SMTP_PORT") or 587)
    username = str(current_app.config.get("SMTP_USERNAME") or "").strip()
    password = str(current_app.config.get("SMTP_PASSWORD") or "")
    timeout = int(current_app.config.get("SMTP_TIMEOUT") or 15)
    use_ssl = bool(current_app.config.get("SMTP_USE_SSL"))
    use_tls = bool(current_app.config.get("SMTP_USE_TLS")) and not use_ssl

    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    kwargs = {"host": host, "port": port, "timeout": timeout}
    if use_ssl:
        kwargs["context"] = ssl.create_default_context()

    with smtp_class(**kwargs) as client:
        if use_tls:
            client.ehlo()
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
        if username:
            if not password:
                raise RuntimeError("SMTP password is required when SMTP username is configured.")
            client.login(username, password)
        client.send_message(message)

    return {
        "status": "sent",
        "provider": "smtp",
        "recipient": recipient,
    }
