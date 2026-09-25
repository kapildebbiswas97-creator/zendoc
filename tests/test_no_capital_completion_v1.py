from tests.test_milestone1 import make_app
from zendoc.no_capital_status import no_capital_completion_report


def test_named_no_capital_software_scope_is_100_percent_working(tmp_path):
    app = make_app(tmp_path)

    with app.app_context():
        report = no_capital_completion_report()

    scope = report["software_no_capital_scope"]
    assert scope["total"] > 0
    assert scope["working"] == scope["total"], scope["capabilities"]
    assert scope["beta"] == 0
    assert scope["incomplete"] == 0
    assert scope["working_percent"] == 100.0


def test_100_percent_software_scope_does_not_hide_external_dependencies(tmp_path):
    app = make_app(tmp_path)

    with app.app_context():
        report = no_capital_completion_report()

    assert report["integration_dependencies"]
    assert report["partner_dependencies"]
    assert report["physical_capital_dependencies"]
    assert "does not represent regulatory approval" in report["disclaimer"].lower()
