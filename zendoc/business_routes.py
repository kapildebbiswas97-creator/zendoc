"""Public B2B/B2C business model surface for ZENDOC."""
from flask import Blueprint, render_template

bp = Blueprint("business", __name__)


@bp.get("/business")
def business_page():
    return render_template("business.html")
