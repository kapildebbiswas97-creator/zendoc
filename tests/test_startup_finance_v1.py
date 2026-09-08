from zendoc.investor_dashboard import investor_traction_snapshot
from zendoc.startup_finance import create_financial_entry, create_financial_snapshot, financial_kpis
from tests.test_milestone1 import make_app, make_client


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def test_financial_kpis_compute_revenue_cost_burn_and_runway_from_real_entries(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        create_financial_entry(
            owner_actor(),
            {
                "entry_date": "2026-09-01",
                "entry_type": "revenue",
                "category": "subscription",
                "amount_inr": 10000,
                "recurring": True,
                "description": "Real subscription revenue",
            },
        )
        create_financial_entry(
            owner_actor(),
            {
                "entry_date": "2026-09-02",
                "entry_type": "cost",
                "category": "cloud",
                "amount_inr": 15000,
                "recurring": True,
            },
        )
        create_financial_snapshot(
            owner_actor(),
            {"snapshot_month": "2026-09", "cash_balance_inr": 50000},
        )

        kpis = financial_kpis(owner_actor(), month="2026-09")
        assert kpis["revenue_inr"] == 10000
        assert kpis["recurring_revenue_inr"] == 10000
        assert kpis["costs_inr"] == 15000
        assert kpis["net_cash_flow_inr"] == -5000
        assert kpis["net_burn_inr"] == 5000
        assert kpis["cash_balance_inr"] == 50000
        assert kpis["runway_months"] == 10


def test_finance_rejects_category_type_mismatch_and_negative_amount(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        failed_category = False
        try:
            create_financial_entry(
                owner_actor(),
                {
                    "entry_date": "2026-09-01",
                    "entry_type": "revenue",
                    "category": "cloud",
                    "amount_inr": 100,
                },
            )
        except ValueError:
            failed_category = True
        assert failed_category is True

        failed_amount = False
        try:
            create_financial_entry(
                owner_actor(),
                {
                    "entry_date": "2026-09-01",
                    "entry_type": "cost",
                    "category": "cloud",
                    "amount_inr": -1,
                },
            )
        except ValueError:
            failed_amount = True
        assert failed_amount is True


def test_investor_snapshot_keeps_missing_traction_as_not_yet(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        snapshot = investor_traction_snapshot(owner_actor(), days=30, finance_month="2026-09")
        assert snapshot["readiness"]["product_usage_observed"] is False
        assert snapshot["readiness"]["d7_retention_measurable"] is False
        assert snapshot["readiness"]["d30_retention_measurable"] is False
        assert snapshot["readiness"]["institution_demand_observed"] is False
        assert snapshot["readiness"]["paid_revenue_recorded"] is False
        assert snapshot["readiness"]["cash_runway_measurable"] is False


def test_finance_and_investor_apis_are_owner_only(tmp_path):
    _app, client = make_client(tmp_path)

    assert client.get("/api/v1/admin/startup/finance").status_code in {302, 401, 403}
    assert client.get("/api/v1/admin/startup/investor-snapshot").status_code in {302, 401, 403}

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminStrong123"},
    )
    token = login.get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/v1/admin/startup/finance/entries",
        headers=headers,
        json={
            "entry_date": "2026-09-01",
            "entry_type": "cost",
            "category": "cloud",
            "amount_inr": 250,
        },
    )
    assert created.status_code == 201

    finance = client.get(
        "/api/v1/admin/startup/finance?month=2026-09",
        headers=headers,
    )
    investor = client.get(
        "/api/v1/admin/startup/investor-snapshot?finance_month=2026-09",
        headers=headers,
    )
    assert finance.status_code == 200
    assert finance.get_json()["kpis"]["costs_inr"] == 250
    assert investor.status_code == 200
    assert investor.get_json()["snapshot"]["evidence"]["finance"]["costs_inr"] == 250
