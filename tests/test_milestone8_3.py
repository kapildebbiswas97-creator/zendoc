import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

from zendoc import create_app
from zendoc.config import ConfigError, resolve_database_config, validate_startup_config
from zendoc.db import MILESTONE83_MIGRATION_VERSION, get_db, now_iso, table_columns
from zendoc.infrastructure import database_status
from zendoc.postgres_backend import split_sql_script, translate_sql
from tests.test_milestone1 import csrf, login_web, register_web


PASSWORD = "StrongPass123"


def make_m83_app(tmp_path, db_path=None, **overrides):
    config = {
        "TESTING": True,
        "DATABASE": str(db_path or (tmp_path / "m83-test.db")),
        "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        "SECRET_KEY": "m83-test-secret",
        "ADMIN_EMAIL": "owner@example.com",
        "ADMIN_PASSWORD": "OwnerStrong123",
        "RATE_LIMIT_PER_MINUTE": 1000,
    }
    config.update(overrides)
    return create_app(config)


def register_api(client, email, role="patient", name="M83 User", password=PASSWORD):
    return client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": password, "role": role},
    )


def login_api(client, email, role="patient", password=PASSWORD):
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "role": role},
    )


def test_email_nfkc_case_whitespace_duplicate_and_safe_login_failures(tmp_path):
    app = make_m83_app(tmp_path)
    client = app.test_client()

    registered = register_api(client, "  Ｕser＠Ｅxample．com  ", name="Normalized User")
    assert registered.status_code == 201
    duplicate = register_api(client, "user@example.com", name="Duplicate")
    assert duplicate.status_code == 409
    assert duplicate.json["error"]["message"] == "An account with this email already exists. Please log in."

    wrong = login_api(client, " USER@EXAMPLE.COM ", password="wrong-password")
    missing = login_api(client, "missing@example.com")
    injection = login_api(client, "x'OR'1'='1@example.com")
    for response in (wrong, missing, injection):
        assert response.status_code == 401
        assert response.json["error"] == "Email or password is incorrect."

    with app.app_context():
        rows = get_db().execute(
            "SELECT email,email_normalized,password_hash FROM users WHERE email_normalized=?",
            ("user@example.com",),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["email"] == "user@example.com"
        assert rows[0]["password_hash"] != PASSWORD
        assert PASSWORD not in rows[0]["password_hash"]


def test_session_fixation_role_tampering_and_idle_expiry_return_to_login(tmp_path):
    app = make_m83_app(tmp_path, SESSION_IDLE_MINUTES=5)
    client = app.test_client()
    register_api(client, "session@example.com", name="Session User")

    page = client.get("/login/patient")
    form_token = csrf(page.data.decode())
    with client.session_transaction() as session_state:
        session_state["session_nonce"] = "attacker-controlled"
        old_csrf = session_state["csrf_token"]
    logged_in = client.post(
        "/login/patient",
        data={"csrf_token": form_token, "email": "session@example.com", "password": PASSWORD},
        follow_redirects=True,
    )
    assert logged_in.status_code == 200
    with client.session_transaction() as session_state:
        assert session_state["session_nonce"] != "attacker-controlled"
        assert session_state["csrf_token"] != old_csrf
        assert session_state["role"] == "patient"
        session_state["role"] = "admin"

    assert client.get("/admin").status_code == 403
    with client.session_transaction() as session_state:
        session_state["role"] = "patient"
        session_state["last_activity_at"] = "2020-01-01T00:00:00+00:00"

    expired = client.get("/dashboard", follow_redirects=True)
    assert expired.status_code == 200
    assert b"Your session expired. Please log in again." in expired.data
    assert b"Patient Login" in expired.data
    with client.session_transaction() as session_state:
        assert "user_id" not in session_state


def test_production_logout_is_post_only_and_csrf_protected(tmp_path):
    app = make_m83_app(tmp_path, ALLOW_LEGACY_GET_LOGOUT=False)
    client = app.test_client()
    register_api(client, "logout@example.com")
    login_web(client, "patient", "logout@example.com")

    assert client.get("/logout").status_code == 405
    assert client.get("/dashboard").status_code == 200
    assert client.post("/logout").status_code == 400
    with client.session_transaction() as session_state:
        form_token = session_state["csrf_token"]
    logged_out = client.post(
        "/logout", data={"csrf_token": form_token}, follow_redirects=True
    )
    assert logged_out.status_code == 200
    assert b"Logged out." in logged_out.data
    assert client.get("/dashboard", follow_redirects=False).status_code == 302


def test_reset_tokens_are_short_lived_and_cannot_authenticate_as_bearer_tokens(tmp_path):
    app = make_m83_app(tmp_path)
    client = app.test_client()
    register_api(client, "recovery@example.com")

    recovery = client.post("/api/v1/auth/forgot-password", json={"email": "recovery@example.com"})
    assert recovery.status_code == 200
    reset_token = recovery.json["reset_token"]
    assert client.get(
        "/api/v1/dashboard", headers={"Authorization": f"Bearer {reset_token}"}
    ).status_code == 401

    with app.app_context():
        get_db().execute(
            "UPDATE api_tokens SET expires_at=? WHERE token_type='password_reset'",
            ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds"),),
        )
        get_db().commit()
    expired = client.post(
        "/api/v1/auth/reset-password",
        json={"reset_token": reset_token, "password": "NewStrongPass123"},
    )
    assert expired.status_code == 400

    second = client.post("/api/v1/auth/forgot-password", json={"email": "recovery@example.com"})
    changed = client.post(
        "/api/v1/auth/reset-password",
        json={"reset_token": second.json["reset_token"], "password": "NewStrongPass123"},
    )
    assert changed.status_code == 200
    assert login_api(client, "recovery@example.com", password=PASSWORD).status_code == 401
    assert login_api(client, "recovery@example.com", password="NewStrongPass123").status_code == 200


def test_production_password_recovery_is_truthfully_integration_required(tmp_path):
    app = make_m83_app(tmp_path, PASSWORD_RECOVERY_MODE="integration_required")
    client = app.test_client()
    register_api(client, "known@example.com")
    known = client.post("/api/v1/auth/forgot-password", json={"email": "known@example.com"})
    unknown = client.post("/api/v1/auth/forgot-password", json={"email": "unknown@example.com"})
    assert known.status_code == unknown.status_code == 503
    assert known.json == unknown.json == {
        "message": "Password recovery delivery is not integrated.",
        "status": "integration_required",
    }


def test_restart_preserves_patient_provider_identity_profiles_and_records(tmp_path):
    database_path = tmp_path / "restart-persistence.db"
    app = make_m83_app(tmp_path, database_path)
    client = app.test_client()
    assert register_api(client, "patient@example.com", name="Persistent Patient").status_code == 201
    assert register_api(client, "doctor@example.com", role="doctor", name="Persistent Doctor").status_code == 201

    with app.app_context():
        db = get_db()
        patient_id = db.execute("SELECT id FROM users WHERE email_normalized='patient@example.com'").fetchone()["id"]
        doctor_id = db.execute("SELECT id FROM users WHERE email_normalized='doctor@example.com'").fetchone()["id"]
        now = now_iso()
        db.execute("UPDATE users SET city='Kolkata', phone='0000000000' WHERE id=?", (patient_id,))
        db.execute(
            "INSERT INTO health_metrics (user_id,metric_type,metric_value,unit,recorded_at,source,notes) VALUES (?, 'weight', '70', 'kg', ?, 'manual', 'restart marker')",
            (patient_id, now),
        )
        db.execute(
            "INSERT INTO notifications (user_id,title,message,created_at) VALUES (?, 'Private restart notice', 'Patient-only data', ?)",
            (patient_id, now),
        )
        profile_cursor = db.execute(
            """
            INSERT INTO provider_profiles
            (user_id,provider_type,specialty,organization,verification_status,created_at,updated_at)
            VALUES (?, 'doctor', 'Cardiology', 'Demo Clinic', 'verified', ?, ?)
            """,
            (doctor_id, now, now),
        )
        profile_id = profile_cursor.lastrowid
        db.execute(
            "INSERT INTO provider_schedules (provider_profile_id,weekday,start_time,end_time,slot_minutes,created_at,updated_at) VALUES (?,1,'09:00','12:00',30,?,?)",
            (profile_id, now, now),
        )
        db.execute(
            """
            INSERT INTO appointments
            (patient_id,provider_id,provider_profile_id,provider_name,specialty,scheduled_for,reason,status,created_at,updated_at)
            VALUES (?,?,?,?,?,'2026-09-15T10:00','Restart follow-up','confirmed',?,?)
            """,
            (patient_id, doctor_id, profile_id, "Persistent Doctor", "Cardiology", now, now),
        )
        conversation = db.execute(
            "INSERT INTO conversations (title,created_by,created_at,updated_at) VALUES ('Restart conversation',?,?,?)",
            (patient_id, now, now),
        ).lastrowid
        db.execute(
            "INSERT INTO conversation_participants (conversation_id,user_id,role,joined_at) VALUES (?,?, 'patient', ?)",
            (conversation, patient_id, now),
        )
        db.execute(
            "INSERT INTO conversation_participants (conversation_id,user_id,role,joined_at) VALUES (?,?, 'doctor', ?)",
            (conversation, doctor_id, now),
        )
        db.execute(
            "INSERT INTO messages (conversation_id,sender_id,body,created_at) VALUES (?,?, 'Persistent message', ?)",
            (conversation, patient_id, now),
        )
        db.commit()

    restarted = make_m83_app(tmp_path, database_path, UPLOAD_FOLDER=str(tmp_path / "uploads-restarted"))
    restarted_client = restarted.test_client()
    patient_login = login_web(restarted_client, "patient", " PATIENT@EXAMPLE.COM ")
    assert b"Welcome, Persistent Patient" in patient_login.data
    assert b"Private restart notice" in restarted_client.get("/notifications").data

    with restarted.app_context():
        db = get_db()
        patient = db.execute("SELECT * FROM users WHERE email_normalized='patient@example.com'").fetchone()
        doctor = db.execute("SELECT * FROM users WHERE email_normalized='doctor@example.com'").fetchone()
        assert patient["id"] == patient_id and patient["role"] == "patient" and patient["city"] == "Kolkata"
        assert doctor["id"] == doctor_id and doctor["role"] == "doctor"
        assert db.execute("SELECT COUNT(*) c FROM health_metrics WHERE user_id=?", (patient_id,)).fetchone()["c"] == 1
        assert db.execute("SELECT COUNT(*) c FROM appointments WHERE patient_id=? AND provider_id=?", (patient_id, doctor_id)).fetchone()["c"] == 1
        assert db.execute("SELECT COUNT(*) c FROM provider_schedules WHERE provider_profile_id=?", (profile_id,)).fetchone()["c"] == 1
        assert db.execute("SELECT COUNT(*) c FROM messages WHERE conversation_id=?", (conversation,)).fetchone()["c"] == 1

    restarted_client.get("/logout")
    doctor_login = login_web(restarted_client, "doctor", "doctor@example.com")
    assert b"Welcome, Persistent Doctor" in doctor_login.data
    assert b"Private restart notice" not in restarted_client.get("/notifications").data
    duplicate = register_api(restarted_client, "patient@example.com")
    assert duplicate.status_code == 409
    with restarted.app_context():
        assert get_db().execute("SELECT COUNT(*) c FROM users WHERE email_normalized='patient@example.com'").fetchone()["c"] == 1


def test_legacy_m82_database_migrates_additively_without_losing_accounts(tmp_path):
    database_path = tmp_path / "legacy-m82.db"
    app = make_m83_app(tmp_path, database_path)
    client = app.test_client()
    register_api(client, "legacy@example.com", name="Legacy Patient")
    with app.app_context():
        user_id = get_db().execute("SELECT id FROM users WHERE email_normalized='legacy@example.com'").fetchone()["id"]
        get_db().execute(
            "INSERT INTO health_metrics (user_id,metric_type,metric_value,recorded_at) VALUES (?,'heart_rate','72',?)",
            (user_id, now_iso()),
        )
        get_db().commit()

    with sqlite3.connect(database_path) as raw:
        raw.executescript(
            """
            DROP TABLE api_tokens;
            CREATE TABLE api_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token TEXT,
                token_hash TEXT UNIQUE,
                revoked_at TEXT,
                created_at TEXT NOT NULL
            );
            DELETE FROM schema_migrations WHERE version='m8_3_auth_persistence_v1';
            """
        )

    migrated = make_m83_app(tmp_path, database_path, UPLOAD_FOLDER=str(tmp_path / "legacy-uploads"))
    migrated_client = migrated.test_client()
    assert b"Welcome, Legacy Patient" in login_web(migrated_client, "patient", "legacy@example.com").data
    with migrated.app_context():
        db = get_db()
        assert {"token_type", "expires_at"}.issubset(table_columns(db, "api_tokens"))
        assert db.execute("SELECT id FROM users WHERE email_normalized='legacy@example.com'").fetchone()["id"] == user_id
        assert db.execute("SELECT COUNT(*) c FROM health_metrics WHERE user_id=?", (user_id,)).fetchone()["c"] == 1
        assert db.execute("SELECT COUNT(*) c FROM schema_migrations WHERE version=?", (MILESTONE83_MIGRATION_VERSION,)).fetchone()["c"] == 1


def test_admin_remains_owner_only_across_registration_profile_tampering_and_restart(tmp_path):
    database_path = tmp_path / "owner-invariant.db"
    app = make_m83_app(tmp_path, database_path)
    client = app.test_client()
    assert client.get("/register/admin").status_code == 403
    assert register_api(client, "attacker@example.com", role="admin").status_code == 403
    register_api(client, "patient-role@example.com")
    login_web(client, "patient", "patient-role@example.com")
    page = client.get("/profile")
    response = client.post(
        "/profile",
        data={
            "csrf_token": csrf(page.data.decode()),
            "name": "Still Patient",
            "role": "admin",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        owner_id = get_db().execute("SELECT id FROM users WHERE role='admin'").fetchone()["id"]
        assert get_db().execute("SELECT role FROM users WHERE email_normalized='patient-role@example.com'").fetchone()["role"] == "patient"
        assert get_db().execute("SELECT COUNT(*) c FROM users WHERE role='admin'").fetchone()["c"] == 1

    restarted = make_m83_app(tmp_path, database_path)
    with restarted.app_context():
        owner = get_db().execute("SELECT id,email_normalized FROM users WHERE role='admin'").fetchone()
        assert owner["id"] == owner_id
        assert owner["email_normalized"] == "owner@example.com"


def test_database_configuration_matrix_and_test_database_isolation(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ZENDOC_DATABASE_PATH", raising=False)
    development = resolve_database_config(tmp_path, "development")
    assert development["DATABASE_ENGINE"] == "sqlite"
    assert development["DATABASE_DURABILITY"] == "local_development"

    isolated_path = tmp_path / "isolated.db"
    testing = resolve_database_config(tmp_path, "production", True, {"DATABASE": str(isolated_path)})
    assert testing["DATABASE_ENGINE"] == "sqlite"
    assert testing["DATABASE"] == str(isolated_path)
    assert testing["DATABASE_DURABILITY"] == "isolated_testing"

    unsafe = resolve_database_config(tmp_path, "production")
    assert unsafe["DATABASE_DURABILITY"] == "integration_required"
    managed = resolve_database_config(
        tmp_path,
        "production",
        overrides={"DATABASE_URL": "postgresql://db.invalid/zendoc"},
    )
    assert managed["DATABASE_ENGINE"] == "postgresql"
    assert managed["DATABASE_DURABILITY"] == "durable_configured"
    mounted = resolve_database_config(
        tmp_path,
        "production",
        overrides={"DATABASE": str(tmp_path / "mounted" / "zendoc.db"), "PERSISTENCE_MODE": "durable"},
    )
    assert mounted["DATABASE_ENGINE"] == "sqlite"
    assert mounted["DATABASE_DURABILITY"] == "durable_configured"

    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://db.invalid/production"
    )
    test_app = make_m83_app(tmp_path, tmp_path / "must-stay-local.db")
    assert test_app.config["DATABASE_ENGINE"] == "sqlite"
    assert test_app.config["DATABASE"] == str(tmp_path / "must-stay-local.db")


def test_strict_production_persistence_can_fail_closed():
    app = Flask("persistence-validation")
    app.config.update(
        TESTING=False,
        ZENDOC_ENV="production",
        SECRET_KEY="configured-secret",
        ADMIN_EMAIL="owner@example.com",
        ADMIN_PASSWORD="configured-password",
        DATABASE_DURABILITY="integration_required",
        REQUIRE_DURABLE_DATABASE=True,
    )
    with pytest.raises(ConfigError, match="Production persistence is not durable"):
        validate_startup_config(app)


def test_owner_persistence_visibility_never_exposes_database_credentials(tmp_path):
    app = make_m83_app(tmp_path)
    with app.app_context():
        app.config.update(
            ZENDOC_ENV="production",
            DATABASE_ENGINE="postgresql",
            DATABASE_DURABILITY="durable_configured",
            DATABASE_URL="postgresql://private.invalid/zendoc?application_name=sensitive_marker",
            PERSISTENCE_VERIFIED=False,
        )
        status = database_status()
    serialized = repr(status)
    assert status["engine"] == "PostgreSQL"
    assert status["persistence"] == "integration_required"
    assert status["status"] == "beta"
    for secret in ("sensitive_marker", "private.invalid", "postgresql://"):
        assert secret not in serialized


def test_postgresql_adapter_translation_is_parameterized_and_migration_ready():
    query, returns_id = translate_sql(
        "INSERT INTO messages (conversation_id,sender_id,body,created_at) VALUES (?,?,?,?)"
    )
    assert query.count("%s") == 4
    assert query.endswith("RETURNING id")
    assert returns_id is True

    ai_conv_query, ai_conv_returns_id = translate_sql(
        "INSERT INTO ai_conversations (user_id, title, last_intent, created_at, updated_at) VALUES (?,?,?,?,?)"
    )
    assert ai_conv_query.endswith("RETURNING id")
    assert ai_conv_returns_id is True

    ignored, _ = translate_sql(
        "INSERT OR IGNORE INTO schema_migrations (version,applied_at) VALUES (?,?)"
    )
    assert "INSERT OR IGNORE" not in ignored
    assert "ON CONFLICT DO NOTHING" in ignored

    ddl, _ = translate_sql(
        "CREATE TABLE sample (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id))"
    )
    assert "BIGSERIAL PRIMARY KEY" in ddl
    assert "user_id BIGINT NOT NULL REFERENCES" in ddl

    # Test datetime('now') and variants translation to PostgreSQL CURRENT_TIMESTAMP
    exercise_ddl, _ = translate_sql(
        "CREATE TABLE exercises (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    assert "BIGSERIAL PRIMARY KEY" in exercise_ddl
    assert "datetime('now')" not in exercise_ddl
    assert "DEFAULT (CURRENT_TIMESTAMP)" in exercise_ddl

    datetime_interval_sql, _ = translate_sql(
        "SELECT * FROM logs WHERE created_at < datetime('now', '-6 hours')"
    )
    assert "datetime(" not in datetime_interval_sql
    assert "(CURRENT_TIMESTAMP + INTERVAL '-6 hours')" in datetime_interval_sql

    # Test all foreign key constraint combinations are translated to BIGINT
    fk_unique_ddl, _ = translate_sql(
        "CREATE TABLE consultation_rooms (consultation_id INTEGER NOT NULL UNIQUE REFERENCES consultation_requests(id))"
    )
    assert "consultation_id BIGINT NOT NULL UNIQUE REFERENCES" in fk_unique_ddl

    fk_pk_ddl, _ = translate_sql(
        "CREATE TABLE patient_health_profiles (patient_id INTEGER PRIMARY KEY REFERENCES users(id))"
    )
    assert "patient_id BIGINT PRIMARY KEY REFERENCES" in fk_pk_ddl

    assert split_sql_script("CREATE TABLE one (id TEXT); CREATE TABLE two (note TEXT DEFAULT ';');") == [
        "CREATE TABLE one (id TEXT)",
        "CREATE TABLE two (note TEXT DEFAULT ';')",
    ]


def test_fresh_postgresql_schema_ordering_has_no_forward_references():
    import re
    from zendoc.postgres_backend import split_sql_script, translate_sql

    # Read the init_db DDL from db.py
    import zendoc.db as zdb
    import inspect
    init_src = inspect.getsource(zdb.init_db)
    m = re.search(r'db\.executescript\(\s*"""(.*?)"""\s*\)', init_src, re.DOTALL)
    assert m is not None, "Could not find init_db executescript DDL"
    init_sql = m.group(1)

    statements = split_sql_script(init_sql)
    created_tables = set()
    table_order = []

    for idx, stmt in enumerate(statements):
        t_stmt, _ = translate_sql(stmt)

        # Verify CREATE TABLE statements
        create_match = re.search(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_]+)\s*\((.*)\)",
            t_stmt,
            re.DOTALL | re.IGNORECASE,
        )
        if create_match:
            table_name = create_match.group(1).lower()
            table_order.append(table_name)
            body = create_match.group(2)

            # All referenced foreign key tables must already exist in created_tables
            fks = re.findall(r"REFERENCES\s+([A-Za-z0-9_]+)\s*\(", body, re.IGNORECASE)
            for fk in fks:
                fk_table = fk.lower()
                assert fk_table == table_name or fk_table in created_tables, (
                    f"PostgreSQL forward reference error at statement {idx+1}: "
                    f"table '{table_name}' references '{fk_table}' before '{fk_table}' is created."
                )

            created_tables.add(table_name)
            continue

        # Verify CREATE INDEX statements
        idx_match = re.search(
            r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_]+)\s+ON\s+([A-Za-z0-9_]+)",
            t_stmt,
            re.IGNORECASE,
        )
        if idx_match:
            idx_name = idx_match.group(1)
            on_table = idx_match.group(2).lower()
            assert on_table in created_tables, (
                f"PostgreSQL index error at statement {idx+1}: "
                f"index '{idx_name}' created on '{on_table}' before '{on_table}' is created."
            )

    # Specific assertion for agent_tasks before agent_approvals
    assert "agent_tasks" in table_order
    assert "agent_approvals" in table_order
    assert table_order.index("agent_tasks") < table_order.index("agent_approvals"), (
        "agent_tasks must be created before agent_approvals"
    )



def test_patient_and_provider_demo_routes_smoke_without_ai_providers(tmp_path):
    app = make_m83_app(
        tmp_path,
        LOCAL_AI_ENABLED=False,
        AI_PROVIDER="",
        AI_API_KEY="",
    )
    client = app.test_client()
    register_api(client, "demo-patient@example.com", name="Demo Patient")
    register_api(client, "demo-doctor@example.com", role="doctor", name="Demo Doctor")

    login_web(client, "patient", "demo-patient@example.com")
    patient_routes = (
        "/dashboard",
        "/ai",
        "/finder",
        "/appointments",
        "/health",
        "/timeline",
        "/fitness",
        "/messages",
        "/notifications",
        "/profile",
    )
    assert {path: client.get(path).status_code for path in patient_routes} == {
        path: 200 for path in patient_routes
    }

    client.get("/logout")
    login_web(client, "doctor", "demo-doctor@example.com")
    provider_routes = (
        "/dashboard",
        "/provider/profile",
        "/doctor/availability",
        "/messages",
        "/appointments",
        "/notifications",
    )
    assert {path: client.get(path).status_code for path in provider_routes} == {
        path: 200 for path in provider_routes
    }
