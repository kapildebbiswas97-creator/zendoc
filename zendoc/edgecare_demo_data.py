"""Development-only synthetic care fixture for the EdgeCare competition demo.

This module exists so a fresh local clone can demonstrate the complete
search -> verified profile -> published slot -> appointment flow without
pretending that a public directory or map listing is connected to ZENDOC.

The records are deliberately and visibly labelled DEMO ONLY. The seeder
refuses to run when ``ZENDOC_ENV=production`` and never contains a committed
password. A local password must be supplied through ``ZENDOC_DEMO_PASSWORD``.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from werkzeug.security import generate_password_hash

from . import create_app
from .db import get_db, now_iso


DEMO_DOCTOR_EMAIL = "demo-doctor@zendoc.local"
DEMO_PATIENT_EMAIL = "demo-patient@zendoc.local"
DEMO_DOCTOR_NAME = "DEMO ONLY — Dr Asha Test"
DEMO_PATIENT_NAME = "DEMO ONLY — Patient"
DEMO_ORGANIZATION = "DEMO ONLY — ZENDOC Test Heart Clinic"
DEMO_LICENSE = "DEMO-NOT-A-LICENSE"


def _normalized_env(name: str) -> str:
    return str(os.environ.get(name, "") or "").strip()


def _upsert_demo_user(db, *, email: str, name: str, role: str, password: str) -> int:
    now = now_iso()
    row = db.execute("SELECT id FROM users WHERE email_normalized=?", (email.lower(),)).fetchone()
    password_hash = generate_password_hash(password)
    if row:
        user_id = int(row["id"])
        db.execute(
            """
            UPDATE users
            SET name=?, email=?, email_normalized=?, password_hash=?, role=?, active=1, updated_at=?
            WHERE id=?
            """,
            (name, email, email.lower(), password_hash, role, now, user_id),
        )
        return user_id

    return int(
        db.execute(
            """
            INSERT INTO users
            (name,email,email_normalized,password_hash,role,active,created_at,updated_at)
            VALUES (?,?,?,?,?,1,?,?)
            """,
            (name, email, email.lower(), password_hash, role, now, now),
        ).lastrowid
    )


def seed_edgecare_demo_data(*, password: str | None = None) -> dict[str, object]:
    """Create/update clearly synthetic local demo users, provider and schedules.

    The function is idempotent for the two fixed ``@zendoc.local`` identities.
    It is intentionally unavailable in production.
    """

    environment = (_normalized_env("ZENDOC_ENV") or "development").lower()
    if environment == "production":
        raise RuntimeError("EdgeCare synthetic demo data is disabled in production.")

    password = password or _normalized_env("ZENDOC_DEMO_PASSWORD")
    if len(password) < 12:
        raise ValueError("Set ZENDOC_DEMO_PASSWORD to a local-only password of at least 12 characters.")

    app = create_app()
    with app.app_context():
        db = get_db()
        doctor_id = _upsert_demo_user(
            db,
            email=DEMO_DOCTOR_EMAIL,
            name=DEMO_DOCTOR_NAME,
            role="doctor",
            password=password,
        )
        patient_id = _upsert_demo_user(
            db,
            email=DEMO_PATIENT_EMAIL,
            name=DEMO_PATIENT_NAME,
            role="patient",
            password=password,
        )

        now = now_iso()
        profile = db.execute("SELECT id FROM provider_profiles WHERE user_id=?", (doctor_id,)).fetchone()
        if profile:
            profile_id = int(profile["id"])
            db.execute(
                """
                UPDATE provider_profiles
                SET provider_type='doctor', specialty='Cardiology',
                    qualifications='Synthetic competition fixture — not a real clinician or healthcare provider.',
                    license_identifier=?, organization=?, address='Demo Road', city='Kalyani',
                    state='West Bengal', postal_code='741235', public_phone='',
                    verification_status='verified', updated_at=?
                WHERE id=?
                """,
                (DEMO_LICENSE, DEMO_ORGANIZATION, now, profile_id),
            )
        else:
            profile_id = int(
                db.execute(
                    """
                    INSERT INTO provider_profiles
                    (user_id,provider_type,specialty,qualifications,license_identifier,organization,address,
                     city,state,postal_code,public_phone,verification_status,created_at,updated_at)
                    VALUES (?,'doctor','Cardiology',?,?,?,?,?,?,?,'','verified',?,?)
                    """,
                    (
                        doctor_id,
                        "Synthetic competition fixture — not a real clinician or healthcare provider.",
                        DEMO_LICENSE,
                        DEMO_ORGANIZATION,
                        "Demo Road",
                        "Kalyani",
                        "West Bengal",
                        "741235",
                        now,
                        now,
                    ),
                ).lastrowid
            )

        # Keep the synthetic fixture deterministic and available every day.
        db.execute("DELETE FROM provider_schedules WHERE provider_profile_id=?", (profile_id,))
        for weekday in range(7):
            db.execute(
                """
                INSERT INTO provider_schedules
                (provider_profile_id,weekday,start_time,end_time,slot_minutes,active,
                 organization_id,organization_location_id,created_at,updated_at)
                VALUES (?,?,?, ?,30,1,NULL,NULL,?,?)
                """,
                (profile_id, weekday, "09:00", "17:00", now, now),
            )

        db.commit()
        return {
            "doctor_email": DEMO_DOCTOR_EMAIL,
            "patient_email": DEMO_PATIENT_EMAIL,
            "provider_profile_id": profile_id,
            "doctor_user_id": doctor_id,
            "patient_user_id": patient_id,
            "synthetic_demo_only": True,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }


def main() -> None:
    result = seed_edgecare_demo_data()
    print("EdgeCare synthetic demo fixture is ready.")
    print("These records are DEMO ONLY and must not be presented as real providers or patients.")
    print(f"Patient login: {result['patient_email']}")
    print(f"Provider login: {result['doctor_email']}")
    print("Use the local-only password supplied through ZENDOC_DEMO_PASSWORD.")
    print("Search demo location: Kalyani")


if __name__ == "__main__":  # pragma: no cover
    main()
