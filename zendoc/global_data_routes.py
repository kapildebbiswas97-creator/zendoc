from flask import Blueprint, jsonify

from .db import get_db
from .global_source_registry import country_coverage_manifest
from .security import owner_required

bp = Blueprint("global_data", __name__)


@bp.get("/owner/data/global-coverage")
@owner_required
def owner_global_coverage():
    rows = get_db().execute(
        "SELECT COALESCE(country_code,'') code,COUNT(*) c FROM public_healthcare_entities WHERE active=1 GROUP BY COALESCE(country_code,'')"
    ).fetchall()
    counts = {str(row["code"] or "UNSET"): int(row["c"] or 0) for row in rows}
    countries = country_coverage_manifest()
    for country in countries:
        country["active_public_rows"] = counts.get(country["country_code"], 0)
    return jsonify({"countries": countries})
