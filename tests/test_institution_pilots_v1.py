from zendoc.institution_pilots import create_institution_pilot, institution_pilot_metrics, update_institution_pilot
from tests.test_milestone1 import make_app, make_client


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def test_institution_pilot_tracks_real_status_and_commercial_conversion(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        pilot = create_institution_pilot(
            owner_actor(),
            {
                "organization_name": "Pilot Hospital",
                "organization_type": "hospital",
                "state": "West Bengal",
                "district": "Nadia",
                "status": "active",
                "commercial_status": "loi",
                "target_users": 100,
                "target_provider_seats": 10,
                "agreed_features": ["healthcare discovery", "provider onboarding"],
                "success_metrics": ["useful result rate", "repeat users"],
                "monthly_value_inr": 5000,
            },
        )
        assert pilot["status"] == "active"
        assert pilot["commercial_status"] == "loi"

        metrics = institution_pilot_metrics(owner_actor())
        assert metrics["pilot_count"] == 1
        assert metrics["active_pilots"] == 1
        assert metrics["paid_pilots"] == 0
        assert metrics["entered_monthly_value_inr"] == 0

        updated = update_institution_pilot(
            owner_actor(),
            pilot["id"],
            {"status": "converted", "commercial_status": "paid", "monthly_value_inr": 5000},
        )
        assert updated["status"] == "converted"
        assert updated["commercial_status"] == "paid"

        metrics = institution_pilot_metrics(owner_actor())
        assert metrics["converted_pilots"] == 1
        assert metrics["paid_pilots"] == 1
        assert metrics["entered_monthly_value_inr"] == 5000


def test_institution_pilot_rejects_negative_fake_value(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        failed = False
        try:
            create_institution_pilot(
                owner_actor(),
                {
                    "organization_name": "Invalid Pilot",
                    "organization_type": "hospital",
                    "monthly_value_inr": -1,
                },
            )
        except ValueError:
            failed = True
        assert failed is True


def test_institution_pilot_api_is_owner_only(tmp_path):
    _app, client = make_client(tmp_path)

    denied = client.get("/api/v1/admin/startup/pilots")
    assert denied.status_code in {302, 401, 403}

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminStrong123"},
    )
    token = login.get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/v1/admin/startup/pilots",
        headers=headers,
        json={"organization_name": "API Pilot", "organization_type": "ngo"},
    )
    assert created.status_code == 201

    listed = client.get("/api/v1/admin/startup/pilots", headers=headers)
    assert listed.status_code == 200
    assert listed.get_json()["metrics"]["pilot_count"] == 1
