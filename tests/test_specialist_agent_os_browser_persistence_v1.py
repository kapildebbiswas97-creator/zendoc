import re
from datetime import datetime, timedelta, timezone

from tests.test_milestone1 import csrf, login_web, make_client, register_web
from zendoc.db import get_db, now_iso


def _seed_connected_provider(app, patient_email):
    target = datetime.now(timezone.utc).date() + timedelta(days=11)
    weekday = target.weekday()
    stamp = now_iso()
    with app.app_context():
        db = get_db()
        patient = db.execute(
            "SELECT * FROM users WHERE email_normalized=?",
            (patient_email.lower(),),
        ).fetchone()
        doctor_id = db.execute(
            """
            INSERT INTO users
            (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
            VALUES ('Dr Browser Sen','browser-agent-doctor@example.test','browser-agent-doctor@example.test',
                    'unused','doctor',1,?,?)
            """,
            (stamp, stamp),
        ).lastrowid
        profile_id = db.execute(
            """
            INSERT INTO provider_profiles
            (user_id,provider_type,specialty,organization,address,city,state,postal_code,
             verification_status,created_at,updated_at)
            VALUES (?,'doctor','Cardiology','Browser Heart Clinic','Station Road','Kalyani',
                    'West Bengal','741235','verified',?,?)
            """,
            (doctor_id, stamp, stamp),
        ).lastrowid
        db.execute(
            """
            INSERT INTO provider_schedules
            (provider_profile_id,weekday,start_time,end_time,slot_minutes,active,
             organization_id,organization_location_id,created_at,updated_at)
            VALUES (?,?,?,?,30,1,NULL,NULL,?,?)
            """,
            (profile_id, weekday, "09:00", "10:00", stamp, stamp),
        )
        db.commit()
        return int(patient["id"]), int(profile_id), target


def _latest_workflow_refs(app, patient_id):
    with app.app_context():
        db = get_db()
        task = db.execute(
            """
            SELECT id,status FROM agent_tasks
            WHERE requested_by=? AND task_type='specialist_workflow:appointment_booking'
            ORDER BY id DESC LIMIT 1
            """,
            (patient_id,),
        ).fetchone()
        journey = db.execute(
            "SELECT id,state FROM care_journeys WHERE patient_id=? ORDER BY id DESC LIMIT 1",
            (patient_id,),
        ).fetchone()
        return dict(task), dict(journey)


def test_browser_agent_os_booking_preserves_workflow_and_provider_confirmation_boundary(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENDOC_PLACES_PROVIDER", "none")
    app, client = make_client(tmp_path)
    email = "browser-agent-patient@example.test"
    register_web(client, "patient", email, "Browser Agent Patient")
    login_web(client, "patient", email)
    patient_id, profile_id, target = _seed_connected_provider(app, email)

    page = client.get("/agent-os")
    response = client.post(
        "/agent-os",
        data={
            "csrf_token": csrf(page.data.decode()),
            "command": "Book appointment with a cardiologist in Kalyani next week",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    html = response.data.decode()
    first_task, journey = _latest_workflow_refs(app, patient_id)
    assert first_task["status"] == "waiting_human"
    assert journey["state"] == "WAITING_USER_SELECTION"
    assert f'name="workflow_task_id" value="{first_task["id"]}"' in html
    assert f'name="journey_id" value="{journey["id"]}"' in html

    response = client.post(
        "/agent-os",
        data={
            "csrf_token": csrf(html),
            "command": "Book appointment with a cardiologist",
            "provider_profile_id": str(profile_id),
            "date": target.isoformat(),
            "workflow_task_id": str(first_task["id"]),
            "journey_id": str(journey["id"]),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    html = response.data.decode()
    second_task, staged_journey = _latest_workflow_refs(app, patient_id)
    assert second_task["id"] != first_task["id"]
    assert second_task["status"] == "waiting_human"
    assert staged_journey["id"] == journey["id"]
    assert staged_journey["state"] == "APPOINTMENT_STAGED"
    assert 'action="/agent-os/booking/confirm"' in html
    assert f'name="workflow_task_id" value="{second_task["id"]}"' in html
    assert f'name="journey_id" value="{journey["id"]}"' in html

    with app.app_context():
        db = get_db()
        assert db.execute(
            "SELECT status FROM agent_tasks WHERE id=?", (first_task["id"],)
        ).fetchone()["status"] == "completed"
        assert db.execute(
            "SELECT COUNT(*) AS c FROM appointments WHERE patient_id=?", (patient_id,)
        ).fetchone()["c"] == 0

    slot_match = re.search(r'name="scheduled_for" value="([^"]+)"', html)
    assert slot_match is not None
    scheduled_for = slot_match.group(1)

    response = client.post(
        "/agent-os/booking/confirm",
        data={
            "csrf_token": csrf(html),
            "provider_profile_id": str(profile_id),
            "scheduled_for": scheduled_for,
            "reason": "Cardiology consultation",
            "workflow_task_id": str(second_task["id"]),
            "journey_id": str(journey["id"]),
            "user_confirmed": "true",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Provider confirmation is still pending" in response.data

    with app.app_context():
        db = get_db()
        appointment = db.execute(
            "SELECT status FROM appointments WHERE patient_id=? ORDER BY id DESC LIMIT 1",
            (patient_id,),
        ).fetchone()
        persisted_journey = db.execute(
            "SELECT state,required_actor FROM care_journeys WHERE id=?",
            (journey["id"],),
        ).fetchone()
        assert appointment["status"] == "requested"
        assert persisted_journey["state"] == "WAITING_PROVIDER"
        assert persisted_journey["required_actor"] == "provider"
        assert db.execute(
            "SELECT status FROM agent_tasks WHERE id=?", (second_task["id"],)
        ).fetchone()["status"] == "completed"


def test_browser_booking_confirmation_requires_persisted_agent_os_refs_before_side_effect(tmp_path):
    app, client = make_client(tmp_path)
    email = "browser-agent-ref-check@example.test"
    register_web(client, "patient", email, "Browser Ref Patient")
    login_web(client, "patient", email)
    patient_id, profile_id, target = _seed_connected_provider(app, email)

    page = client.get("/agent-os")
    response = client.post(
        "/agent-os/booking/confirm",
        data={
            "csrf_token": csrf(page.data.decode()),
            "provider_profile_id": str(profile_id),
            "scheduled_for": f"{target.isoformat()}T09:00",
            "reason": "Should be blocked before booking",
            "user_confirmed": "true",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"requires its persisted Agent OS task and Care Journey references" in response.data

    with app.app_context():
        count = get_db().execute(
            "SELECT COUNT(*) AS c FROM appointments WHERE patient_id=?", (patient_id,)
        ).fetchone()["c"]
        assert count == 0


def test_agent_os_browser_booking_confirmation_route_is_registered(tmp_path):
    app, _client = make_client(tmp_path)
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/agent-os/booking/confirm" in rules
