from tests.test_milestone1 import login_web, make_client, register_web


PUBLIC_CRITICAL_GETS = (
    "/",
    "/login",
    "/register",
    "/healthz",
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
)


def _assert_no_missing_or_server_error(client, paths):
    failures = []
    for path in paths:
        response = client.get(path, follow_redirects=False)
        if response.status_code == 404 or response.status_code >= 500:
            failures.append((path, response.status_code))
    assert not failures, f"Critical ZENDOC routes failed smoke gate: {failures}"


def test_public_submission_routes_have_no_404_or_5xx(tmp_path):
    _app, client = make_client(tmp_path)
    _assert_no_missing_or_server_error(client, PUBLIC_CRITICAL_GETS)


def test_patient_submission_routes_have_no_404_or_5xx(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "submission-smoke@example.com", "Submission Smoke")
    login_web(client, "patient", "submission-smoke@example.com")
    _assert_no_missing_or_server_error(client, PATIENT_CRITICAL_GETS)
