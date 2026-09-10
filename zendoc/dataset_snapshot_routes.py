"""Owner-only immutable dataset snapshot ingestion endpoints."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .dataset_snapshot_ingestion import ingest_public_snapshot, normalize_dataset_snapshot
from .routes import require_api_user
from .security import is_owner


bp = Blueprint("dataset_snapshot_ingestion", __name__)


def _owner():
    user, error = require_api_user()
    if error:
        return None, error
    if not is_owner(user):
        return None, (
            jsonify({"error": {"code": 403, "message": "Only the ZENDOC owner may manage dataset snapshots."}}),
            403,
        )
    return user, None


@bp.post("/api/v1/admin/ingestion/snapshots/validate")
def api_dataset_snapshot_validate():
    user, error = _owner()
    if error:
        return error
    del user
    data = request.get_json(silent=True) or {}
    try:
        snapshot = normalize_dataset_snapshot(data.get("source_id"), data.get("dataset_snapshot") or {})
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    return jsonify({
        "status": "valid",
        "dataset_snapshot": snapshot,
        "truth_notice": (
            "Validation checks provenance structure and safety only. It does not prove that the source content is "
            "factually correct, current, licensed for every use, or ZENDOC-verified."
        ),
    })


@bp.post("/api/v1/admin/ingestion/snapshots/preview")
def api_dataset_snapshot_preview():
    user, error = _owner()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        result = ingest_public_snapshot(
            user,
            source_id=data.get("source_id"),
            ingestion_type=data.get("ingestion_type"),
            records=data.get("records") or [],
            dataset_snapshot=data.get("dataset_snapshot") or {},
            dry_run=True,
        )
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    return jsonify({"status": "previewed", "batch": result})


@bp.post("/api/v1/admin/ingestion/snapshots/apply")
def api_dataset_snapshot_apply():
    user, error = _owner()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    if data.get("apply") is not True:
        return jsonify({
            "error": {
                "code": 400,
                "message": "Explicit apply=true is required after previewing the exact dataset snapshot.",
            }
        }), 400
    try:
        result = ingest_public_snapshot(
            user,
            source_id=data.get("source_id"),
            ingestion_type=data.get("ingestion_type"),
            records=data.get("records") or [],
            dataset_snapshot=data.get("dataset_snapshot") or {},
            dry_run=False,
            preview_batch_uid=data.get("preview_batch_uid"),
        )
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    return jsonify({"status": "completed", "batch": result}), 201
