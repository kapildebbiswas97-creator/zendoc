from tests.test_milestone1 import make_client, register_web


def _api_headers(client, email, role="patient", password="StrongPass123"):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password, "role": role})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['token']}"}


def _journey(client, headers):
    response = client.post("/api/v1/care-journeys", headers=headers, json={"provenance": {"source": "test"}})
    assert response.status_code == 201
    return response.get_json()["journey"]["id"]


def test_care_action_to_reported_outcome_loop_is_durable_and_truthful(tmp_path):
    _app, client = make_client(tmp_path)
    email = "care-loop@example.com"
    register_web(client, "patient", email)
    headers = _api_headers(client, email)
    journey_id = _journey(client, headers)

    created = client.post(
        f"/api/v1/care-journeys/{journey_id}/actions",
        headers=headers,
        json={
            "action_type": "lab_test",
            "title": "Complete ordered blood test",
            "rationale": "Track the patient-confirmed next step from the care journey.",
            "estimated_cost": 450,
            "provider_name": "Example Lab",
            "evidence": {"source_type": "patient_record"},
            "provenance": {"origin": "care_journey"},
        },
    )
    assert created.status_code == 201
    action = created.get_json()["action"]
    assert action["status"] == "PROPOSED"
    assert action["external_execution"] is False
    action_id = action["id"]

    for target, note in [
        ("STAGED", "Patient is reviewing this proposed action."),
        ("CONFIRMED", "Patient confirmed they intend to proceed."),
        ("IN_PROGRESS", "Patient reported that the sample was collected."),
        ("COMPLETED", "Patient reported the lab visit completed; result reference pending."),
    ]:
        response = client.post(
            f"/api/v1/care-actions/{action_id}/transition",
            headers=headers,
            json={"target_status": target, "note": note, "provenance": {"source": "patient_report"}},
        )
        assert response.status_code == 200
        assert response.get_json()["action"]["status"] == target

    outcome = client.post(
        f"/api/v1/care-actions/{action_id}/outcomes",
        headers=headers,
        json={
            "outcome_type": "lab_result_received",
            "summary": "Patient reports that the result was received and saved for follow-up.",
            "status": "REPORTED",
            "source_type": "patient",
            "source_ref": "record_pending_link",
            "provenance": {"source": "patient_report"},
        },
    )
    assert outcome.status_code == 201
    payload = outcome.get_json()["outcome"]
    assert payload["status"] == "REPORTED"
    assert payload["clinical_claim_verified"] is False

    fetched = client.get(f"/api/v1/care-actions/{action_id}", headers=headers)
    assert fetched.status_code == 200
    stored = fetched.get_json()["action"]
    assert stored["status"] == "COMPLETED"
    assert len(stored["events"]) == 5
    assert len(stored["outcomes"]) == 1
    assert stored["outcomes"][0]["clinical_claim_verified"] is False


def test_patient_cannot_mark_outcome_clinically_verified(tmp_path):
    _app, client = make_client(tmp_path)
    email = "care-verify@example.com"
    register_web(client, "patient", email)
    headers = _api_headers(client, email)
    journey_id = _journey(client, headers)
    created = client.post(
        f"/api/v1/care-journeys/{journey_id}/actions",
        headers=headers,
        json={"action_type": "follow_up", "title": "Complete follow-up"},
    )
    action_id = created.get_json()["action"]["id"]
    for target in ["STAGED", "CONFIRMED", "COMPLETED"]:
        changed = client.post(
            f"/api/v1/care-actions/{action_id}/transition",
            headers=headers,
            json={"target_status": target, "note": f"Patient state: {target}"},
        )
        assert changed.status_code == 200

    denied = client.post(
        f"/api/v1/care-actions/{action_id}/outcomes",
        headers=headers,
        json={"outcome_type": "clinical_review", "summary": "Patient supplied claim", "status": "VERIFIED"},
    )
    assert denied.status_code == 403


def test_care_action_blocks_cross_patient_idor(tmp_path):
    _app, client = make_client(tmp_path)
    owner_email = "care-owner@example.com"
    intruder_email = "care-intruder@example.com"
    register_web(client, "patient", owner_email)
    owner_headers = _api_headers(client, owner_email)
    journey_id = _journey(client, owner_headers)
    created = client.post(
        f"/api/v1/care-journeys/{journey_id}/actions",
        headers=owner_headers,
        json={"action_type": "appointment", "title": "Private appointment action"},
    )
    action_id = created.get_json()["action"]["id"]

    client.get("/logout")
    register_web(client, "patient", intruder_email)
    intruder_headers = _api_headers(client, intruder_email)
    denied = client.get(f"/api/v1/care-actions/{action_id}", headers=intruder_headers)
    assert denied.status_code == 403


def test_outcome_requires_completed_action(tmp_path):
    _app, client = make_client(tmp_path)
    email = "care-incomplete@example.com"
    register_web(client, "patient", email)
    headers = _api_headers(client, email)
    journey_id = _journey(client, headers)
    created = client.post(
        f"/api/v1/care-journeys/{journey_id}/actions",
        headers=headers,
        json={"action_type": "medicine", "title": "Obtain prescribed medicine"},
    )
    action_id = created.get_json()["action"]["id"]
    denied = client.post(
        f"/api/v1/care-actions/{action_id}/outcomes",
        headers=headers,
        json={"outcome_type": "adherence", "summary": "Too early"},
    )
    assert denied.status_code == 400
