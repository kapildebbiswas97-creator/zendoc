from zendoc.carefin_cases import (
    create_carefin_case,
    get_carefin_case,
    owner_transition_case,
    request_case_verification,
    submit_case_evidence,
)
from zendoc.db import get_db
from tests.test_milestone1 import csrf, login_web, make_app, register_web


def _user(app, email):
    with app.app_context():
        return dict(get_db().execute("SELECT * FROM users WHERE email_normalized=?", (email,)).fetchone())


def test_carefin_case_needs_authoritative_evidence_for_approval(tmp_path):
    app = make_app(tmp_path)
    patient_client = app.test_client()
    register_web(patient_client, "patient", "carefin-case@example.com", "CareFin Case")
    patient = _user(app, "carefin-case@example.com")

    with app.app_context():
        case = create_carefin_case(patient, "lic", initial_state="DISCOVERED")
        case = submit_case_evidence(
            patient,
            case["id"],
            evidence_type="POLICY_REFERENCE",
            evidence_reference="POLICY-REF-ONLY",
        )
        assert case["state"] == "EVIDENCE_RECEIVED"
        case = request_case_verification(patient, case["id"])
        assert case["state"] == "VERIFICATION_REQUIRED"

        owner = dict(get_db().execute("SELECT * FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone())
        try:
            owner_transition_case(owner, case["id"], target_state="CONFIRMED")
            assert False, "authoritative transition must not succeed without evidence"
        except PermissionError:
            pass

        confirmed = owner_transition_case(
            owner,
            case["id"],
            target_state="CONFIRMED",
            evidence_type="INSURER_RESPONSE",
            evidence_reference="INSURER-RESPONSE-123",
        )
        assert confirmed["state"] == "CONFIRMED"
        assert confirmed["authoritative_confirmation"] == 1


def test_carefin_case_is_private_to_owner_and_zendoc_owner(tmp_path):
    app = make_app(tmp_path)
    a = app.test_client()
    b = app.test_client()
    register_web(a, "patient", "case-a@example.com", "Case A")
    register_web(b, "patient", "case-b@example.com", "Case B")
    user_a = _user(app, "case-a@example.com")
    user_b = _user(app, "case-b@example.com")

    with app.app_context():
        case = create_carefin_case(user_a, "pmjay")
        try:
            get_carefin_case(user_b, case["id"])
            assert False, "cross-user CareFin access must be blocked"
        except PermissionError:
            pass


def test_carefin_web_case_flow_is_visible(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "carefin-web@example.com", "CareFin Web")
    login_web(client, "patient", "carefin-web@example.com")

    page = client.get("/carefin")
    assert page.status_code == 200
    assert b"My CareFin cases" in page.data

    token = csrf(page.data.decode())
    created = client.post(
        "/carefin",
        data={
            "csrf_token": token,
            "action": "create_case",
            "source_id": "pmjay",
            "initial_state": "DISCOVERED",
        },
        follow_redirects=True,
    )
    assert created.status_code == 200
    assert b"CareFin case created" in created.data
    assert b"PM-JAY" in created.data or b"Pradhan" in created.data
