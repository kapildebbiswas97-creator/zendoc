"""Public launch, legal, PWA, and account-control routes."""
from __future__ import annotations

import json
from io import BytesIO

from flask import Blueprint, abort, current_app, g, jsonify, make_response, redirect, render_template, request, send_file, session, url_for

from .account_export import build_account_export
from .account_lifecycle import (
    create_account_deletion_token,
    delete_account,
    resolve_account_deletion_token,
)
from .auth import validate_email
from .db import get_db
from .email_delivery import email_delivery_status, send_transactional_email
from .routes import audit, require_api_user
from .security import login_required


bp = Blueprint("public_launch", __name__)


@bp.get("/privacy")
def privacy_policy():
    return render_template("privacy.html")


@bp.get("/terms")
def terms_of_service():
    return render_template("terms.html")


@bp.get("/medical-disclaimer")
def medical_disclaimer():
    return render_template("medical_disclaimer.html")


@bp.get("/community-guidelines")
def community_guidelines():
    return render_template("community_guidelines.html")


def _public_base_url() -> str:
    configured = str(current_app.config.get("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    return configured or request.url_root.rstrip("/")


@bp.route("/account-deletion", methods=("GET", "POST"))
def account_deletion():
    email_status = email_delivery_status()
    if request.method == "POST":
        if g.get("user"):
            password = request.form.get("password", "")
            try:
                result = delete_account(g.user, password=password)
            except (PermissionError, RuntimeError, LookupError) as exc:
                return render_template(
                    "account_deletion.html",
                    error=str(exc),
                    email_status=email_status,
                ), 400
            session.clear()
            return render_template("account_deleted.html", result=result), 200

        raw_email = request.form.get("email", "")
        try:
            email = validate_email(raw_email)
        except ValueError:
            email = ""

        # Always give the same public response so this endpoint cannot be used
        # to enumerate ZENDOC accounts.
        if email and email_status.get("transactional_email"):
            token_info = create_account_deletion_token(email)
            if token_info:
                token, user = token_info
                link = f"{_public_base_url()}{url_for('public_launch.confirm_account_deletion')}?token={token}"
                try:
                    send_transactional_email(
                        user["email"],
                        "Confirm deletion of your ZENDOC account",
                        (
                            "A request was made to delete your ZENDOC account and associated application data.\n\n"
                            f"Open this link to review and confirm deletion: {link}\n\n"
                            "The link expires in 60 minutes. If you did not request deletion, ignore this email."
                        ),
                    )
                except Exception:
                    current_app.logger.exception(
                        "Account deletion email delivery failed for user_id=%s",
                        user["id"],
                    )
        return render_template(
            "account_deletion_requested.html",
            email_available=bool(email_status.get("transactional_email")),
        ), 200

    return render_template(
        "account_deletion.html",
        error=None,
        email_status=email_status,
    )


@bp.route("/account-deletion/confirm", methods=("GET", "POST"))
def confirm_account_deletion():
    token = str(request.values.get("token") or "")
    try:
        token_row = resolve_account_deletion_token(token)
    except PermissionError as exc:
        return render_template("account_deletion_confirm.html", error=str(exc), token="", account=None), 400

    account = {
        "name": token_row["name"],
        "email": token_row["email"],
        "role": token_row["role"],
    }
    if request.method == "POST":
        if request.form.get("confirm_delete") != "yes":
            return render_template(
                "account_deletion_confirm.html",
                error="Explicit confirmation is required.",
                token=token,
                account=account,
            ), 400
        try:
            result = delete_account(token_row, token_authorized=True)
        except (PermissionError, RuntimeError, LookupError) as exc:
            return render_template(
                "account_deletion_confirm.html",
                error=str(exc),
                token=token,
                account=account,
            ), 400
        session.clear()
        return render_template("account_deleted.html", result=result), 200

    return render_template(
        "account_deletion_confirm.html",
        error=None,
        token=token,
        account=account,
    )


@bp.get("/account/export")
@login_required
def account_export():
    payload = build_account_export(g.user)
    audit("export", "account_data", str(g.user["id"]))
    get_db().commit()
    body = json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    return send_file(
        BytesIO(body),
        mimetype="application/json",
        as_attachment=True,
        download_name=f"zendoc-account-export-{g.user['id']}.json",
        max_age=0,
    )


@bp.get("/api/v1/account/export")
def api_account_export():
    user, error = require_api_user()
    if error:
        return error
    payload = build_account_export(user)
    audit("export", "account_data", str(user["id"]), actor=user)
    get_db().commit()
    return jsonify(payload)


@bp.delete("/api/v1/account")
def api_delete_account():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        result = delete_account(user, password=str(data.get("password") or ""))
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403
    except (RuntimeError, LookupError) as exc:
        return jsonify({"error": {"code": 409, "message": str(exc)}}), 409
    return jsonify(result), 200


@bp.get("/manifest.webmanifest")
def web_manifest():
    payload = {
        "id": "/",
        "name": "ZENDOC",
        "short_name": "ZENDOC",
        "description": "Safety-first connected healthcare, Health Memory, care discovery, and bounded AI assistance.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#0b6b61",
        "orientation": "any",
        "categories": ["medical", "health", "lifestyle"],
        "icons": [
            {
                "src": url_for("static", filename="icons/zendoc-192.png"),
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": url_for("static", filename="icons/zendoc-512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": url_for("static", filename="icons/zendoc-maskable-512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
        ],
    }
    response = jsonify(payload)
    response.headers["Content-Type"] = "application/manifest+json"
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


@bp.get("/sw.js")
def service_worker():
    response = make_response(
        current_app.send_static_file("sw.js")
    )
    response.headers["Content-Type"] = "application/javascript; charset=utf-8"
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@bp.get("/offline")
def offline_page():
    return render_template("offline.html")


@bp.get("/.well-known/assetlinks.json")
def android_asset_links():
    package_name = str(current_app.config.get("ANDROID_PACKAGE_NAME") or "").strip()
    fingerprint = str(current_app.config.get("ANDROID_SHA256_CERT_FINGERPRINT") or "").strip()
    if not package_name or not fingerprint:
        abort(404)
    return jsonify([
        {
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": package_name,
                "sha256_cert_fingerprints": [fingerprint],
            },
        }
    ])
