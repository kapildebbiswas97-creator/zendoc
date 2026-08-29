from pathlib import Path

from flask import Flask

from .config import load_config, validate_startup_config
from .db import close_db, init_db
from .ecosystem_routes import bp as ecosystem_bp
from .family_routes import bp as family_bp
from .fitness_routes import bp as fitness_bp
from .health_routes import bp as health_memory_bp
from .milestone7_routes import bp as milestone7_bp
from .milestone8_routes import bp as milestone8_bp
from .milestone82_routes import bp as milestone82_bp
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
    app.register_blueprint(family_bp)
    app.register_blueprint(ecosystem_bp)
    app.register_blueprint(milestone7_bp)
    app.register_blueprint(milestone8_bp)
    app.register_blueprint(milestone82_bp)
    app.teardown_appcontext(close_db)
    validate_startup_config(app)
    with app.app_context():
        init_db()

    return app
