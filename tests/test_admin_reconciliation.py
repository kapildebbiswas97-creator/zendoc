import sqlite3

import pytest

from zendoc import create_app
from zendoc.agent_core import respond_with_core_agent
from zendoc.config import ConfigError
from zendoc.db import LEGACY_ADMIN_RECONCILIATION_VERSION, get_db, now_iso

from tests.test_milestone7 import api_token, headers


OWNER_EMAIL = "owner@example.com"
OWNER_PASSWORD = "OwnerFixture123"
LEGACY_PASSWORD_HASH = "legacy-password-hash-must-not-change"


def app_config(tmp_path, db_path, owner_email=OWNER_EMAIL, owner_password=OWNER_PASSWORD):
    return {
        "TESTING": True,
        "DATABASE": str(db_path),
        "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        "SECRET_KEY": "test-secret",
        "ADMIN_EMAIL": owner_email,
        "ADMIN_PASSWORD": owner_password,
        "RATE_LIMIT_PER_MINUTE": 1000,
    }


def fresh_owner_app(tmp_path, owner_email=OWNER_EMAIL):
    db_path = tmp_path / "legacy-admin.db"
    app = create_app(app_config(tmp_path, db_path, owner_email=owner_email))
    return app, db_path


def add_legacy_admin(app, email, name="Legacy Admin", provider_role=None, normalized=True):
    with app.app_context():
        db = get_db()
        db.execute("DROP INDEX IF EXISTS idx_users_single_admin")
        now = now_iso()
        cursor = db.execute(
            """
            INSERT INTO users
            (name,email,email_normalized,password_hash,role,verified,active,created_at,updated_at)
            VALUES (?,?,?,?, 'admin',1,1,?,?)
            """,
            (name, email, email.strip().lower() if normalized else None, LEGACY_PASSWORD_HASH, now, now),
        )
        user_id = cursor.lastrowid
        if provider_role:
            db.execute(
                """
                INSERT INTO provider_profiles
                (user_id,provider_type,verification_status,created_at,updated_at)
                VALUES (?,?, 'verified',?,?)
                """,
                (user_id, provider_role, now, now),
            )
        db.commit()
        return user_id


def roles_by_email(db_path):
    with sqlite3.connect(db_path) as db:
        return dict(db.execute("SELECT email, role FROM users ORDER BY id").fetchall())


def test_a_fresh_db_with_configured_owner_has_exactly_one_admin(tmp_path):
    app, _db_path = fresh_owner_app(tmp_path, owner_email="  OWNER@Example.com  ")
    with app.app_context():
        admins = get_db().execute(
            "SELECT email,email_normalized FROM users WHERE role='admin'"
        ).fetchall()
        assert len(admins) == 1
        assert admins[0]["email"] == OWNER_EMAIL
        assert admins[0]["email_normalized"] == OWNER_EMAIL


def test_b_two_legacy_admins_reconcile_to_configured_owner_without_deleting_accounts(tmp_path):
    app, db_path = fresh_owner_app(tmp_path)
    legacy_id = add_legacy_admin(app, "legacy-second@example.com")

    restarted = create_app(app_config(tmp_path, db_path, owner_email="  OWNER@EXAMPLE.COM "))
    with restarted.app_context():
        db = get_db()
        admins = db.execute("SELECT id,email FROM users WHERE role='admin'").fetchall()
        legacy = db.execute(
            "SELECT role,password_hash FROM users WHERE id=?", (legacy_id,)
        ).fetchone()
        assert len(admins) == 1
        assert admins[0]["email"] == OWNER_EMAIL
        assert legacy["role"] == "patient"
        assert legacy["password_hash"] == LEGACY_PASSWORD_HASH
        assert db.execute("SELECT COUNT(*) c FROM users WHERE id=?", (legacy_id,)).fetchone()["c"] == 1


