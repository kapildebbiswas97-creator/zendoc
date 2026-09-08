from datetime import datetime, timedelta, timezone

from zendoc.db import get_db
from zendoc.startup_analytics import care_journey_conversion, provider_onboarding_funnel, retention_metrics
from tests.test_milestone1 import make_app


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def create_user(db, email, role="patient"):
    now = "2026-08-01T00:00:00+00:00"
    cursor = db.execute(
        "INSERT INTO users (name,email,email_normalized,password_hash,role,active,created_at,updated_at) VALUES (?,?,?,?,?,1,?,?)",
        ("User", email, email, "x", role, now, now),
    )
    return int(cursor.lastrowid)


def add_activity(db, user_id, when):
    db.execute(
        "INSERT INTO product_analytics_events (user_id,event_type,result_count,useful_result,source_tiers_json,metadata_json,created_at) VALUES (?,'session_login',0,0,'{}','{}',?)",
        (user_id, when),
    )


def test_exact_day_d7_d30_retention_uses_only_eligible_patient_cohorts(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        user_a = create_user(db, "ret-a@example.com")
        user_b = create_user(db, "ret-b@example.com")
        first = datetime(2026, 7, 1, tzinfo=timezone.utc)
        add_activity(db, user_a, first.isoformat())
        add_activity(db, user_a, (first + timedelta(days=7)).isoformat())
        add_activity(db, user_a, (first + timedelta(days=30)).isoformat())
        add_activity(db, user_b, first.isoformat())
        db.commit()

        metrics = retention_metrics(owner_actor(), as_of="2026-08-15T00:00:00+00:00")
        assert metrics["d7"]["eligible_users"] == 2
        assert metrics["d7"]["retained_users"] == 1
        assert metrics["d7"]["retention_rate"] == 0.5
        assert metrics["d30"]["eligible_users"] == 2
        assert metrics["d30"]["retained_users"] == 1
        assert metrics["d30"]["retention_rate"] == 0.5


def test_care_journey_funnel_counts_persisted_states_without_calling_staged_completed(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        patient = create_user(db, "journey@example.com")
        now = "2026-09-08T00:00:00+00:00"
        cursor = db.execute(
            "INSERT INTO care_journeys (journey_uid,patient_id,created_by,state,next_safe_action,status,created_at,updated_at) VALUES (?,?,?,?,?,'active',?,?)",
            ("journey-test-1", patient, patient, "APPOINTMENT_STAGED", "confirm appointment", now, now),
        )
        jid = int(cursor.lastrowid)
        db.execute(
            "INSERT INTO care_journey_events (journey_id,previous_state,state,reason,actor_type,actor_id,provenance_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (jid, "CONTEXT_READY", "PROVIDER_SEARCH", "search", "patient", patient, "{}", now),
        )
        db.execute(
            "INSERT INTO care_journey_events (journey_id,previous_state,state,reason,actor_type,actor_id,provenance_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (jid, "WAITING_USER_SELECTION", "APPOINTMENT_STAGED", "selected", "patient", patient, "{}", now),
        )
        db.commit()

        funnel = care_journey_conversion(owner_actor(), days=30)
        stages = {item["stage"]: item for item in funnel["stages"]}
        assert stages["started"]["journey_count"] == 1
        assert stages["provider_search"]["journey_count"] == 1
        assert stages["appointment_staged"]["journey_count"] == 1
        assert stages["consultation"]["journey_count"] == 0
        assert stages["completed"]["journey_count"] == 0


def test_provider_onboarding_funnel_tracks_real_milestones_independently(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        provider_user = create_user(db, "provider-funnel@example.com", role="doctor")
        now = "2026-09-08T00:00:00+00:00"
        cursor = db.execute(
            """
            INSERT INTO provider_profiles
            (user_id,provider_type,specialty,qualifications,license_identifier,organization,address,city,state,postal_code,public_phone,verification_status,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,'verified',?,?)
            """,
            (
                provider_user, "doctor", "Cardiology", "MBBS", "REG-1", "Clinic",
                "1 Road", "Kalyani", "West Bengal", "741235", "1234567890", now, now,
            ),
        )
        profile_id = int(cursor.lastrowid)
        db.execute(
            "INSERT INTO provider_verification_evidence (provider_profile_id,evidence_type,identifier,source_name,status,submitted_by,created_at,reviewed_at) VALUES (?,?,?,?, 'verified',?,?,?)",
            (profile_id, "professional_registration", "REG-1", "Official Registry", provider_user, now, now),
        )
        db.execute(
            "INSERT INTO provider_schedules (provider_profile_id,weekday,start_time,end_time,slot_minutes,active,created_at,updated_at) VALUES (?,0,'09:00','12:00',30,1,?,?)",
            (profile_id, now, now),
        )
        db.commit()

        funnel = provider_onboarding_funnel(owner_actor(), days=90)
        stages = {item["stage"]: item for item in funnel["stages"]}
        assert stages["profile_created"]["provider_count"] == 1
        assert stages["profile_complete"]["provider_count"] == 1
        assert stages["evidence_submitted"]["provider_count"] == 1
        assert stages["evidence_verified"]["provider_count"] == 1
        assert stages["provider_verified"]["provider_count"] == 1
        assert stages["schedule_published"]["provider_count"] == 1
