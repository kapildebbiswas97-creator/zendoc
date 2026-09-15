import os
from pathlib import Path

from flask import Flask

from .config import load_config, validate_startup_config
from .care_action_ledger import ensure_care_action_ledger_schema
from .care_os_routes import bp as care_os_bp
from .carefin_routes import bp as carefin_bp
from .care_journey_routes import bp as care_journey_bp
from .careloop_integration import finish_careloop_request
from .continental_coverage import install_continental_coverage
from .continental_medical_authorities import install_continental_medical_authorities
from .dataset_snapshot_routes import bp as dataset_snapshot_ingestion_bp
from .db import close_db, get_db, init_db
from .connected_care_routes import bp as connected_care_bp
from .document_extraction_routes import bp as document_extraction_bp
from .edgecare_routes import bp as edgecare_bp
from .ecosystem_routes import bp as ecosystem_bp
from .family_routes import bp as family_bp
from .fitness_routes import bp as fitness_bp
from .geography_routes import bp as geography_graph_bp
from .global_data_routes import bp as global_data_bp
from .global_data_schema import ensure_global_data_schema
from .global_medical_authorities import install_global_medical_authorities
from .global_registry_install import install_global_public_sources
from .health_access import ensure_consent_schema
from .health_routes import bp as health_memory_bp
from .india_care_rail import bp as india_care_rail_bp
from .knowledge_routes import bp as medical_knowledge_bp
from .language_routes import bp as language_bp
from .medical_knowledge_documents import ensure_medical_knowledge_document_schema
from .medical_knowledge_registry import MEDICAL_KNOWLEDGE_SOURCES
from .medical_rag_ingestion import ensure_medical_rag_schema
from .milestone7_routes import bp as milestone7_bp
from .milestone8_routes import bp as milestone8_bp
from .milestone82_routes import bp as milestone82_bp
from .nutrition_routes import bp as nutrition_intelligence_bp
from .operational_fulfilment import (
    bp as operational_fulfilment_bp,
    ensure_operational_fulfilment_schema,
    finish_operational_careloop_request,
)
from .operational_fulfilment_release import bp as operational_fulfilment_release_bp
from .operational_fulfilment_ui import bp as operational_fulfilment_ui_bp
from .organization_routes import bp as provider_organizations_bp
from .personal_baseline_routes import bp as personal_health_baseline_bp
from .pharmacy_order_routes import bp as pharmacy_order_ops_bp
from .preventive_care import ensure_preventive_care_schema
from .preventive_care_routes import bp as preventive_care_bp
from .public_ingestion_routes import bp as public_ingestion_bp
from .provider_onboarding_routes import bp as provider_onboarding_bp
from .showcase_routes import bp as showcase_bp
from .system_intelligence_routes import bp as system_intelligence_bp
from .universal_search_routes import bp as universal_search_bp
from .database_reliability import readiness_report
from .observability import finish_request_observation, start_request_observation
from .routes import bp


BASE_DIR = Path(__file__).resolve().parent.parent


def _normalize_hosted_environment():
    """Fail toward production security when the app is running on Render.

    Render supplies platform metadata independently of Blueprint-managed custom
    environment variables. A real hosted service must therefore never fall
    back to development cookie/security/persistence semantics merely because
    ZENDOC_ENV was omitted in the service dashboard.
    """
    if os.environ.get("ZENDOC_ENV"):
        return
    if any(
        os.environ.get(key)
        for key in (
            "RENDER",
            "RENDER_SERVICE_ID",
            "RENDER_SERVICE_NAME",
            "RENDER_EXTERNAL_HOSTNAME",
        )
    ):
        os.environ["ZENDOC_ENV"] = "production"


def create_app(test_config=None):
    _normalize_hosted_environment()

    # Extend the in-memory source catalog before binding it into the existing
    # governed ingestion registry.
    install_continental_coverage()
    install_global_public_sources()
    install_global_medical_authorities(MEDICAL_KNOWLEDGE_SOURCES)
    install_continental_medical_authorities(MEDICAL_KNOWLEDGE_SOURCES)

    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
    )
    app.config.from_mapping(load_config(BASE_DIR, test_config))

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    if app.config.get("DATABASE_ENGINE") == "sqlite" and app.config["DATABASE"] != ":memory:":
        Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    app.before_request(start_request_observation)

    app.register_blueprint(bp)
    app.register_blueprint(health_memory_bp)
    app.register_blueprint(medical_knowledge_bp)
    app.register_blueprint(personal_health_baseline_bp)
    app.register_blueprint(preventive_care_bp)
    app.register_blueprint(document_extraction_bp)
    app.register_blueprint(fitness_bp)
    app.register_blueprint(family_bp)
    app.register_blueprint(ecosystem_bp)
    app.register_blueprint(pharmacy_order_ops_bp)
    app.register_blueprint(operational_fulfilment_bp)
    app.register_blueprint(operational_fulfilment_release_bp)
    app.register_blueprint(operational_fulfilment_ui_bp)
    app.register_blueprint(milestone7_bp)
    app.register_blueprint(milestone8_bp)
    app.register_blueprint(edgecare_bp)
    app.register_blueprint(milestone82_bp)
    app.register_blueprint(connected_care_bp)
    app.register_blueprint(care_os_bp)
    app.register_blueprint(india_care_rail_bp)
    app.register_blueprint(universal_search_bp)
    app.register_blueprint(carefin_bp)
    app.register_blueprint(care_journey_bp)
    app.register_blueprint(nutrition_intelligence_bp)
    app.register_blueprint(provider_organizations_bp)
    app.register_blueprint(language_bp)
    app.register_blueprint(geography_graph_bp)
    app.register_blueprint(public_ingestion_bp)
    app.register_blueprint(dataset_snapshot_ingestion_bp)
    app.register_blueprint(provider_onboarding_bp)
    app.register_blueprint(global_data_bp)
    app.register_blueprint(showcase_bp)
    app.register_blueprint(system_intelligence_bp)
    app.after_request(finish_operational_careloop_request)
    app.after_request(finish_careloop_request)
    app.after_request(finish_request_observation)
    app.teardown_appcontext(close_db)
    validate_startup_config(app)
    with app.app_context():
        try:
            init_db()
            ensure_global_data_schema()
            ensure_consent_schema()
            ensure_medical_knowledge_document_schema()
            ensure_medical_rag_schema()
            ensure_preventive_care_schema()
            ensure_care_action_ledger_schema()
            ensure_operational_fulfilment_schema()
            get_db().commit()
            report = readiness_report()
            if report.get("status") != "ready":
                raise RuntimeError(f"Database readiness check failed after migration: {report}")
        except Exception:
            try:
                get_db().rollback()
            except Exception:
                pass
            app.logger.exception("ZENDOC database initialization/readiness failed.")
            raise

    return app
