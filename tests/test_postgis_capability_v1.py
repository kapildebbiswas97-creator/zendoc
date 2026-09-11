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


def test_readiness_keeps_database_failure_reportable_before_optional_postgis_probe(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    with app.app_context():
        monkeypatch.setattr(
            "zendoc.database_reliability.database_probe",
            lambda: (_ for _ in ()).throw(RuntimeError("database unavailable")),
        )
        monkeypatch.setattr(
            "zendoc.database_reliability.postgis_status",
            lambda: (_ for _ in ()).throw(AssertionError("optional probe must not run")),
        )
        report = readiness_report()
        assert report["status"] == "not_ready"
        assert report["database"] == "unreachable"

