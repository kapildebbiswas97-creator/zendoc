from pathlib import Path

from flask import Flask

from .config import load_config, validate_startup_config
from .db import init_db
from .fitness_routes import bp as fitness_bp
from .health_routes import bp as health_memory_bp
from .routes import bp


BASE_DIR = Path(__file__).resolve().parent.parent


def create_app(test_config=None):
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
    )
    app.config.from_mapping(load_config(BASE_DIR, test_config))

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    app.register_blueprint(bp)
    app.register_blueprint(health_memory_bp)
    app.register_blueprint(fitness_bp)
    validate_startup_config(app)
    with app.app_context():
        init_db()

    return app
