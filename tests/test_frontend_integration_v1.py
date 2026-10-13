"""Rendered frontend integration against real Flask sessions and booking state."""
from html.parser import HTMLParser

import pytest

from tests.test_milestone1 import csrf, login_web, make_client, register_web
from tests.test_milestone3 import create_verified_doctor, next_weekday_date
from zendoc.db import get_db


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def find(self, tag, **attrs):
        return [item for kind, item in self.elements if kind == tag and all(item.get(key) == value for key, value in attrs.items())]


@pytest.mark.parametrize("role", ["patient", "doctor", "hospital", "pharmacy"])
def test_patient_shortcuts_and_dock_respect_authenticated_role(tmp_path, role):
    _app, client = make_client(tmp_path)
    email = f"stitch-{role}@example.test"
    assert register_web(client, role, email).status_code == 200
    assert login_web(client, role, email).status_code == 200
    page = client.get("/dashboard")
    assert page.status_code == 200
    elements = Elements(page.get_data(as_text=True))
    assert bool(elements.find("section", **{"class": "stitch-patient-intro"})) == (role == "patient")
    assert bool(elements.find("nav", **{"class": "patient-mobile-dock"})) == (role == "patient")


def test_find_care_keeps_navigation_context_after_universal_search(tmp_path):
    _app, client = make_client(tmp_path)
    register_web(client, "patient", "stitch-find@example.test")
    login_web(client, "patient", "stitch-find@example.test")
    page = client.get("/universal-search")
    assert page.status_code == 200
    elements = Elements(page.get_data(as_text=True))
    current = elements.find("a", **{"class": "mobile-dock-link", "aria-current": "page"})
    assert len(current) == 1
    assert current[0]["href"] == "/finder"
    assert elements.find("form", method="get", action="/universal-search")
    assert elements.find("details", **{"class": "nav-menu", "data-active": "true"})


def test_refreshed_provider_booking_escapes_profile_and_persists_only_authorized_request(tmp_path):
    app, client = make_client(tmp_path)
    _token, profile_id = create_verified_doctor(app, client)
    appointment_date = next_weekday_date(0).isoformat()
    hostile_name = '<img src=x onerror="alert(1)">'
    with app.app_context():
        db = get_db()
        db.execute("UPDATE provider_profiles SET organization=? WHERE id=?", (hostile_name, profile_id))
        db.execute(
            """INSERT INTO provider_schedules
            (provider_profile_id,weekday,start_time,end_time,slot_minutes,active,created_at,updated_at)
            VALUES (?,0,'10:00','11:00',30,1,'now','now')""", (profile_id,),
        )
        db.commit()
    register_web(client, "patient", "stitch-booker@example.test")
    login_web(client, "patient", "stitch-booker@example.test")
    page = client.get(f"/providers/{profile_id}?date={appointment_date}")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert hostile_name not in body
    assert "&lt;img src=x onerror=" in body
    elements = Elements(body)
    assert elements.find("section", **{"class": "stitch-provider-showcase"})
    assert elements.find("form", method="post", action="/appointments")
    slots = elements.find("input", type="radio", name="scheduled_for")
    assert slots
    payload = {"provider_profile_id": profile_id, "scheduled_for": slots[0]["value"], "reason": "Synthetic frontend booking regression"}
    assert client.post("/appointments", data=payload).status_code == 400
    payload["csrf_token"] = csrf(body)
    response = client.post("/appointments", data=payload, follow_redirects=True)
    assert response.status_code == 200
    assert "Synthetic frontend booking regression" in response.get_data(as_text=True)
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) AS n FROM appointments WHERE reason=?", (payload["reason"],)).fetchone()["n"] == 1
    other = app.test_client()
    register_web(other, "patient", "stitch-other@example.test")
    login_web(other, "patient", "stitch-other@example.test")
    assert payload["reason"] not in other.get("/appointments").get_data(as_text=True)


def test_landing_scenario_tabs_have_matching_accessible_panels(tmp_path):
    _app, client = make_client(tmp_path)
    elements = Elements(client.get("/").get_data(as_text=True))
    tabs = elements.find("button", role="tab")
    panels = elements.find("div", role="tabpanel")
    assert len(tabs) == len(panels) == 4
    assert sum(tab["tabindex"] == "0" for tab in tabs) == 1
    for tab in tabs:
        panel = next(panel for panel in panels if panel["id"] == tab["aria-controls"])
        assert panel["aria-labelledby"] == tab["id"]
        assert ("hidden" not in panel) == (tab["aria-selected"] == "true")


def test_auth_pages_render_accessible_forms_and_panels(tmp_path):
    _app, client = make_client(tmp_path)
    login_page = client.get("/login")
    assert login_page.status_code == 200
    elements = Elements(login_page.get_data(as_text=True))
    assert elements.find("section", **{"class": "auth-panel"})
    assert elements.find("input", name="email", type="email")
    assert elements.find("input", name="password", type="password")
    assert elements.find("input", name="csrf_token", type="hidden")

    reg_page = client.get("/register", follow_redirects=True)
    assert reg_page.status_code == 200
    reg_elements = Elements(reg_page.get_data(as_text=True))
    assert reg_elements.find("section", **{"class": "auth-panel"})
    assert reg_elements.find("input", name="name")
    assert reg_elements.find("input", name="email", type="email")
    assert reg_elements.find("input", name="password", type="password")


def test_health_memory_and_appointments_views_render_panels(tmp_path):
    _app, client = make_client(tmp_path)
    email = "stitch-memory@example.test"
    register_web(client, "patient", email)
    login_web(client, "patient", email)

    appts = client.get("/appointments")
    assert appts.status_code == 200
    appt_elements = Elements(appts.get_data(as_text=True))
    assert appt_elements.find("article", **{"class": "panel"})
    assert appt_elements.find("span", **{"class": "count-pill"})

    recs = client.get("/records")
    assert recs.status_code == 200
    rec_elements = Elements(recs.get_data(as_text=True))
    assert rec_elements.find("form", **{"class": "panel", "method": "post"})
    assert rec_elements.find("input", name="record_file", type="file")


def test_pharmacy_and_agent_os_render_bounded_workflows(tmp_path):
    _app, client = make_client(tmp_path)
    email = "stitch-bounded@example.test"
    register_web(client, "patient", email)
    login_web(client, "patient", email)

    pharm = client.get("/pharmacy")
    assert pharm.status_code == 200
    pharm_elements = Elements(pharm.get_data(as_text=True))
    assert pharm_elements.find("form", **{"role": "search"})
    assert pharm_elements.find("aside", **{"class": "trust-note warning"})

    agent = client.get("/agent-os")
    assert agent.status_code == 200
    agent_elements = Elements(agent.get_data(as_text=True))
    assert agent_elements.find("section", **{"aria-label": "Personal AI agent"})
    assert agent_elements.find("form", method="post")

