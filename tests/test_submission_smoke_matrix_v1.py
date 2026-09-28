from html.parser import HTMLParser
from urllib.parse import urlsplit

from tests.test_milestone1 import login_web, make_client, register_web


PUBLIC_CRITICAL_GETS = (
    "/",
    "/login",
    "/register",
    "/healthz",
    "/privacy",
    "/terms",
    "/medical-disclaimer",
    "/account-deletion",
    "/resend-verification",
    "/manifest.webmanifest",
    "/sw.js",
    "/offline",
)

PATIENT_CRITICAL_GETS = (
    "/dashboard",
    "/finder",
    "/universal-search",
    "/ai?new=1",
    "/ai?mode=doctor&new=1",
    "/appointments",
    "/health-summary",
    "/timeline",
    "/records",
    "/health",
    "/health-access",
    "/messages",
    "/family",
    "/videos",
    "/profile",
    "/agent-os",
    "/care-continuity",
    "/account/export",
)


def _assert_no_missing_or_server_error(client, paths):
    failures = []
    for path in paths:
        response = client.get(path, follow_redirects=False)
        if response.status_code == 404 or response.status_code >= 500:
            failures.append((path, response.status_code))
    assert not failures, f"Critical ZENDOC routes failed smoke gate: {failures}"


class _LinkCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.hrefs.append(href)


def _local_get_links(html):
    parser = _LinkCollector()
    parser.feed(html)
    paths = set()
    for href in parser.hrefs:
        value = str(href or "").strip()
        if not value or value.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc:
            continue
        path = parsed.path or "/"
        if path in {"/logout"}:
            continue
        target = path + (f"?{parsed.query}" if parsed.query else "")
        paths.add(target)
    return sorted(paths)


def _assert_rendered_navigation_is_live(client, entry_paths):
    checked = set()
    failures = []
    for entry in entry_paths:
        page = client.get(entry, follow_redirects=False)
        if page.status_code == 404 or page.status_code >= 500:
            failures.append((entry, page.status_code, "entry"))
            continue
        if page.status_code != 200 or "text/html" not in str(page.content_type or ""):
            continue
        for target in _local_get_links(page.get_data(as_text=True)):
            if target in checked:
                continue
            checked.add(target)
            response = client.get(target, follow_redirects=False)
            if response.status_code in {403, 404} or response.status_code >= 500:
                failures.append((target, response.status_code, f"linked from {entry}"))
    assert not failures, f"Rendered ZENDOC navigation contains broken local links: {failures}"


def test_public_submission_routes_have_no_404_or_5xx(tmp_path):
    _app, client = make_client(tmp_path)
    _assert_no_missing_or_server_error(client, PUBLIC_CRITICAL_GETS)


def test_patient_submission_routes_have_no_404_or_5xx(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "submission-smoke@example.com", "Submission Smoke")
    login_web(client, "patient", "submission-smoke@example.com")
    _assert_no_missing_or_server_error(client, PATIENT_CRITICAL_GETS)



def test_patient_rendered_navigation_has_no_404_or_5xx(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "navigation-patient@example.com", "Navigation Patient")
    login_web(client, "patient", "navigation-patient@example.com")
    _assert_rendered_navigation_is_live(
        client,
        (
            "/dashboard",
            "/health-hub",
            "/finder",
            "/messages",
            "/mental-wellness",
            "/family",
        ),
    )


def test_provider_rendered_navigation_has_no_404_or_5xx(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "doctor", "navigation-doctor@example.com", "Navigation Doctor")
    login_web(client, "doctor", "navigation-doctor@example.com")
    _assert_rendered_navigation_is_live(
        client,
        (
            "/dashboard",
            "/provider/profile",
            "/appointments",
            "/messages",
        ),
    )


def test_owner_rendered_navigation_has_no_404_or_5xx(tmp_path):
    _app, client = make_client(tmp_path)
    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    _assert_rendered_navigation_is_live(
        client,
        (
            "/admin",
            "/admin/startup",
            "/admin/integrations",
            "/admin/dashboard-preview/patient",
            "/admin/dashboard-preview/doctor",
            "/admin/dashboard-preview/hospital",
            "/admin/dashboard-preview/pharmacy",
        ),
    )



def test_owner_is_denied_patient_fitness_route_without_server_error(tmp_path):
    _app, client = make_client(tmp_path)
    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    response = client.get("/fitness", follow_redirects=False)
    assert response.status_code == 403
