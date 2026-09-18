from zendoc.db import get_db, now_iso
from zendoc.edgecare_demo_data import DEMO_PATIENT_EMAIL, seed_edgecare_demo_data
from zendoc.investor_dashboard import investor_traction_snapshot
from zendoc.launch_readiness import first50_launch_readiness
from zendoc.startup_analytics import (
    care_journey_conversion,
    provider_onboarding_funnel,
    record_finder_search,
    record_product_activity,
    retention_metrics,
    startup_metrics,
)
from tests.test_milestone1 import make_app


DEMO_PASSWORD = "LocalDemoPass123!"


def _owner():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def test_synthetic_demo_fixture_never_inflates_fundraising_metrics(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENDOC_ENV", "development")
    app = make_app(tmp_path)
    seed_edgecare_demo_data(password=DEMO_PASSWORD, app=app)

    with app.app_context():
        db = get_db()
        patient = dict(
            db.execute(
                "SELECT * FROM users WHERE email_normalized=?",
                (DEMO_PATIENT_EMAIL,),
            ).fetchone()
        )

        record_product_activity(patient, event_type="session_login")
        record_finder_search(
            patient,
            category="doctor",
            location="Kalyani",
            result_count=1,
            source_tiers={"zendoc_verified": 1},
        )

        stamp = now_iso()
        db.execute(
            """
            INSERT INTO care_journeys
            (journey_uid,patient_id,created_by,state,next_safe_action,status,created_at,updated_at)
            VALUES ('demo-metric-journey',?,?, 'WAITING_PROVIDER',
                    'wait_for_provider_response','active',?,?)
            """,
            (int(patient["id"]), int(patient["id"]), stamp, stamp),
        )
        db.commit()

        owner = _owner()
        product = startup_metrics(owner, days=30)
        retention = retention_metrics(owner)
        care = care_journey_conversion(owner, days=30)
        providers = provider_onboarding_funnel(owner, days=90)
        launch = first50_launch_readiness()
        investor = investor_traction_snapshot(owner, days=30)

        assert product["healthcare_searches"] == 0
        assert product["active_search_users"] == 0
        assert retention["patient_users_with_recorded_activity"] == 0
        assert retention["d7"]["eligible_users"] == 0
        assert care["started_journeys"] == 0
        assert providers["provider_profiles_created"] == 0

        assert launch["counts"]["active_non_admin_users"] == 0
        assert launch["counts"]["provider_profiles"] == 0
        assert launch["counts"]["verified_providers"] == 0
        assert "Synthetic competition fixtures are excluded" in launch["truth_notice"]

        evidence = investor["evidence"]
        assert evidence["product"]["healthcare_searches"] == 0
        assert evidence["activation"]["registered_patient_accounts"] == 0
        assert evidence["providers"]["profiles_created"] == 0
        assert evidence["providers"]["provider_verified"] == 0
        assert investor["readiness"]["product_usage_observed"] is False
        assert investor["readiness"]["provider_network_observed"] is False
        assert investor["readiness"]["patient_activation_measurable"] is False