def test_c_three_legacy_admins_keep_only_owner_and_restore_reliable_provider_role(tmp_path):
    app, db_path = fresh_owner_app(tmp_path)
    doctor_id = add_legacy_admin(app, "legacy-doctor@example.com", provider_role="doctor")
    fallback_id = add_legacy_admin(app, "legacy-fallback@example.com")

    restarted = create_app(app_config(tmp_path, db_path))
    with restarted.app_context():
        db = get_db()
        admins = db.execute("SELECT email FROM users WHERE role='admin'").fetchall()
        assert [row["email"] for row in admins] == [OWNER_EMAIL]
        assert db.execute("SELECT role FROM users WHERE id=?", (doctor_id,)).fetchone()["role"] == "doctor"
        assert db.execute("SELECT role FROM users WHERE id=?", (fallback_id,)).fetchone()["role"] == "patient"


def test_d_multiple_admins_fail_closed_when_configured_owner_matches_none(tmp_path):
    app, db_path = fresh_owner_app(tmp_path)
    add_legacy_admin(app, "legacy-second@example.com")

    with pytest.raises(ConfigError, match="does not match any legacy Admin account"):
        create_app(app_config(tmp_path, db_path, owner_email="not-an-admin@example.com"))

    assert roles_by_email(db_path)[OWNER_EMAIL] == "admin"
    assert roles_by_email(db_path)["legacy-second@example.com"] == "admin"


def test_e_multiple_admins_fail_closed_when_owner_email_is_missing(tmp_path):
    app, db_path = fresh_owner_app(tmp_path)
    add_legacy_admin(app, "legacy-second@example.com")

    with pytest.raises(ConfigError, match="ZENDOC_ADMIN_EMAIL is required"):
        create_app(app_config(tmp_path, db_path, owner_email=None, owner_password=None))

    assert list(roles_by_email(db_path).values()).count("admin") == 2


def test_f_duplicate_normalized_owner_identity_fails_closed_without_merging(tmp_path):
    app, db_path = fresh_owner_app(tmp_path)
    duplicate_id = add_legacy_admin(
        app,
        " OWNER@EXAMPLE.COM ",
        name="Duplicate Owner Identity",
        normalized=False,
    )

    with pytest.raises(ConfigError, match="owner identity is ambiguous"):
        create_app(app_config(tmp_path, db_path))

    with sqlite3.connect(db_path) as db:
        rows = db.execute(
            "SELECT id,role FROM users WHERE LOWER(TRIM(email))=? ORDER BY id", (OWNER_EMAIL,)
        ).fetchall()
        assert len(rows) == 2
        assert duplicate_id in {row[0] for row in rows}
        assert {row[1] for row in rows} == {"admin"}


def test_g_legacy_admin_reconciliation_is_idempotent(tmp_path):
    app, db_path = fresh_owner_app(tmp_path)
    legacy_id = add_legacy_admin(app, "legacy-second@example.com")
    first_restart = create_app(app_config(tmp_path, db_path))
    with first_restart.app_context():
        db = get_db()
        first_audit_count = db.execute(
            "SELECT COUNT(*) c FROM audit_logs WHERE action LIKE 'security.legacy_admin_demoted.%'"
        ).fetchone()["c"]
        first_roles = [tuple(row) for row in db.execute("SELECT id,role FROM users ORDER BY id")]

    second_restart = create_app(app_config(tmp_path, db_path))
    with second_restart.app_context():
        db = get_db()
        assert [tuple(row) for row in db.execute("SELECT id,role FROM users ORDER BY id")] == first_roles
        assert db.execute(
            "SELECT COUNT(*) c FROM audit_logs WHERE action LIKE 'security.legacy_admin_demoted.%'"
        ).fetchone()["c"] == first_audit_count == 1
        assert db.execute(
            "SELECT COUNT(*) c FROM schema_migrations WHERE version=?",
            (LEGACY_ADMIN_RECONCILIATION_VERSION,),
        ).fetchone()["c"] == 1
        assert db.execute("SELECT role FROM users WHERE id=?", (legacy_id,)).fetchone()["role"] == "patient"


