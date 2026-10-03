from flask import Blueprint, jsonify

from .continental_coverage import continent_coverage_summary
from .db import get_db
from .global_source_registry import country_coverage_manifest
from .organization_intelligence_registry import organization_intelligence_manifest
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
    source_registered = sum(1 for country in countries if int(country.get("source_count") or 0) > 0)
    return jsonify({
        "continents": continent_coverage_summary(),
        "jurisdiction_summary": {
            "country_count": len(countries),
            "source_registered_country_count": source_registered,
            "source_discovery_required_country_count": len(countries) - source_registered,
            "rule": "Country-aware support is not a claim that an authoritative national source has been ingested.",
        },
        "countries": countries,
        "organization_intelligence": organization_intelligence_manifest(),
    })
