import sqlite3
from datetime import datetime, timezone

from flask import current_app, g
from werkzeug.security import generate_password_hash


ROLES = ("patient", "doctor", "hospital", "pharmacy", "government", "admin")


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('patient','doctor','hospital','pharmacy','government','admin')),
            phone TEXT,
            age INTEGER,
            gender TEXT,
            city TEXT,
            emergency_contact TEXT,
            verified INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
        CREATE INDEX IF NOT EXISTS idx_users_active ON users(active);

        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            provider_profile_id INTEGER,
            provider_name TEXT NOT NULL,
            specialty TEXT,
            scheduled_for TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'requested',
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_appointments_patient ON appointments(patient_id);
        CREATE INDEX IF NOT EXISTS idx_appointments_provider ON appointments(provider_id);
        CREATE INDEX IF NOT EXISTS idx_appointments_status ON appointments(status);

        CREATE TABLE IF NOT EXISTS provider_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            provider_type TEXT NOT NULL,
            specialty TEXT,
            qualifications TEXT,
            license_identifier TEXT,
            organization TEXT,
            address TEXT,
            city TEXT,
            state TEXT,
            postal_code TEXT,
            latitude REAL,
            longitude REAL,
            public_phone TEXT,
            verification_status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_provider_profiles_type ON provider_profiles(provider_type);
        CREATE INDEX IF NOT EXISTS idx_provider_profiles_specialty ON provider_profiles(specialty);
        CREATE INDEX IF NOT EXISTS idx_provider_profiles_verification ON provider_profiles(verification_status);

        CREATE TABLE IF NOT EXISTS provider_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_profile_id INTEGER NOT NULL REFERENCES provider_profiles(id) ON DELETE CASCADE,
            weekday INTEGER NOT NULL CHECK(weekday BETWEEN 0 AND 6),
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            slot_minutes INTEGER NOT NULL DEFAULT 30,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_provider_schedules_profile ON provider_schedules(provider_profile_id, weekday);

        CREATE TABLE IF NOT EXISTS medical_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            uploaded_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL UNIQUE,
            mime_type TEXT,
            file_size INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_records_owner ON medical_records(owner_id);

        CREATE TABLE IF NOT EXISTS health_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            metric_type TEXT NOT NULL,
            metric_value TEXT NOT NULL,
            unit TEXT,
            recorded_at TEXT NOT NULL,
            numeric_value REAL,
            secondary_value REAL,
            source TEXT NOT NULL DEFAULT 'manual',
            notes TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_metrics_user ON health_metrics(user_id);
        CREATE INDEX IF NOT EXISTS idx_metrics_user_type_date ON health_metrics(user_id, metric_type, recorded_at);

        CREATE TABLE IF NOT EXISTS patient_health_profiles (
            patient_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            date_of_birth TEXT,
            sex_at_birth TEXT,
            blood_group TEXT,
            height_cm REAL,
            baseline_weight_kg REAL,
            allergies TEXT NOT NULL DEFAULT '[]',
            current_medications TEXT NOT NULL DEFAULT '[]',
            chronic_conditions TEXT NOT NULL DEFAULT '[]',
            previous_conditions TEXT NOT NULL DEFAULT '[]',
            surgeries TEXT NOT NULL DEFAULT '[]',
            vaccinations TEXT NOT NULL DEFAULT '[]',
            health_goals TEXT NOT NULL DEFAULT '[]',
            lifestyle_notes TEXT,
            emergency_contact_name TEXT,
            emergency_contact_phone TEXT,
            emergency_contact_relationship TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS report_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL UNIQUE REFERENCES medical_records(id) ON DELETE CASCADE,
            report_uid TEXT NOT NULL UNIQUE,
            report_type TEXT NOT NULL,
            document_date TEXT,
            provider_name TEXT,
            lab_name TEXT,
            description TEXT,
            extraction_status TEXT NOT NULL DEFAULT 'unavailable',
            extraction_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_report_metadata_type_date ON report_metadata(report_type, document_date);

        CREATE TABLE IF NOT EXISTS report_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL REFERENCES medical_records(id) ON DELETE CASCADE,
            test_name TEXT NOT NULL,
            value_text TEXT NOT NULL,
            numeric_value REAL,
            unit TEXT,
            reference_range TEXT,
            abnormal_flag TEXT NOT NULL DEFAULT 'unknown',
            measurement_date TEXT,
            source TEXT NOT NULL,
            created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_report_results_record ON report_results(record_id);
        CREATE INDEX IF NOT EXISTS idx_report_results_trend ON report_results(test_name, measurement_date);

        CREATE TABLE IF NOT EXISTS health_timeline_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,
            event_at TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT,
            provider_name TEXT,
            source TEXT NOT NULL,
            source_ref TEXT,
            created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_timeline_patient_date ON health_timeline_events(patient_id, event_at);
        CREATE INDEX IF NOT EXISTS idx_timeline_patient_type ON health_timeline_events(patient_id, event_type, event_at);

        CREATE TABLE IF NOT EXISTS health_access_grants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider_profile_id INTEGER REFERENCES provider_profiles(id) ON DELETE SET NULL,
            scopes TEXT NOT NULL,
            expires_at TEXT,
            revoked_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_health_grants_patient ON health_access_grants(patient_id, revoked_at);
        CREATE INDEX IF NOT EXISTS idx_health_grants_provider ON health_access_grants(provider_id, patient_id, revoked_at);

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            channel TEXT NOT NULL DEFAULT 'in_app',
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read);

        CREATE TABLE IF NOT EXISTS ai_interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            conversation_id INTEGER,
            feature TEXT NOT NULL,
            intent TEXT,
            input_text TEXT NOT NULL,
            output_text TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            model_version TEXT NOT NULL,
            provider TEXT,
            emergency INTEGER NOT NULL DEFAULT 0,
            success INTEGER NOT NULL DEFAULT 1,
            latency_ms INTEGER,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ai_user ON ai_interactions(user_id);

        CREATE TABLE IF NOT EXISTS ai_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT,
            last_intent TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ai_conversations_user ON ai_conversations(user_id, updated_at);

        CREATE TABLE IF NOT EXISTS api_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token TEXT,
            token_hash TEXT UNIQUE,
            revoked_at TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_logs(actor_id);

        CREATE TABLE IF NOT EXISTS fitness_profiles (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            fitness_goal TEXT,
            experience_level TEXT,
            preferred_workout_type TEXT,
            workout_location TEXT,
            equipment TEXT NOT NULL DEFAULT '[]',
            available_minutes INTEGER NOT NULL DEFAULT 45,
            preferred_days TEXT NOT NULL DEFAULT '[]',
            height_cm REAL,
            weight_kg REAL,
            limitations TEXT,
            target_weight_kg REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS exercises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            muscle_group TEXT NOT NULL,
            equipment TEXT NOT NULL DEFAULT 'bodyweight',
            difficulty TEXT NOT NULL DEFAULT 'beginner',
            instructions TEXT NOT NULL,
            common_mistakes TEXT,
            easier_variation TEXT,
            harder_variation TEXT,
            camera_ready INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_exercises_category ON exercises(category, difficulty);
        CREATE INDEX IF NOT EXISTS idx_exercises_equipment ON exercises(equipment);

        CREATE TABLE IF NOT EXISTS workout_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            goal TEXT NOT NULL,
            experience_level TEXT NOT NULL,
            workout_location TEXT,
            estimated_minutes INTEGER,
            plan_data TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_workout_plans_user ON workout_plans(user_id, created_at);

        CREATE TABLE IF NOT EXISTS workout_plan_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL REFERENCES workout_plans(id) ON DELETE CASCADE,
            exercise_id INTEGER NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
            day_number INTEGER NOT NULL DEFAULT 1,
            order_in_day INTEGER NOT NULL DEFAULT 1,
            sets INTEGER NOT NULL DEFAULT 3,
            reps TEXT NOT NULL DEFAULT '10',
            rest_seconds INTEGER NOT NULL DEFAULT 60,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_plan_items_plan ON workout_plan_items(plan_id, day_number);

        CREATE TABLE IF NOT EXISTS workout_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            plan_id INTEGER REFERENCES workout_plans(id) ON DELETE SET NULL,
            name TEXT NOT NULL DEFAULT 'Workout Session',
            status TEXT NOT NULL DEFAULT 'active',
            started_at TEXT NOT NULL,
            finished_at TEXT,
            duration_minutes INTEGER,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user_date ON workout_sessions(user_id, started_at);
        CREATE INDEX IF NOT EXISTS idx_sessions_status ON workout_sessions(user_id, status);

        CREATE TABLE IF NOT EXISTS workout_session_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES workout_sessions(id) ON DELETE CASCADE,
            exercise_id INTEGER NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
            planned_sets INTEGER,
            planned_reps TEXT,
            rest_seconds INTEGER,
            completed_sets INTEGER NOT NULL DEFAULT 0,
            form_notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_session_items_session ON workout_session_items(session_id);

        CREATE TABLE IF NOT EXISTS workout_set_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES workout_sessions(id) ON DELETE CASCADE,
            session_item_id INTEGER REFERENCES workout_session_items(id) ON DELETE CASCADE,
            exercise_id INTEGER NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
            set_number INTEGER NOT NULL DEFAULT 1,
            completed_reps INTEGER,
            duration_seconds INTEGER,
            notes TEXT,
            logged_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_set_logs_session ON workout_set_logs(session_id);

        CREATE TABLE IF NOT EXISTS nutrition_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            food_name TEXT NOT NULL,
            meal_type TEXT NOT NULL DEFAULT 'other',
            quantity_g REAL,
            calories_kcal REAL,
            protein_g REAL,
            carbs_g REAL,
            fat_g REAL,
            notes TEXT,
            logged_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_nutrition_user_date ON nutrition_logs(user_id, logged_at);

        CREATE TABLE IF NOT EXISTS hydration_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            ml REAL NOT NULL,
            logged_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_hydration_user_date ON hydration_logs(user_id, logged_at);
        """
    )
    migrate_schema(db)
    seed_admin()
    _seed_exercises_safe()
    current_app.teardown_appcontext(close_db)


def table_columns(db, table):
    rows = db.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def column_info(db, table):
    return {row["name"]: dict(row) for row in db.execute(f"PRAGMA table_info({table})").fetchall()}


def migrate_schema(db):
    token_info = column_info(db, "api_tokens")
    if token_info.get("token", {}).get("notnull"):
        db.executescript(
            """
            ALTER TABLE api_tokens RENAME TO api_tokens_legacy;
            CREATE TABLE api_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token TEXT,
                token_hash TEXT UNIQUE,
                revoked_at TEXT,
                created_at TEXT NOT NULL
            );
            INSERT INTO api_tokens (id, user_id, token, token_hash, revoked_at, created_at)
            SELECT id, user_id, token, NULL, NULL, created_at FROM api_tokens_legacy;
            DROP TABLE api_tokens_legacy;
            """
        )

    token_columns = table_columns(db, "api_tokens")
    if "token_hash" not in token_columns:
        db.execute("ALTER TABLE api_tokens ADD COLUMN token_hash TEXT")
    if "revoked_at" not in token_columns:
        db.execute("ALTER TABLE api_tokens ADD COLUMN revoked_at TEXT")

    user_columns = table_columns(db, "users")
    for column, ddl in {
        "gender": "ALTER TABLE users ADD COLUMN gender TEXT",
        "city": "ALTER TABLE users ADD COLUMN city TEXT",
        "emergency_contact": "ALTER TABLE users ADD COLUMN emergency_contact TEXT",
        "verified": "ALTER TABLE users ADD COLUMN verified INTEGER NOT NULL DEFAULT 0",
        "active": "ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1",
    }.items():
        if column not in user_columns:
            db.execute(ddl)
    db.execute("CREATE INDEX IF NOT EXISTS idx_tokens_hash ON api_tokens(token_hash)")

    ai_columns = table_columns(db, "ai_interactions")
    for column, ddl in {
        "conversation_id": "ALTER TABLE ai_interactions ADD COLUMN conversation_id INTEGER",
        "intent": "ALTER TABLE ai_interactions ADD COLUMN intent TEXT",
        "provider": "ALTER TABLE ai_interactions ADD COLUMN provider TEXT",
        "emergency": "ALTER TABLE ai_interactions ADD COLUMN emergency INTEGER NOT NULL DEFAULT 0",
        "success": "ALTER TABLE ai_interactions ADD COLUMN success INTEGER NOT NULL DEFAULT 1",
        "latency_ms": "ALTER TABLE ai_interactions ADD COLUMN latency_ms INTEGER",
    }.items():
        if column not in ai_columns:
            db.execute(ddl)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT,
            last_intent TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_ai_conversations_user ON ai_conversations(user_id, updated_at)")

    metric_columns = table_columns(db, "health_metrics")
    for column, ddl in {
        "numeric_value": "ALTER TABLE health_metrics ADD COLUMN numeric_value REAL",
        "secondary_value": "ALTER TABLE health_metrics ADD COLUMN secondary_value REAL",
        "source": "ALTER TABLE health_metrics ADD COLUMN source TEXT NOT NULL DEFAULT 'legacy_manual'",
        "notes": "ALTER TABLE health_metrics ADD COLUMN notes TEXT",
    }.items():
        if column not in metric_columns:
            db.execute(ddl)
    db.execute("CREATE INDEX IF NOT EXISTS idx_metrics_user_type_date ON health_metrics(user_id, metric_type, recorded_at)")

    appointment_columns = table_columns(db, "appointments")
    for column, ddl in {
        "provider_profile_id": "ALTER TABLE appointments ADD COLUMN provider_profile_id INTEGER",
        "specialty": "ALTER TABLE appointments ADD COLUMN specialty TEXT",
    }.items():
        if column not in appointment_columns:
            db.execute(ddl)
    db.execute("CREATE INDEX IF NOT EXISTS idx_appointments_profile ON appointments(provider_profile_id)")

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS provider_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            provider_type TEXT NOT NULL,
            specialty TEXT,
            qualifications TEXT,
            license_identifier TEXT,
            organization TEXT,
            address TEXT,
            city TEXT,
            state TEXT,
            postal_code TEXT,
            latitude REAL,
            longitude REAL,
            public_phone TEXT,
            verification_status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_provider_profiles_type ON provider_profiles(provider_type)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_provider_profiles_specialty ON provider_profiles(specialty)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_provider_profiles_verification ON provider_profiles(verification_status)")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS provider_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_profile_id INTEGER NOT NULL REFERENCES provider_profiles(id) ON DELETE CASCADE,
            weekday INTEGER NOT NULL CHECK(weekday BETWEEN 0 AND 6),
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            slot_minutes INTEGER NOT NULL DEFAULT 30,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_provider_schedules_profile ON provider_schedules(provider_profile_id, weekday)")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS patient_health_profiles (
            patient_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            date_of_birth TEXT,
            sex_at_birth TEXT,
            blood_group TEXT,
            height_cm REAL,
            baseline_weight_kg REAL,
            allergies TEXT NOT NULL DEFAULT '[]',
            current_medications TEXT NOT NULL DEFAULT '[]',
            chronic_conditions TEXT NOT NULL DEFAULT '[]',
            previous_conditions TEXT NOT NULL DEFAULT '[]',
            surgeries TEXT NOT NULL DEFAULT '[]',
            vaccinations TEXT NOT NULL DEFAULT '[]',
            health_goals TEXT NOT NULL DEFAULT '[]',
            lifestyle_notes TEXT,
            emergency_contact_name TEXT,
            emergency_contact_phone TEXT,
            emergency_contact_relationship TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS report_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL UNIQUE REFERENCES medical_records(id) ON DELETE CASCADE,
            report_uid TEXT NOT NULL UNIQUE,
            report_type TEXT NOT NULL,
            document_date TEXT,
            provider_name TEXT,
            lab_name TEXT,
            description TEXT,
            extraction_status TEXT NOT NULL DEFAULT 'unavailable',
            extraction_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_report_metadata_type_date ON report_metadata(report_type, document_date);
        CREATE TABLE IF NOT EXISTS report_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL REFERENCES medical_records(id) ON DELETE CASCADE,
            test_name TEXT NOT NULL,
            value_text TEXT NOT NULL,
            numeric_value REAL,
            unit TEXT,
            reference_range TEXT,
            abnormal_flag TEXT NOT NULL DEFAULT 'unknown',
            measurement_date TEXT,
            source TEXT NOT NULL,
            created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_report_results_record ON report_results(record_id);
        CREATE INDEX IF NOT EXISTS idx_report_results_trend ON report_results(test_name, measurement_date);
        CREATE TABLE IF NOT EXISTS health_timeline_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,
            event_at TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT,
            provider_name TEXT,
            source TEXT NOT NULL,
            source_ref TEXT,
            created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_timeline_patient_date ON health_timeline_events(patient_id, event_at);
        CREATE INDEX IF NOT EXISTS idx_timeline_patient_type ON health_timeline_events(patient_id, event_type, event_at);
        CREATE TABLE IF NOT EXISTS health_access_grants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider_profile_id INTEGER REFERENCES provider_profiles(id) ON DELETE SET NULL,
            scopes TEXT NOT NULL,
            expires_at TEXT,
            revoked_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_health_grants_patient ON health_access_grants(patient_id, revoked_at);
        CREATE INDEX IF NOT EXISTS idx_health_grants_provider ON health_access_grants(provider_id, patient_id, revoked_at);
        """
    )
    db.commit()


def seed_admin():
    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
    if existing:
        return
    admin_email = current_app.config.get("ADMIN_EMAIL")
    admin_password = current_app.config.get("ADMIN_PASSWORD")
    if not admin_email or not admin_password:
        return
    now = now_iso()
    db.execute(
        """
        INSERT INTO users (name, email, password_hash, role, verified, created_at, updated_at)
        VALUES (?, ?, ?, 'admin', 1, ?, ?)
        """,
        (
            "ZENDOC Admin",
            admin_email.strip().lower(),
            generate_password_hash(admin_password),
            now,
            now,
        ),
    )
    db.commit()


def _seed_exercises_safe():
    """Seed the exercise library.  Imported here to avoid circular imports."""
    try:
        from .exercise_library import seed_exercises
        seed_exercises()
    except Exception:
        pass  # Exercise seeding failure must not block app startup