def test_h_demoted_account_retains_associated_data(tmp_path):
    app, db_path = fresh_owner_app(tmp_path)
    legacy_id = add_legacy_admin(app, "legacy-with-data@example.com")
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO health_metrics (user_id,metric_type,metric_value,unit,recorded_at,source)
            VALUES (?, 'weight','72','kg',?, 'legacy_manual')
            """,
            (legacy_id, now_iso()),
        )
        db.commit()

    restarted = create_app(app_config(tmp_path, db_path))
    with restarted.app_context():
        db = get_db()
        assert db.execute("SELECT role FROM users WHERE id=?", (legacy_id,)).fetchone()["role"] == "patient"
        metric = db.execute(
            "SELECT metric_value,unit FROM health_metrics WHERE user_id=?", (legacy_id,)
        ).fetchone()
        assert dict(metric) == {"metric_value": "72", "unit": "kg"}


def test_i_security_audit_records_each_correction_without_secrets(tmp_path):
    app, db_path = fresh_owner_app(tmp_path)
    first_id = add_legacy_admin(app, "legacy-first@example.com")
    second_id = add_legacy_admin(app, "legacy-second@example.com", provider_role="pharmacy")

    restarted = create_app(app_config(tmp_path, db_path))
    with restarted.app_context():
        events = get_db().execute(
            """
            SELECT actor_id,action,entity_type,entity_id
            FROM audit_logs WHERE action LIKE 'security.legacy_admin_demoted.%'
            ORDER BY entity_id
            """
        ).fetchall()
        assert {row["entity_id"] for row in events} == {str(first_id), str(second_id)}
        assert {row["entity_type"] for row in events} == {"user"}
        actions = " ".join(row["action"] for row in events).lower()
        assert "admin_to_patient.fallback_no_reliable_role_metadata" in actions
        assert "admin_to_pharmacy.restored_provider_profile_role" in actions
        for forbidden in ("password", "hash", OWNER_PASSWORD.lower(), "@"):
            assert forbidden not in actions


def test_j_public_registration_still_rejects_admin(tmp_path):
    app, _db_path = fresh_owner_app(tmp_path)
    client = app.test_client()
    response = client.post(
        "/api/v1/auth/register",
        json={"name": "Attacker", "email": "attacker@example.com", "password": "StrongPass123", "role": "admin"},
    )
    assert response.status_code == 403
    with app.app_context():
        assert get_db().execute(
            "SELECT COUNT(*) c FROM users WHERE email_normalized='attacker@example.com'"
        ).fetchone()["c"] == 0


def test_k_profile_api_cannot_promote_account_and_unique_index_blocks_second_admin(tmp_path):
    app, _db_path = fresh_owner_app(tmp_path)
    client = app.test_client()
    doctor_token = api_token(client, "profile-doctor@example.com", role="doctor")
    response = client.post(
        "/api/v1/provider/profile",
        json={"role": "admin", "specialty": "Cardiology", "organization": "Test Clinic"},
        headers=headers(doctor_token),
    )
    assert response.status_code == 200
    with app.app_context():
        db = get_db()
        doctor = db.execute(
            "SELECT id,role FROM users WHERE email_normalized='profile-doctor@example.com'"
        ).fetchone()
        assert doctor["role"] == "doctor"
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE users SET role='admin' WHERE id=?", (doctor["id"],))
        db.rollback()


def test_core_agent_cannot_treat_forged_admin_identity_as_owner(tmp_path):
    app, _db_path = fresh_owner_app(tmp_path)
    with app.app_context():
        forged_admin = {
            "id": 999999,
            "email": "forged-admin@example.com",
            "email_normalized": "forged-admin@example.com",
            "role": "admin",
            "active": 1,
        }
        with pytest.raises(PermissionError, match="ZENDOC owner"):
            respond_with_core_agent(forged_admin, "run alert check")
