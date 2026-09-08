from datetime import datetime, timedelta, timezone

from zendoc.business_api import create_business_api_client
from zendoc.db import get_db
from zendoc.provider_operations import provider_operational_metrics
from tests.test_milestone1 import make_app


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def create_provider(db, *, email, name, role="doctor"):
    now = "2026-09-08T00:00:00+00:00"
    user_id = db.execute(
        """
        INSERT INTO users
        (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
        VALUES (?,?,?,?,?,1,?,?)
        """,
        (name, email, email, "x", role, now, now),
    ).lastrowid
    profile_id = db.execute(
        """
        INSERT INTO provider_profiles
        (user_id,provider_type,specialty,qualifications,license_identifier,organization,address,city,state,
         postal_code,public_phone,verification_status,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,'verified',?,?)
        """,
        (
            user_id,
            role,
            "Cardiology" if role == "doctor" else None,
            "Qualified",
            f"REG-{user_id}",
            f"{name} Org",
            "1 Road",
            "Kalyani",
            "West Bengal",
            "741235",
            "1234567890",
            now,
            now,
        ),
    ).lastrowid
    return int(user_id), int(profile_id)


def test_provider_operational_metrics_are_provider_scoped(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        provider_a, profile_a = create_provider(db, email="ops-a@example.com", name="Provider A")
        provider_b, profile_b = create_provider(db, email="ops-b@example.com", name="Provider B")

        now = "2026-09-08T00:00:00+00:00"
        db.execute(
            """
            INSERT INTO provider_schedules
            (provider_profile_id,weekday,start_time,end_time,slot_minutes,active,created_at,updated_at)
            VALUES (?,0,'09:00','10:00',30,1,?,?)
            """,
            (profile_a, now, now),
        )
        db.execute(
            """
            INSERT INTO provider_schedules
            (provider_profile_id,weekday,start_time,end_time,slot_minutes,active,created_at,updated_at)
            VALUES (?,0,'10:00','11:00',30,1,?,?)
            """,
            (profile_b, now, now),
        )

        partner = create_business_api_client(
            owner_actor(),
            {"name": "Ops Partner", "client_type": "hospital", "allowed_scopes": ["booking_handoff.write"]},
        )
        future_slot = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT09:00+00:00")
        handoff_a = db.execute(
            """
            INSERT INTO partner_booking_handoffs
            (handoff_uid,client_id,provider_profile_id,partner_reference,requested_for,status,created_at,updated_at)
            VALUES (?,?,?,?,?,'received',?,?)
            """,
            ("handoff-ops-a", partner["id"], profile_a, "OPS-A", future_slot, now, now),
        ).lastrowid
        db.execute(
            """
            INSERT INTO partner_booking_handoffs
            (handoff_uid,client_id,provider_profile_id,partner_reference,requested_for,status,created_at,updated_at)
            VALUES (?,?,?,?,?,'received',?,?)
            """,
            ("handoff-ops-b", partner["id"], profile_b, "OPS-B", future_slot, now, now),
        )
        db.execute(
            """
            INSERT INTO partner_slot_holds
            (client_id,provider_profile_id,slot_key,handoff_id,status,expires_at,created_at,updated_at)
            VALUES (?,?,?,?,'active',?,?,?)
            """,
            (
                partner["id"],
                profile_a,
                future_slot[:16],
                handoff_a,
                (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat(timespec="seconds"),
                now,
                now,
            ),
        )

        patient_id = db.execute(
            """
            INSERT INTO users
            (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
            VALUES ('Patient','ops-patient@example.com','ops-patient@example.com','x','patient',1,?,?)
            """,
            (now, now),
        ).lastrowid
        db.execute(
            """
            INSERT INTO appointments
            (patient_id,provider_id,provider_profile_id,provider_name,scheduled_for,reason,status,created_at,updated_at)
            VALUES (?,?,?,?,?,'','requested',?,?)
            """,
            (patient_id, provider_a, profile_a, "Provider A", future_slot, now, now),
        )
        db.execute(
            """
            INSERT INTO appointments
            (patient_id,provider_id,provider_profile_id,provider_name,scheduled_for,reason,status,created_at,updated_at)
            VALUES (?,?,?,?,?,'','confirmed',?,?)
            """,
            (patient_id, provider_b, profile_b, "Provider B", future_slot, now, now),
        )
        db.commit()

        metrics_a = provider_operational_metrics({"id": provider_a, "role": "doctor", "active": 1})
        metrics_b = provider_operational_metrics({"id": provider_b, "role": "doctor", "active": 1})

        assert metrics_a["provider_profile_id"] == profile_a
        assert metrics_a["active_schedules"] == 1
        assert metrics_a["active_slot_holds"] == 1
        assert metrics_a["handoff_total"] == 1
        assert metrics_a["appointment_status_counts"]["requested"] == 1
        assert "confirmed" not in metrics_a["appointment_status_counts"]

        assert metrics_b["provider_profile_id"] == profile_b
        assert metrics_b["active_slot_holds"] == 0
        assert metrics_b["handoff_total"] == 1
        assert metrics_b["appointment_status_counts"]["confirmed"] == 1
        assert "requested" not in metrics_b["appointment_status_counts"]

        assert "patient" not in str(metrics_a).lower()


def test_non_provider_cannot_read_provider_operational_metrics(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        blocked = False
        try:
            provider_operational_metrics({"id": 999, "role": "patient", "active": 1})
        except PermissionError:
            blocked = True
        assert blocked is True
