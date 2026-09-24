from tests.test_milestone1 import login_web, make_client, register_web
from zendoc.copilot import copilot_context


def test_diagnostics_context_wins_over_broad_connected_care_context():
    context = copilot_context("connected_care.diagnostics_page", "patient")

    assert context is not None
    assert context["key"] == "diagnostics"
    assert context["actions"] == [
        {"label": "Diagnostics", "endpoint": "connected_care.diagnostics_page"}
    ]


def test_government_role_has_explicit_institutional_context_and_unknown_roles_fail_closed():
    government = copilot_context("main.dashboard", "government")

    assert government is not None
    assert government["key"] == "government_workspace"
    assert government["title"] == "Public Health Workspace Copilot"
    assert government["agent_command"] is None
    assert "patient" not in government["description"].lower()

    assert copilot_context("main.dashboard", "future_role") is None
    assert copilot_context("main.dashboard", None) is None


def test_all_copilot_actions_point_to_registered_flask_endpoints(tmp_path):
    app, _client = make_client(tmp_path)

    contexts = [
        ("main.dashboard", "admin"),
        ("main.dashboard", "doctor"),
        ("main.dashboard", "government"),
        ("main.dashboard", "patient"),
        ("universal_search.search_home", "patient"),
        ("health_memory.health_summary_page", "patient"),
        ("main.appointments", "patient"),
        ("milestone7.messages_page", "patient"),
        ("mental_wellness.mental_wellness_page", "patient"),
        ("family.family_page", "patient"),
        ("fitness.overview", "patient"),
        ("health_social.community_page", "patient"),
        ("health_shop.health_shop_page", "patient"),
        ("payments.payments_page", "patient"),
        ("connected_care.care_journey_page", "patient"),
        ("connected_care.diagnostics_page", "patient"),
        ("carefin.carefin_page", "patient"),
        ("ecosystem.pharmacy_page", "patient"),
        ("ecosystem.iot_hub_page", "patient"),
        ("main.profile", "patient"),
    ]

    for endpoint, role in contexts:
        context = copilot_context(endpoint, role)
        assert context is not None, (endpoint, role)
        for action in context.get("actions", []):
            assert action["endpoint"] in app.view_functions, (
                endpoint,
                role,
                action["endpoint"],
            )

    assert "ai_chat.chat_home" in app.view_functions
    assert "specialist_agents.agent_os_page" in app.view_functions


def test_authenticated_patient_shell_renders_context_aware_copilot(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "copilot-shell@example.com", "Copilot Shell")
    login_web(client, "patient", "copilot-shell@example.com")

    response = client.get("/dashboard")

    assert response.status_code == 200
    assert b"data-zendoc-copilot" in response.data
    assert b'data-copilot-key="dashboard"' in response.data
    assert b"ZENDOC Copilot" in response.data
    assert b"AI helps; ZENDOC rules execute." in response.data
    assert b'aria-expanded="false"' in response.data
    assert b'aria-controls="zendoc-copilot-panel"' in response.data


def test_anonymous_shell_does_not_render_private_copilot(tmp_path):
    _app, client = make_client(tmp_path)

    response = client.get("/")

    assert response.status_code == 200
    assert b"data-zendoc-copilot" not in response.data


def test_copilot_ai_draft_is_editable_contextual_and_html_escaped(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "copilot-draft@example.com", "Copilot Draft")
    login_web(client, "patient", "copilot-draft@example.com")

    malicious = '</textarea><script>alert("zendoc")</script>'
    response = client.get(
        "/ai",
        query_string={
            "new": "1",
            "draft": malicious,
            "context": "health_memory",
        },
    )

    assert response.status_code == 200
    assert b"Opened from Health Memory" in response.data
    assert malicious.encode() not in response.data
    assert b"&lt;/textarea&gt;" in response.data
    assert b"&lt;script&gt;" in response.data
    assert b"edit before sending" in response.data


def test_ai_context_badge_rejects_untrusted_or_spoofed_context(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "copilot-context@example.com", "Copilot Context")
    login_web(client, "patient", "copilot-context@example.com")

    response = client.get(
        "/ai",
        query_string={
            "new": "1",
            "draft": "Explain this page",
            "context": "admin_superuser_spoof",
        },
    )

    assert response.status_code == 200
    assert b"Opened from Admin Superuser Spoof" not in response.data
    assert b"edit before sending" not in response.data
