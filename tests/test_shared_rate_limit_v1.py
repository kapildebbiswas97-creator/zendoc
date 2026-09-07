from tests.test_milestone1 import make_client


def test_database_rate_limit_is_shared_across_clients(tmp_path):
    app, client_a = make_client(tmp_path)
    client_b = app.test_client()

    app.config["TESTING"] = False
    app.config["RATE_LIMIT_PER_MINUTE"] = 2

    first = client_a.get("/api/v1/dashboard")
    second = client_b.get("/api/v1/dashboard")
    third = client_a.get("/api/v1/dashboard")

    assert first.status_code == 401
    assert second.status_code == 401
    assert third.status_code == 429

    with app.app_context():
        from zendoc.db import get_db
        row = get_db().execute(
            "SELECT count FROM api_rate_limit_buckets ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        assert int(row["count"]) >= 3
