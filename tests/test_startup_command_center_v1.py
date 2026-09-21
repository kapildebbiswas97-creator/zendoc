from tests.test_milestone1 import login_web, make_client


def test_startup_command_center_is_owner_only(tmp_path):
    _app, client = make_client(tmp_path)

    denied = client.get("/admin/startup", follow_redirects=False)
    assert denied.status_code in {302, 401, 403}

    logged = login_web(client, "admin", "admin@example.com", "AdminStrong123")
    assert logged.status_code == 200

    allowed = client.get("/admin/startup")
    assert allowed.status_code == 200
    assert b"Startup Command Center" in allowed.data
    assert b"India State/UT coverage status" in allowed.data
    assert b"AI runtime &amp; care-chain readiness" in allowed.data
    assert b"Public showcase" in allowed.data

def test_investor_snapshot_export_is_owner_only_and_aggregated(tmp_path):
    _app, client = make_client(tmp_path)

    denied = client.get("/admin/startup/investor-snapshot.json", follow_redirects=False)
    assert denied.status_code in {302, 401, 403}

    logged = login_web(client, "admin", "admin@example.com", "AdminStrong123")
    assert logged.status_code == 200

    response = client.get("/admin/startup/investor-snapshot.json?days=30")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["schema_version"] == "2026.1"
    assert payload["scope"] == "aggregated_owner_investor_evidence"
    assert payload["contains_patient_clinical_content"] is False
    assert payload["generated_at"]
    assert "evidence" in payload["snapshot"]
    assert "readiness" in payload["snapshot"]
    assert "operational_risks" in payload["snapshot"]
    assert "truth_notice" in payload["snapshot"]

