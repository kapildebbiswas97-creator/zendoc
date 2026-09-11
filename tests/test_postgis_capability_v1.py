from __future__ import annotations

from tests.test_milestone1 import make_app
from zendoc.database_reliability import postgis_status, readiness_report


def test_sqlite_reports_postgis_not_configured_without_acceleration(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        status = postgis_status()
        assert status["status"] == "POSTGIS_NOT_CONFIGURED"
        assert status["available"] is False
        assert status["spatial_index_acceleration"] is False

        report = readiness_report()
        assert report["postgis"]["status"] == "POSTGIS_NOT_CONFIGURED"
        assert report["postgis"]["spatial_index_acceleration"] is False

