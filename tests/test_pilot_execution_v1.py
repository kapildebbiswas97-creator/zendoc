from zendoc.institution_pilots import (
    create_institution_pilot,
    create_pilot_milestone,
    pilot_execution_summary,
    record_pilot_usage_snapshot,
)
from tests.test_milestone1 import make_app, make_client


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def test_pilot_execution_separates_targets_from_observed_usage(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        pilot = create_institution_pilot(
            owner_actor(),
            {
                "organization_name": "Execution Hospital",
                "organization_type": "hospital",
                "status": "active",
                "target_users": 100,
                "target_provider_seats": 10,
            },
        )
        create_pilot_milestone(
            owner_actor(),
            pilot["id"],
            {"title": "Provider onboarding", "status": "completed"},
        )
        create_pilot_milestone(
            owner_actor(),
            pilot["id"],
            {"title": "First user cohort", "status": "in_progress"},
        )
        record_pilot_usage_snapshot(
            owner_actor(),
            pilot["id"],
            {
                "observed_at": "2026-09-08T10:00:00+00:00",
                "active_users": 25,
                "active_providers": 5,
                "healthcare_searches": 80,
                "completed_handoffs": 3,
                "api_requests": 40,
                "source_type": "owner_entered_observed",
            },
        )

        execution = pilot_execution_summary(owner_actor(), pilot["id"])
        assert execution["user_progress"]["actual"] == 25
        assert execution["user_progress"]["target"] == 100
        assert execution["user_progress"]["progress_rate"] == 0.25
        assert execution["provider_progress"]["actual"] == 5
        assert execution["provider_progress"]["target"] == 10
        assert execution["provider_progress"]["progress_rate"] == 0.5
        assert execution["milestone_completion_rate"] == 0.5
        assert execution["latest_usage"]["source_type"] == "owner_entered_observed"


def test_manual_entry_cannot_claim_system_derived_usage(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        pilot = create_institution_pilot(
            owner_actor(),
            {"organization_name": "Truthful Pilot", "organization_type": "ngo"},
        )
        failed = False
        try:
            record_pilot_usage_snapshot(
                owner_actor(),
                pilot["id"],
                {
                    "active_users": 10,
                    "source_type": "system_derived",
                },
            )
        except ValueError:
            failed = True
        assert failed is True


def test_pilot_execution_api_is_owner_only(tmp_path):
    _app, client = make_client(tmp_path)
    assert client.get("/api/v1/admin/startup/pilots/1/execution").status_code in {302, 401, 403}

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminStrong123"},
    )
    token = login.get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/v1/admin/startup/pilots",
        headers=headers,
        json={"organization_name": "API Execution Pilot", "organization_type": "hospital", "target_users": 50},
    )
    assert created.status_code == 201
    pilot_id = created.get_json()["pilot"]["id"]

    milestone = client.post(
        f"/api/v1/admin/startup/pilots/{pilot_id}/milestones",
        headers=headers,
        json={"title": "Launch", "status": "planned"},
    )
    assert milestone.status_code == 201

    usage = client.post(
        f"/api/v1/admin/startup/pilots/{pilot_id}/usage",
        headers=headers,
        json={"active_users": 5, "source_type": "owner_entered_observed"},
    )
    assert usage.status_code == 201

    execution = client.get(
        f"/api/v1/admin/startup/pilots/{pilot_id}/execution",
        headers=headers,
    )
    assert execution.status_code == 200
    payload = execution.get_json()["execution"]
    assert payload["pilot"]["id"] == pilot_id
    assert payload["latest_usage"]["active_users"] == 5
