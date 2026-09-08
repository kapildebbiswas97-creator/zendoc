import json

import pytest

from tests.test_milestone1 import make_client, register_web
from zendoc.care_graph import get_patient_care_graph, record_care_continuity_event
from zendoc.db import get_db
from zendoc.telehealth import get_consultation, request_consultation, set_doctor_availability


def _user_by_email(email):
    return get_db().execute(
        "SELECT * FROM users WHERE email_normalized=?",
        (email.lower(),),
    ).fetchone()


def test_care_graph_blocks_cross_patient_idor(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "patient", "graph-one@example.com", "Graph One")
    register_web(client, "patient", "graph-two@example.com", "Graph Two")

    with app.app_context():
        patient_one = _user_by_email("graph-one@example.com")
        patient_two = _user_by_email("graph-two@example.com")

        own_graph = get_patient_care_graph(patient_one["id"], actor=patient_one)
        assert own_graph["patient"]["id"] == patient_one["id"]

        with pytest.raises(PermissionError):
            get_patient_care_graph(patient_one["id"], actor=patient_two)


def test_consultation_blocks_cross_patient_idor(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "patient", "consult-one@example.com", "Consult One")
    register_web(client, "patient", "consult-two@example.com", "Consult Two")
    register_web(client, "doctor", "consult-doctor@example.com", "Consult Doctor")

    with app.app_context():
        patient_one = _user_by_email("consult-one@example.com")
        patient_two = _user_by_email("consult-two@example.com")
        doctor = _user_by_email("consult-doctor@example.com")

        consultation = request_consultation(
            patient_one,
            {
                "doctor_id": doctor["id"],
                "consultation_type": "chat",
                "reason": "Follow-up",
            },
        )

        assert get_consultation(patient_one, consultation["id"])["id"] == consultation["id"]
        with pytest.raises(PermissionError):
            get_consultation(patient_two, consultation["id"])


def test_doctor_cannot_update_another_doctors_availability(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "doctor", "doctor-one@example.com", "Doctor One")
    register_web(client, "doctor", "doctor-two@example.com", "Doctor Two")

    with app.app_context():
        doctor_one = _user_by_email("doctor-one@example.com")
        doctor_two = _user_by_email("doctor-two@example.com")

        with pytest.raises(PermissionError):
            set_doctor_availability(
                doctor_two,
                {
                    "doctor_id": doctor_one["id"],
                    "status": "available",
                },
            )


def test_care_graph_platform_event_redacts_sensitive_metadata(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "patient", "audit-patient@example.com", "Audit Patient")

    with app.app_context():
        patient = _user_by_email("audit-patient@example.com")
        record_care_continuity_event(
            patient_id=patient["id"],
            event_type="follow_up",
            title="Follow-up recorded",
            summary="Timeline summary remains in the user-facing clinical record.",
            source="USER_REPORTED",
            actor_id=patient["id"],
            metadata={
                "patient_id": patient["id"],
                "status": "created",
                "diagnosis": "private-clinical-detail",
                "phone": "9999999999",
            },
        )

        row = get_db().execute(
            "SELECT payload_json FROM platform_events WHERE agent_name='CareGraph' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        payload = json.loads(row["payload_json"])

        assert payload["patient_id"] == patient["id"]
        assert payload["status"] == "created"
        assert payload["diagnosis"] == "[redacted]"
        assert payload["phone"] == "[redacted]"
        assert "private-clinical-detail" not in row["payload_json"]
        assert "9999999999" not in row["payload_json"]
