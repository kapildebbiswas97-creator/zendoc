from zendoc.business_api import (
    authenticate_business_api_key,
    create_business_api_client,
    issue_business_api_key,
)
from zendoc.db import get_db
from zendoc.medical_transport import create_transport_request, get_transport_request
from zendoc.transport_partner import (
    assign_transport_partner,
    list_partner_transport_assignments,
    partner_update_transport_assignment,
)
from tests.test_milestone1 import make_app


def _owner():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def _patient(db):
    return db.execute("SELECT * FROM users WHERE role='patient' ORDER BY id LIMIT 1").fetchone()


def _partner():
    partner = create_business_api_client(
        _owner(),
        {
            "name": "Test Transport Partner",
            "client_type": "medical_transport",
            "allowed_scopes": ["transport_fulfilment.write"],
        },
    )
    key = issue_business_api_key(_owner(), partner["id"], expires_in_days=30)
    identity = authenticate_business_api_key(
        key["api_key"],
        required_scope="transport_fulfilment.write",
        endpoint="/test",
    )
    return partner, identity


def test_non_emergency_transport_partner_round_trip(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient = _patient(db)
        request_row = create_transport_request(patient, {
            "transport_type": "patient_transport",
            "pickup_address": "1 Test Road",
            "destination_address": "Test Hospital",
        })
        partner, identity = _partner()
        assignment = assign_transport_partner(_owner(), request_row["id"], partner["id"])
        assert assignment["status"] == "assigned"
        assert assignment["provider_confirmed"] is False

        listed = list_partner_transport_assignments(identity)
        assert len(listed) == 1
        assert listed[0]["pickup_address"] == "1 Test Road"
        assert "patient_name" not in listed[0]
        assert "notes" not in listed[0]

        accepted = partner_update_transport_assignment(
            identity,
            assignment["id"],
            status="accepted",
            eta_minutes=20,
            vehicle_reference="AMB-TEST-7",
        )
        assert accepted["provider_confirmed"] is True
        assert accepted["dispatch_confirmed"] is False

        en_route = partner_update_transport_assignment(
            identity,
            assignment["id"],
            status="en_route",
        )
        assert en_route["dispatch_confirmed"] is True

        patient_view = get_transport_request(patient, request_row["id"])
        assert patient_view["provider_confirmed"] is True
        assert patient_view["dispatch_confirmed"] is True
        assert patient_view["partner_status"] == "en_route"
        assert patient_view["partner_name"] == "Test Transport Partner"


def test_generic_partner_bridge_rejects_emergency_transport(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient = _patient(db)
        request_row = create_transport_request(patient, {
            "transport_type": "emergency_ambulance",
            "pickup_address": "Emergency Location",
        })
        partner, _identity = _partner()

        blocked = False
        try:
            assign_transport_partner(_owner(), request_row["id"], partner["id"])
        except PermissionError as exc:
            blocked = "Emergency transport" in str(exc)
        assert blocked is True


def test_transport_partner_is_cross_client_isolated(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient = _patient(db)
        request_row = create_transport_request(patient, {
            "transport_type": "wheelchair_transport",
            "pickup_address": "Pickup",
        })
        partner_a, identity_a = _partner()
        assignment = assign_transport_partner(_owner(), request_row["id"], partner_a["id"])

        partner_b = create_business_api_client(
            _owner(),
            {
                "name": "Other Transport",
                "client_type": "medical_transport",
                "allowed_scopes": ["transport_fulfilment.write"],
            },
        )
        key_b = issue_business_api_key(_owner(), partner_b["id"], expires_in_days=30)
        identity_b = authenticate_business_api_key(
            key_b["api_key"],
            required_scope="transport_fulfilment.write",
            endpoint="/test-b",
        )
        assert list_partner_transport_assignments(identity_b) == []

        failed = False
        try:
            partner_update_transport_assignment(
                identity_b, assignment["id"], status="accepted"
            )
        except LookupError:
            failed = True
        assert failed is True
