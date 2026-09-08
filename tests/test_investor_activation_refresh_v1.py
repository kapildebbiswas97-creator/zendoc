from zendoc.data_refresh import create_data_refresh_task
from zendoc.db import get_db, now_iso
from zendoc.investor_dashboard import investor_traction_snapshot
from zendoc.startup_analytics import record_finder_search, record_product_activity
from tests.test_milestone1 import make_app


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def create_patient(db):
    now = now_iso()
    user_id = db.execute(
        """
        INSERT INTO users
        (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
        VALUES ('Investor Patient','investor-patient@example.com','investor-patient@example.com','x','patient',1,?,?)
        """,
        (now, now),
    ).lastrowid
    return dict(db.execute("SELECT * FROM users WHERE id=?", (int(user_id),)).fetchone())


def test_investor_snapshot_includes_observed_activation_and_refresh_risk(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        patient = create_patient(get_db())
        record_product_activity(patient, event_type="session_login")
        record_finder_search(
            patient,
            category="doctor",
            location="Kalyani",
            result_count=1,
            source_tiers={"zendoc_verified": 1},
        )
        record_product_activity(patient, event_type="provider_view")
        record_product_activity(patient, event_type="appointment_requested")
        get_db().commit()

        task = create_data_refresh_task(
            owner_actor(),
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
            owner_note="Urgent source refresh.",
        )
        assert task["status"] == "queued"

        snapshot = investor_traction_snapshot(owner_actor(), days=30)
        activation = snapshot["evidence"]["activation"]
        risks = snapshot["operational_risks"]

        assert activation["registered_patient_accounts"] == 1
        assert activation["logged_in_patients"] == 1
        assert activation["useful_search_patients"] == 1
        assert activation["provider_view_patients"] == 1
        assert activation["appointment_request_patients"] == 1

        assert risks["urgent_data_refresh_sources"] > 0
        assert risks["p0_data_sources"] > 0
        assert risks["queued_refresh_tasks"] == 1
        assert "completed non-dry-run" in risks["truth_notice"]

        assert snapshot["readiness"]["patient_activation_measurable"] is True
        assert snapshot["readiness"]["appointment_request_observed"] is True
