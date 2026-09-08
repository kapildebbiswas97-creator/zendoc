from zendoc.db import get_db
from zendoc.partner_audit import list_partner_audit_events, partner_audit_metrics, record_partner_audit_event
from tests.test_milestone1 import make_app


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def test_partner_audit_strips_clinical_metadata(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        record_partner_audit_event(
            event_type="test_event",
            actor_type="partner",
            outcome="success",
            endpoint="/api/v1/business/test",
            metadata={
                "provider_profile_id": 123,
                "scope": "public_directory.read",
                "symptoms": "should never persist",
                "diagnosis": "should never persist",
                "prescription": "should never persist",
                "medical_history": "should never persist",
                "clinical_notes": "should never persist",
                "request_body": "should never persist",
            },
        )
        get_db().commit()

        events = list_partner_audit_events(owner_actor(), limit=10)
        assert len(events) == 1
        metadata = events[0]["metadata"]
        assert metadata["provider_profile_id"] == 123
        assert metadata["scope"] == "public_directory.read"
        assert "symptoms" not in metadata
        assert "diagnosis" not in metadata
        assert "prescription" not in metadata
        assert "medical_history" not in metadata
        assert "clinical_notes" not in metadata
        assert "request_body" not in metadata

        metrics = partner_audit_metrics(owner_actor(), days=30)
        assert metrics["event_count"] == 1


def test_partner_audit_does_not_store_raw_request_payload_columns(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        columns = {
            row["name"]
            for row in get_db().execute("PRAGMA table_info(partner_api_audit_events)").fetchall()
        }
        forbidden_columns = {
            "symptoms",
            "diagnosis",
            "prescription",
            "medical_history",
            "clinical_notes",
            "request_body",
            "patient_id",
        }
        assert forbidden_columns.isdisjoint(columns)
