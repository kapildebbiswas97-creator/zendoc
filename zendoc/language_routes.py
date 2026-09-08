"""Authenticated multilingual preference/detection APIs."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .db import get_db, now_iso
from .language_service import (
    SUPPORTED_LANGUAGES,
    canonicalize_language_metadata,
    normalize_language,
    safe_template,
    translation_capability,
)
from .routes import require_api_user


bp = Blueprint("language", __name__)


@bp.get("/api/v1/language/capabilities")
def api_language_capabilities():
    user, error = require_api_user()
    if error:
        return error
    preferred = normalize_language(_value(user, "language_preference"), default="en")
    return jsonify({
        "supported_languages": SUPPORTED_LANGUAGES,
        "preferred_language": preferred,
        "free_form_translation": translation_capability(preferred, "en"),
        "safe_templates": {
            "emergency_notice": safe_template("emergency_notice", preferred),
            "not_diagnosis": safe_template("not_diagnosis", preferred),
            "coverage_not_confirmed": safe_template("coverage_not_confirmed", preferred),
        },
    })


@bp.post("/api/v1/language/preference")
def api_language_preference():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    raw = str(data.get("language") or "").strip().lower()
    normalized = normalize_language(raw, default="")
    if normalized not in SUPPORTED_LANGUAGES:
        return jsonify({"error": {"code": 400, "message": "Supported languages are en, bn, hi."}}), 400
    get_db().execute(
        "UPDATE users SET language_preference=?, updated_at=? WHERE id=?",
        (normalized, now_iso(), user["id"]),
    )
    get_db().commit()
    return jsonify({
        "status": "updated",
        "language": normalized,
        "language_name": SUPPORTED_LANGUAGES[normalized],
    })


@bp.post("/api/v1/language/detect")
def api_language_detect():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "")
    use_preference = bool(data.get("use_preference", False))
    preferred = _value(user, "language_preference") if use_preference else None
    result = canonicalize_language_metadata(text, preferred=preferred)
    return jsonify(result)


def _value(user, key, default=None):
    if user is None:
        return default
    if hasattr(user, "keys") and key in user.keys():
        return user[key]
    if isinstance(user, dict):
        return user.get(key, default)
    return default
