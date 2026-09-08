"""Owner-only official/public data ingestion APIs."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .public_data_ingestion import ingest_public_records, list_ingestion_batches
from .dataset_adapters import adapt_records, parse_csv_text
from .data_gap_registry import build_collection_plan, list_data_gaps
from .business_api import (
    business_api_metrics,
    create_business_api_client,
    issue_business_api_key,
    list_business_api_clients,
    revoke_business_api_key,
)
from .public_source_registry import list_public_ingestion_sources, public_data_coverage_matrix
from .official_connectors import connector_readiness, infer_mapping, list_connector_profiles
from .geography_region_registry import import_lgd_state_registry, list_import_regions
from .state_source_priorities import state_source_priority
from .india_regions import india_region_catalog
from .institution_pilots import (
    create_institution_pilot,
    institution_pilot_metrics,
    list_institution_pilots,
    update_institution_pilot,
)
from .startup_analytics import care_journey_conversion, india_coverage_quality, provider_onboarding_funnel, retention_metrics, startup_metrics
from .startup_finance import create_financial_entry, create_financial_snapshot, financial_kpis, list_financial_entries
from .investor_dashboard import investor_traction_snapshot
from .state_geography_bootstrap import (
    bootstrap_state_geography,
    list_target_states,
    state_coverage_summary,
)
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


@bp.get("/api/v1/admin/ingestion/coverage")
def api_ingestion_coverage():
    user, error = _owner()
    if error:
        return error
    return jsonify({"coverage": public_data_coverage_matrix()})


@bp.get("/api/v1/admin/ingestion/sources")
def api_ingestion_sources():
    user, error = _owner()
    if error:
        return error
    return jsonify({"sources": list_public_ingestion_sources()})


@bp.get("/api/v1/admin/ingestion/connectors")
def api_ingestion_connectors():
    user, error = _owner()
    if error:
        return error
    return jsonify({"connectors": list_connector_profiles()})


@bp.get("/api/v1/admin/ingestion/connectors/<source_id>")
def api_ingestion_connector_readiness(source_id):
    user, error = _owner()
    if error:
        return error
    try:
        return jsonify({"connector": connector_readiness(source_id)})
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404


@bp.post("/api/v1/admin/ingestion/connectors/<source_id>/map")
def api_ingestion_connector_map(source_id):
    user, error = _owner()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        rows = data.get("rows")
        if rows is None and data.get("csv_text") is not None:
            rows = parse_csv_text(data.get("csv_text"))
        result = infer_mapping(source_id, rows or [])
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    return jsonify({"status": "mapped", "result": result})


@bp.post("/api/v1/admin/ingestion/geography-registry/india")
def api_geography_india_state_registry():
    user, error = _owner()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    rows = data.get("rows")
    if rows is None and data.get("csv_text") is not None:
        rows = parse_csv_text(data.get("csv_text"))
    try:
        result = import_lgd_state_registry(rows or [], source=data.get("source") or "lgd")
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    return jsonify({"result": result}), 201


@bp.get("/api/v1/admin/ingestion/geography-registry/india")
def api_geography_india_state_registry_list():
    user, error = _owner()
    if error:
        return error
    return jsonify({
        "regions": list_import_regions(country_code="IN", region_level="state")
    })


@bp.get("/api/v1/admin/ingestion/india-regions")
def api_ingestion_india_regions():
    user, error = _owner()
    if error:
        return error
    regions = india_region_catalog()
    return jsonify({
        "country": "India",
        "state_count": sum(1 for item in regions if item["region_type"] == "state"),
        "union_territory_count": sum(1 for item in regions if item["region_type"] == "union_territory"),
        "regions": [
            {
                **item,
                "coverage": state_source_priority(item["slug"]),
            }
            for item in regions
        ],
        "truth_notice": (
            "All listed States/UTs are product coverage targets. Full local accuracy depends on official LGD "
            "geography and official/public provider datasets actually imported for the relevant area."
        ),
    })


@bp.get("/api/v1/admin/ingestion/state-priority/<state_slug>")
def api_ingestion_state_priority(state_slug):
    user, error = _owner()
    if error:
        return error
    return jsonify({"priority": state_source_priority(state_slug)})


@bp.get("/api/v1/admin/ingestion/geography-targets")
def api_geography_targets():
    user, error = _owner()
    if error:
        return error
    return jsonify({"states": list_target_states()})


@bp.get("/api/v1/admin/ingestion/geography/<state_slug>/coverage")
def api_geography_state_coverage(state_slug):
    user, error = _owner()
    if error:
        return error
    try:
        return jsonify({"coverage": state_coverage_summary(state_slug)})
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404


@bp.post("/api/v1/admin/ingestion/geography/<state_slug>/bootstrap")
def api_geography_state_bootstrap(state_slug):
    user, error = _owner()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        result = bootstrap_state_geography(
            user,
            state_slug=state_slug,
            districts=data.get("districts"),
            subdistricts=data.get("subdistricts"),
            villages=data.get("villages"),
            blocks=data.get("blocks"),
            panchayats=data.get("panchayats"),
            local_bodies=data.get("local_bodies"),
            village_panchayat_links=data.get("village_panchayat_links"),
            source=data.get("source") or "lgd",
            freshness_at=data.get("freshness_at"),
            dry_run=data.get("apply") is not True,
        )
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
    return jsonify({"result": result}), 201 if result.get("status") == "APPLIED" else 200


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
    return jsonify({
        "data_gaps": list_data_gaps(),
        "collection_plan": build_collection_plan(),
    })


@bp.get("/api/v1/admin/startup/metrics")
def api_startup_metrics():
    user, error = _owner()
    if error:
        return error
    try:
        days = int(request.args.get("days", 30))
        return jsonify({"metrics": startup_metrics(user, days=days)})
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400


@bp.get("/api/v1/admin/startup/india-coverage")
def api_startup_india_coverage():
    user, error = _owner()
    if error:
        return error
    return jsonify({"coverage": india_coverage_quality(user)})


@bp.get("/api/v1/admin/startup/retention")
def api_startup_retention():
    user, error = _owner()
    if error:
        return error
    return jsonify({"retention": retention_metrics(user)})


@bp.get("/api/v1/admin/startup/care-funnel")
def api_startup_care_funnel():
    user, error = _owner()
    if error:
        return error
    try:
        days = int(request.args.get("days", 30))
        return jsonify({"care_funnel": care_journey_conversion(user, days=days)})
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400


@bp.get("/api/v1/admin/startup/provider-funnel")
def api_startup_provider_funnel():
    user, error = _owner()
    if error:
        return error
    try:
        days = int(request.args.get("days", 90))
        return jsonify({"provider_funnel": provider_onboarding_funnel(user, days=days)})
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400


@bp.get("/api/v1/admin/startup/pilots")
def api_startup_pilots():
    user, error = _owner()
    if error:
        return error
    try:
        return jsonify({
            "pilots": list_institution_pilots(
                user,
                status=request.args.get("status"),
                limit=request.args.get("limit", 100),
            ),
            "metrics": institution_pilot_metrics(user),
        })
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400


@bp.post("/api/v1/admin/startup/pilots")
def api_startup_pilot_create():
    user, error = _owner()
    if error:
        return error
    try:
        pilot = create_institution_pilot(user, request.get_json(silent=True) or {})
        return jsonify({"pilot": pilot}), 201
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400


@bp.patch("/api/v1/admin/startup/pilots/<int:pilot_id>")
def api_startup_pilot_update(pilot_id):
    user, error = _owner()
    if error:
        return error
    try:
        pilot = update_institution_pilot(user, pilot_id, request.get_json(silent=True) or {})
        return jsonify({"pilot": pilot})
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400


@bp.get("/api/v1/admin/startup/business-api-clients")
def api_business_clients_list():
    user, error = _owner()
    if error:
        return error
    return jsonify({
        "clients": list_business_api_clients(user),
        "metrics": business_api_metrics(user),
    })


@bp.post("/api/v1/admin/startup/business-api-clients")
def api_business_client_create():
    user, error = _owner()
    if error:
        return error
    try:
        client = create_business_api_client(user, request.get_json(silent=True) or {})
        return jsonify({"client": client}), 201
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400


@bp.post("/api/v1/admin/startup/business-api-clients/<int:client_id>/keys")
def api_business_key_issue(client_id):
    user, error = _owner()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        key = issue_business_api_key(
            user,
            client_id,
            expires_in_days=data.get("expires_in_days", 90),
        )
        return jsonify({"key": key}), 201
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400


@bp.post("/api/v1/admin/startup/business-api-keys/<int:key_id>/revoke")
def api_business_key_revoke(key_id):
    user, error = _owner()
    if error:
        return error
    try:
        return jsonify({"key": revoke_business_api_key(user, key_id)})
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404


@bp.get("/api/v1/admin/startup/finance")
def api_startup_finance():
    user, error = _owner()
    if error:
        return error
    try:
        return jsonify({
            "kpis": financial_kpis(user, month=request.args.get("month")),
            "entries": list_financial_entries(user, limit=request.args.get("limit", 200)),
        })
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400


@bp.post("/api/v1/admin/startup/finance/entries")
def api_startup_finance_entry_create():
    user, error = _owner()
    if error:
        return error
    try:
        entry = create_financial_entry(user, request.get_json(silent=True) or {})
        return jsonify({"entry": entry}), 201
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400


@bp.post("/api/v1/admin/startup/finance/snapshots")
def api_startup_finance_snapshot_create():
    user, error = _owner()
    if error:
        return error
    try:
        snapshot = create_financial_snapshot(user, request.get_json(silent=True) or {})
        return jsonify({"snapshot": snapshot}), 201
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400


@bp.get("/api/v1/admin/startup/investor-snapshot")
def api_startup_investor_snapshot():
    user, error = _owner()
    if error:
        return error
    try:
        days = int(request.args.get("days", 30))
        return jsonify({
            "snapshot": investor_traction_snapshot(
                user,
                days=days,
                finance_month=request.args.get("finance_month"),
            )
        })
    except (TypeError, ValueError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
