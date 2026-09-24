from urllib.parse import urlsplit

from zendoc.universal_search import PLATFORM_TOOL_CATALOG
from tests.test_milestone1 import login_web, make_app, register_web


def test_patient_platform_catalog_links_do_not_404_or_500(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "launch-surface-smoke@example.com", "Launch Surface Smoke")
    login_web(client, "patient", "launch-surface-smoke@example.com")

    failures = []
    for item in PLATFORM_TOOL_CATALOG:
        path = urlsplit(item["url"]).path or "/"
        response = client.get(path)
        if response.status_code == 404 or response.status_code >= 500:
            failures.append((item["title"], path, response.status_code))

    assert failures == []


def test_core_patient_surfaces_are_reachable_without_server_errors(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "core-surface-smoke@example.com", "Core Surface Smoke")
    login_web(client, "patient", "core-surface-smoke@example.com")

    paths = (
        "/dashboard",
        "/finder",
        "/messages",
        "/mental-wellness",
        "/payments",
        "/health-shop",
        "/health-summary",
        "/connected-care",
        "/connected-care/journey",
        "/carefin",
        "/community",
        "/fitness",
        "/family",
        "/ai",
        "/videos",
        "/ambulance",
        "/pharmacy",
        "/marketplace",
        "/care-os",
        "/health-hub",
    )

    failures = []
    for path in paths:
        response = client.get(path)
        if response.status_code == 404 or response.status_code >= 500:
            failures.append((path, response.status_code))

    assert failures == []
