"""Authenticated document-extraction boundary API."""
from __future__ import annotations

from flask import Blueprint, jsonify

from .document_extraction import document_extraction_capabilities, extract_authorized_native_text
from .routes import require_api_user


bp = Blueprint("document_extraction", __name__)


def _api_error(error):
    if isinstance(error, PermissionError):
        status = 403
    elif isinstance(error, LookupError):
        status = 404
    else:
        status = 400
    return jsonify({"error": {"code": status, "message": str(error)}}), status


@bp.get("/api/v1/document-extraction/capabilities")
def api_document_extraction_capabilities():
    user, error = require_api_user()
    if error:
        return error
    return jsonify({"capabilities": document_extraction_capabilities(), "requester_role": user["role"]})


@bp.post("/api/v1/reports/<int:record_id>/extract-text")
def api_extract_report_text(record_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        result = extract_authorized_native_text(user, record_id)
        status = 200 if result["status"] == "NATIVE_TEXT_EXTRACTED" else 409
        return jsonify(result), status
    except (PermissionError, LookupError, ValueError) as service_error:
        return _api_error(service_error)
