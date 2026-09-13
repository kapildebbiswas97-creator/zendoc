from flask import Blueprint, g, jsonify, request

from .global_provider import set_provider_country, supported_provider_countries
from .security import role_required

bp = Blueprint("global_provider", __name__)


@bp.get("/provider/global-profile")
@role_required("doctor", "hospital", "pharmacy")
def provider_global_profile():
    return jsonify({"supported_countries": supported_provider_countries()})


@bp.post("/provider/global-profile")
@role_required("doctor", "hospital", "pharmacy")
def update_provider_global_profile():
    profile = set_provider_country(g.user, request.form.get("country_code"))
    return jsonify({
        "country_code": profile["country_code"],
        "country_name": profile["country_name"],
        "verification_status": profile["verification_status"],
    })
