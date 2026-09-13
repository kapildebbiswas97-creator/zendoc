from __future__ import annotations

from flask import Blueprint, render_template

bp = Blueprint("showcase", __name__)

@bp.get("/showcase")
def showcase_page():
    return render_template("showcase.html")
