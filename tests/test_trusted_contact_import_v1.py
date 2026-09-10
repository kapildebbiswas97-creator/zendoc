import pytest

from zendoc.db import get_db
from zendoc.trusted_contact_import import (
    apply_trusted_provider_contacts,
    preview_trusted_provider_contacts,
)
from tests.test_milestone1 import make_app


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def contact(reference="student-ref-001", **overrides):
    row = {
        "provider_type": "doctor",
        "source_type": "college_network",
        "source_reference": reference,
        "organization_name": "Thiliani Government Hospital",
        "contact_name": "Dr Pilot Contact",
        "contact_phone": "+91 9000000000",
        "state": "Kerala",
        "district": "Thiruvananthapuram",
        "city": "Thiruvananthapuram",
        "permission_to_share": True,
    }
    row.update(overrides)
    return row


def test_preview_does_not_mutate_and_requires_explicit_permission(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        result = preview_trusted_provider_contacts(owner_actor(), [contact(), contact("no-permission", permission_to_share=False)])
        assert result["status"] == "previewed"
        assert len(result["accepted"]) == 1
        assert result["rejected"][0]["reason"] == "permission_to_share must be true"
        assert get_db().execute("SELECT COUNT(*) c FROM provider_network_prospects").fetchone()["c"] == 0


def test_apply_is_idempotent_and_preserves_discovered_state(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        first = apply_trusted_provider_contacts(owner_actor(), [contact()])
        second = preview_trusted_provider_contacts(owner_actor(), [contact()])
        assert first["applied_count"] == 1
        assert second["accepted"] == []
        assert second["unchanged"][0]["reason"] == "already imported"
        row = get_db().execute("SELECT status,source_reference,owner_note FROM provider_network_prospects").fetchone()
        assert row["status"] == "discovered"
        assert row["source_reference"] == "student-ref-001"
        assert '"permission_to_share":true' in row["owner_note"]


def test_conflicting_source_reference_is_blocked_without_overwrite(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        apply_trusted_provider_contacts(owner_actor(), [contact()])
        result = preview_trusted_provider_contacts(owner_actor(), [contact(contact_name="Different Contact")])
        assert result["accepted"] == []
        assert result["conflicts"][0]["source_reference"] == "student-ref-001"
        with pytest.raises(ValueError, match="conflicting"):
            apply_trusted_provider_contacts(owner_actor(), [contact(contact_name="Different Contact")])
        row = get_db().execute("SELECT contact_name FROM provider_network_prospects").fetchone()
        assert row["contact_name"] == "Dr Pilot Contact"


def test_private_and_operational_fields_are_rejected(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        result = preview_trusted_provider_contacts(owner_actor(), [contact(patient_records="never", bed_count=4)])
        assert result["accepted"] == []
        assert result["rejected"][0]["reason"] == "private or operational fields are not accepted"


def test_only_owner_can_import_contacts(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        with pytest.raises(PermissionError):
            preview_trusted_provider_contacts({"id": 2, "role": "doctor", "email": "doctor@example.com", "active": 1}, [contact()])


def test_owner_api_import_is_preview_first(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    login = client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "AdminStrong123"})
    headers = {"Authorization": f"Bearer {login.get_json()['token']}"}
    preview = client.post(
        "/api/v1/admin/startup/provider-network/trusted-contacts/preview",
        headers=headers,
        json={"rows": [contact()]},
    )
    assert preview.status_code == 200
    assert preview.get_json()["can_apply"] is True
    assert client.post(
        "/api/v1/admin/startup/provider-network/trusted-contacts/apply",
        headers=headers,
        json={"rows": [contact()]},
    ).status_code == 400
    applied = client.post(
        "/api/v1/admin/startup/provider-network/trusted-contacts/apply",
        headers=headers,
        json={"apply": True, "rows": [contact()]},
    )
    assert applied.status_code == 201
    assert applied.get_json()["applied_count"] == 1

