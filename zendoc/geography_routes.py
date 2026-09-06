"""Geographic Healthcare Graph APIs."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .geography_graph import (
    link_entity_to_geography,
    list_entities_for_geography,
    search_geography_nodes,
    upsert_geography_node,
)
from .routes import require_api_user
from .security import is_owner


bp = Blueprint("geography_graph", __name__)


@bp.get("/api/v1/geography/search")
def api_geography_search():
    user, error = require_api_user()
    if error:
        return error
    query = str(request.args.get("q") or "").strip()
    if not query:
        return jsonify({"query": "", "nodes": []})
    try:
        nodes = search_geography_nodes(
            query,
            node_type=request.args.get("node_type"),
            limit=request.args.get("limit", 25),
        )
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    return jsonify({"query": query, "nodes": nodes})


@bp.get("/api/v1/geography/<int:node_id>/entities")
def api_geography_entities(node_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        entities = list_entities_for_geography(
            node_id,
            entity_type=request.args.get("entity_type"),
        )
    except (LookupError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    return jsonify({"geography_node_id": node_id, "entities": entities})


@bp.post("/api/v1/admin/geography/nodes")
def api_admin_geography_node():
    user, error = require_api_user()
    if error:
        return error
    if not is_owner(user):
        return jsonify({"error": {"code": 403, "message": "Only the ZENDOC owner may ingest geography data."}}), 403
    data = request.get_json(silent=True) or {}
    try:
        node = upsert_geography_node(
            node_type=data.get("node_type"),
            name=data.get("name"),
            source=data.get("source"),
            source_ref=data.get("source_ref"),
            parent_id=data.get("parent_id"),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            verified=bool(data.get("verified", False)),
            freshness_at=data.get("freshness_at"),
        )
    except (LookupError, TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    return jsonify({"status": "saved", "node": node}), 201


@bp.post("/api/v1/admin/geography/links")
def api_admin_geography_link():
    user, error = require_api_user()
    if error:
        return error
    if not is_owner(user):
        return jsonify({"error": {"code": 403, "message": "Only the ZENDOC owner may ingest geography links."}}), 403
    data = request.get_json(silent=True) or {}
    try:
        link = link_entity_to_geography(
            geography_node_id=int(data.get("geography_node_id") or 0),
            entity_type=data.get("entity_type"),
            entity_id=data.get("entity_id"),
            source=data.get("source"),
            verification_state=data.get("verification_state"),
            freshness_at=data.get("freshness_at"),
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
        )
    except (LookupError, TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    return jsonify({"status": "saved", "link": link}), 201
