"""Owner-only official/public data ingestion APIs."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .public_data_ingestion import ingest_public_records, list_ingestion_batches
from .dataset_adapters import adapt_records, parse_csv_text
from .data_gap_registry import list_data_gaps
from .public_source_registry import list_public_ingestion_sources
from .routes import require_api_user
from .security import is_owner


bp = Blueprint("public_ingestion", __name__)


def _owner():
    user, error = require_api_user()
    if error:
        return None, error
    if not is_owner(user):
        return None, (jsonify({"error": {"code": 403, "message": "Only the ZENDOC owner may manage public-data ingestion."}}), 403)
    return user, None


@bp.get("/api/v1/admin/ingestion/sources")
def api_ingestion_sources():
    user, error = _owner()
    if error:
        return error
    return jsonify({"sources": list_public_ingestion_sources()})


@bp.get("/api/v1/admin/ingestion/batches")
def api_ingestion_batches():
    user, error = _owner()
    if error:
        return error
    try:
        batches = list_ingestion_batches(user, limit=request.args.get("limit", 50))
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    return jsonify({"batches": batches})


@bp.post("/api/v1/admin/ingestion/adapt")
def api_ingestion_adapt():
    user, error = _owner()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        rows = data.get("rows")
        if rows is None and data.get("csv_text") is not None:
            rows = parse_csv_text(data.get("csv_text"))
        result = adapt_records(
            ingestion_type=data.get("ingestion_type"),
            rows=rows or [],
            mapping=data.get("mapping") if isinstance(data.get("mapping"), dict) else {},
            defaults=data.get("defaults") if isinstance(data.get("defaults"), dict) else {},
        )
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    return jsonify({"status": "adapted", "result": result})


@bp.post("/api/v1/admin/ingestion/preview")
def api_ingestion_preview():
    user, error = _owner()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        result = ingest_public_records(
            user,
            source_id=data.get("source_id"),
            ingestion_type=data.get("ingestion_type"),
            records=data.get("records") or [],
            dry_run=True,
        )
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    return jsonify({"status": "previewed", "batch": result})


@bp.post("/api/v1/admin/ingestion/apply")
def api_ingestion_apply():
    user, error = _owner()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    if data.get("apply") is not True:
        return jsonify({
            "error": {
                "code": 400,
                "message": "Explicit apply=true is required. Preview the batch first and verify source/provenance.",
            }
        }), 400
    try:
        result = ingest_public_records(
            user,
            source_id=data.get("source_id"),
            ingestion_type=data.get("ingestion_type"),
            records=data.get("records") or [],
            dry_run=False,
        )
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    return jsonify({"status": "completed", "batch": result}), 201


@bp.get("/api/v1/admin/ingestion/data-gaps")
def api_ingestion_data_gaps():
    user, error = _owner()
    if error:
        return error
    return jsonify({"data_gaps": list_data_gaps()})
