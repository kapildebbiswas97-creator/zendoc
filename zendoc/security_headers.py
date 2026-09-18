"""Central response-security headers for ZENDOC public deployments."""
from __future__ import annotations

from flask import current_app, request


def apply_security_headers(response):
    """Apply headers without changing route payloads or healthcare behavior."""
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy",
        "geolocation=(self), microphone=(self), camera=(self), payment=(), usb=(), browsing-topics=()",
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "; ".join(
            (
                "default-src 'self'",
                "base-uri 'self'",
                "form-action 'self'",
                "frame-ancestors 'none'",
                "object-src 'none'",
                "script-src 'self' 'unsafe-inline'",
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
                "font-src 'self' https://fonts.gstatic.com data:",
                "img-src 'self' data: blob: https:",
                "media-src 'self' blob: https:",
                "connect-src 'self' https: wss:",
                "frame-src https://www.youtube.com https://www.youtube-nocookie.com",
                "worker-src 'self' blob:",
                "manifest-src 'self'",
            )
        ),
    )

    if current_app.config.get("ZENDOC_ENV") == "production":
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
        if (
            request.path.startswith("/api/")
            or response.mimetype in {"text/html", "application/json"}
        ):
            response.headers.setdefault("Cache-Control", "no-store")
    return response
