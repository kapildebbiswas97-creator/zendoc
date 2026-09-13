from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, render_template

bp = Blueprint("showcase", __name__)


@bp.get("/showcase")
def showcase_page():
    html = render_template("showcase.html")
    css_path = Path(current_app.static_folder) / "showcase.css"
    css = css_path.read_text(encoding="utf-8") if css_path.is_file() else ""
    if css:
        html = html.replace("</head>", f"<style>{css}</style></head>", 1)
    return html
