import json
import sqlite3
from datetime import datetime, timezone

from flask import current_app, g
from werkzeug.security import generate_password_hash


ROLES = ("patient", "doctor", "hospital", "pharmacy", "government", "admin")
LEGACY_ADMIN_FALLBACK_ROLE = "patient"
LEGACY_ADMIN_RECONCILIATION_VERSION = "m8_legacy_admin_reconciliation_v1"


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
            email_normalized TEXT UNIQUE,
            duplicate_of_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            duplicate_detected_at TEXT,
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

        CREATE TABLE IF NOT EXISTS duplicate_account_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_normalized TEXT NOT NULL,
            primary_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            duplicate_user_ids TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'needs_review',
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_duplicate_account_groups_email ON duplicate_account_groups(email_normalized);

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

        -- ── Milestone 6: Family Care, Home Health, Transport, IoT & Marketplace ──

        CREATE TABLE IF NOT EXISTS family_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            member_name TEXT NOT NULL,
            relationship TEXT NOT NULL,
            age INTEGER,
            gender TEXT,
            phone TEXT,
            city TEXT,
            is_remote_parent INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_family_members_user ON family_members(user_id);

        CREATE TABLE IF NOT EXISTS family_access_grants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grantor_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            grantee_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            family_member_id INTEGER REFERENCES family_members(id) ON DELETE CASCADE,
            scopes TEXT NOT NULL DEFAULT '["appointments","reports","metrics"]',
            revoked_at TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_family_grants_grantee ON family_access_grants(grantee_id, revoked_at);

        CREATE TABLE IF NOT EXISTS family_care_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            family_member_id INTEGER REFERENCES family_members(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            task_type TEXT NOT NULL DEFAULT 'general',
            due_date TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            notes TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_care_tasks_user ON family_care_tasks(user_id, status);

        CREATE TABLE IF NOT EXISTS saved_locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            label TEXT NOT NULL,
            address TEXT NOT NULL,
            city TEXT NOT NULL,
            state TEXT,
            country TEXT NOT NULL DEFAULT 'India',
            latitude REAL,
            longitude REAL,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_saved_locations_user ON saved_locations(user_id);

        CREATE TABLE IF NOT EXISTS health_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            device_name TEXT NOT NULL,
            device_type TEXT NOT NULL,
            manufacturer TEXT,
            model TEXT,
            device_identifier TEXT UNIQUE,
            status TEXT NOT NULL DEFAULT 'connected',
            last_synced_at TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_health_devices_user ON health_devices(user_id);

        CREATE TABLE IF NOT EXISTS home_health_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            requested_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            service_type TEXT NOT NULL,
            scheduled_date TEXT NOT NULL,
            address TEXT NOT NULL,
            city TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'requested',
            notes TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_home_health_patient ON home_health_requests(patient_id);

        CREATE TABLE IF NOT EXISTS ambulance_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            requested_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            transport_type TEXT NOT NULL DEFAULT 'emergency_ambulance',
            pickup_address TEXT NOT NULL,
            destination_address TEXT,
            urgency TEXT NOT NULL DEFAULT 'emergency',
            status TEXT NOT NULL DEFAULT 'requested',
            notes TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ambulance_patient ON ambulance_requests(patient_id);

        CREATE TABLE IF NOT EXISTS medicine_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            ordered_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            pharmacy_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            items_json TEXT NOT NULL,
            delivery_address TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            prescription_record_id INTEGER REFERENCES medical_records(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_medicine_orders_patient ON medicine_orders(patient_id);

        CREATE TABLE IF NOT EXISTS medicine_reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            medicine_name TEXT NOT NULL,
            dosage TEXT,
            frequency TEXT NOT NULL DEFAULT 'daily',
            reminder_time TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_medicine_reminders_user ON medicine_reminders(user_id, active);

        -- Milestone 7: agentic core, telehealth, camera intelligence, operations

        CREATE TABLE IF NOT EXISTS agent_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            agent_name TEXT NOT NULL,
            command_text TEXT NOT NULL,
            intent TEXT,
            status TEXT NOT NULL DEFAULT 'completed',
            urgency TEXT NOT NULL DEFAULT 'routine',
            result_summary TEXT,
            approval_state TEXT NOT NULL DEFAULT 'not_required',
            duration_ms INTEGER,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_agent_runs_actor ON agent_runs(actor_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_agent_runs_status ON agent_runs(status, created_at);

        CREATE TABLE IF NOT EXISTS agent_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER REFERENCES agent_runs(id) ON DELETE CASCADE,
            actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            agent_name TEXT NOT NULL,
            action_type TEXT NOT NULL,
            tool_name TEXT,
            entity_type TEXT,
            entity_id TEXT,
            status TEXT NOT NULL DEFAULT 'completed',
            approval_state TEXT NOT NULL DEFAULT 'not_required',
            message TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_agent_actions_run ON agent_actions(run_id);
        CREATE INDEX IF NOT EXISTS idx_agent_actions_status ON agent_actions(status, created_at);

        CREATE TABLE IF NOT EXISTS agent_tool_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER REFERENCES agent_runs(id) ON DELETE CASCADE,
            actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            tool_name TEXT NOT NULL,
            input_summary TEXT,
            output_summary TEXT,
            status TEXT NOT NULL DEFAULT 'completed',
            error TEXT,
            duration_ms INTEGER,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_agent_tool_calls_run ON agent_tool_calls(run_id);

        CREATE TABLE IF NOT EXISTS agent_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER REFERENCES agent_runs(id) ON DELETE CASCADE,
            actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            operation_type TEXT NOT NULL DEFAULT 'agent_action',
            status TEXT NOT NULL DEFAULT 'pending',
            requested_at TEXT NOT NULL DEFAULT '',
            decided_at TEXT,
            decision_note TEXT,
            requested_by_agent TEXT NOT NULL DEFAULT 'ZENDOC Core Agent',
            requested_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            action_type TEXT,
            task_id INTEGER REFERENCES agent_tasks(id) ON DELETE SET NULL,
            payload_summary TEXT,
            risk_level TEXT NOT NULL DEFAULT 'owner_approval',
            approver_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            resolved_at TEXT,
            resolved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            resolution_note TEXT,
            expires_at TEXT,
            created_at TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_agent_approvals_status ON agent_approvals(status, requested_at);

        CREATE TABLE IF NOT EXISTS platform_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            agent_name TEXT,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT,
            status TEXT NOT NULL DEFAULT 'info',
            error TEXT,
            approval_state TEXT NOT NULL DEFAULT 'not_required',
            duration_ms INTEGER,
            event_type TEXT,
            payload_json TEXT NOT NULL DEFAULT '{}',
            correlation_id TEXT,
            idempotency_key TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_platform_events_status ON platform_events(status, created_at);

        CREATE TABLE IF NOT EXISTS doctor_availability (
            doctor_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'offline',
            accepts_chat INTEGER NOT NULL DEFAULT 1,
            accepts_voice INTEGER NOT NULL DEFAULT 0,
            accepts_video INTEGER NOT NULL DEFAULT 0,
            patient_message_policy TEXT NOT NULL DEFAULT 'accepted_consultation',
            allow_voice_requests INTEGER NOT NULL DEFAULT 0,
            allow_video_requests INTEGER NOT NULL DEFAULT 0,
            allow_new_consultation_requests INTEGER NOT NULL DEFAULT 1,
            note TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS consultation_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            doctor_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            appointment_id INTEGER REFERENCES appointments(id) ON DELETE SET NULL,
            consultation_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'requested',
            reason TEXT NOT NULL,
            scheduled_for TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_consultations_patient ON consultation_requests(patient_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_consultations_doctor ON consultation_requests(doctor_id, status);

        CREATE TABLE IF NOT EXISTS consultation_rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consultation_id INTEGER NOT NULL UNIQUE REFERENCES consultation_requests(id) ON DELETE CASCADE,
            room_token_hash TEXT NOT NULL UNIQUE,
            provider TEXT NOT NULL DEFAULT 'local_demo',
            status TEXT NOT NULL DEFAULT 'waiting',
            created_at TEXT NOT NULL,
            ended_at TEXT
        );

        CREATE TABLE IF NOT EXISTS consultation_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consultation_id INTEGER NOT NULL REFERENCES consultation_requests(id) ON DELETE CASCADE,
            sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            body TEXT NOT NULL,
            attachment_record_id INTEGER REFERENCES medical_records(id) ON DELETE SET NULL,
            read_at TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_consultation_messages ON consultation_messages(consultation_id, created_at);

        CREATE TABLE IF NOT EXISTS communication_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requester_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            target_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            context_type TEXT NOT NULL,
            context_id TEXT,
            allow_chat INTEGER NOT NULL DEFAULT 1,
            allow_voice INTEGER NOT NULL DEFAULT 0,
            allow_video INTEGER NOT NULL DEFAULT 0,
            allow_record_sharing INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            expires_at TEXT,
            revoked_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_comm_permissions_pair ON communication_permissions(requester_id, target_user_id, status, revoked_at);
        CREATE INDEX IF NOT EXISTS idx_comm_permissions_context ON communication_permissions(context_type, context_id);

        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_type TEXT NOT NULL DEFAULT 'direct',
            title TEXT,
            created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            context_type TEXT,
            context_id TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_conversations_context ON conversations(context_type, context_id);
        CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at);

        CREATE TABLE IF NOT EXISTS conversation_participants (
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'member',
            joined_at TEXT NOT NULL,
            last_read_at TEXT,
            muted INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (conversation_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_conversation_participants_user ON conversation_participants(user_id, conversation_id);

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            message_type TEXT NOT NULL DEFAULT 'text',
            body TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            edited_at TEXT,
            deleted_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, created_at);

        CREATE TABLE IF NOT EXISTS message_receipts (
            message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'delivered',
            delivered_at TEXT NOT NULL,
            read_at TEXT,
            PRIMARY KEY (message_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_message_receipts_user ON message_receipts(user_id, read_at);

        CREATE TABLE IF NOT EXISTS message_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
            attachment_type TEXT NOT NULL,
            record_id INTEGER REFERENCES medical_records(id) ON DELETE SET NULL,
            url TEXT,
            title TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS staff_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            staff_type TEXT NOT NULL,
            service_area TEXT,
            status TEXT NOT NULL DEFAULT 'available',
            verified INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_staff_profiles_type ON staff_profiles(staff_type, status);

        CREATE TABLE IF NOT EXISTS staff_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requested_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            assigned_staff_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            patient_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            source_type TEXT,
            source_id TEXT,
            task_type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'requested',
            escalation_reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_staff_tasks_requested_by ON staff_tasks(requested_by, status);
        CREATE INDEX IF NOT EXISTS idx_staff_tasks_assigned ON staff_tasks(assigned_staff_id, status);

        CREATE TABLE IF NOT EXISTS staff_task_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES staff_tasks(id) ON DELETE CASCADE,
            actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            event_type TEXT NOT NULL,
            message TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS fitness_pose_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            exercise TEXT NOT NULL,
            reps INTEGER NOT NULL DEFAULT 0,
            sets INTEGER NOT NULL DEFAULT 0,
            duration_seconds INTEGER NOT NULL DEFAULT 0,
            confidence REAL,
            status TEXT NOT NULL DEFAULT 'completed',
            notes TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_pose_sessions_user ON fitness_pose_sessions(user_id, created_at);

        CREATE TABLE IF NOT EXISTS fitness_pose_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pose_session_id INTEGER NOT NULL REFERENCES fitness_pose_sessions(id) ON DELETE CASCADE,
            feedback_type TEXT NOT NULL,
            message TEXT NOT NULL,
            confidence REAL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS video_search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            query TEXT NOT NULL,
            category TEXT,
            provider TEXT NOT NULL,
            available INTEGER NOT NULL DEFAULT 0,
            result_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_video_search_user ON video_search_history(user_id, created_at);

        -- Milestone 8: Intelligence, Task Engine, Approvals, Alerts, Events

        CREATE TABLE IF NOT EXISTS agent_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT NOT NULL,
            requested_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            assigned_agent TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            priority TEXT NOT NULL DEFAULT 'normal',
            risk_level TEXT NOT NULL DEFAULT 'low_risk',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            idempotency_key TEXT UNIQUE,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            result_summary TEXT,
            last_error_category TEXT,
            duration_ms INTEGER,
            started_at TEXT,
            completed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_agent_tasks_status ON agent_tasks(status, created_at);
        CREATE INDEX IF NOT EXISTS idx_agent_tasks_requested_by ON agent_tasks(requested_by);

        CREATE TABLE IF NOT EXISTS agent_task_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES agent_tasks(id) ON DELETE CASCADE,
            status TEXT NOT NULL,
            message TEXT,
            error_category TEXT,
            duration_ms INTEGER,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_agent_task_attempts_task ON agent_task_attempts(task_id);

        CREATE TABLE IF NOT EXISTS agent_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            severity TEXT NOT NULL DEFAULT 'info',
            category TEXT NOT NULL DEFAULT 'operational',
            title TEXT NOT NULL,
            summary TEXT,
            source_type TEXT,
            source_id TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            acknowledged_at TEXT,
            acknowledged_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            resolved_at TEXT,
            resolved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            dedupe_key TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_agent_alerts_status ON agent_alerts(status, created_at);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_alerts_dedupe ON agent_alerts(dedupe_key) WHERE dedupe_key IS NOT NULL AND status='active';

        CREATE TABLE IF NOT EXISTS model_execution_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            task_type TEXT,
            intent TEXT,
            provider TEXT NOT NULL,
            model TEXT,
            routing_reason TEXT,
            latency_ms INTEGER,
            success INTEGER NOT NULL DEFAULT 1,
            fallback_used INTEGER NOT NULL DEFAULT 0,
            error_category TEXT,
            privacy_class TEXT NOT NULL DEFAULT 'INTERNAL',
            fallback_reason TEXT,
            structured_output INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_model_exec_logs_actor ON model_execution_logs(actor_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_model_exec_logs_provider ON model_execution_logs(provider, created_at);

        CREATE TABLE IF NOT EXISTS notification_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            channel TEXT NOT NULL DEFAULT 'in_app',
            template_type TEXT,
            status TEXT NOT NULL DEFAULT 'queued',
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            provider_response TEXT,
            created_at TEXT NOT NULL,
            sent_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_notif_deliveries_user ON notification_deliveries(user_id, status);

        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        );
        """
    )

    migrate_schema(db)
    seed_admin()
    _seed_exercises_safe()


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
        "email_normalized": "ALTER TABLE users ADD COLUMN email_normalized TEXT",
        "duplicate_of_user_id": "ALTER TABLE users ADD COLUMN duplicate_of_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL",
        "duplicate_detected_at": "ALTER TABLE users ADD COLUMN duplicate_detected_at TEXT",
        "gender": "ALTER TABLE users ADD COLUMN gender TEXT",
        "city": "ALTER TABLE users ADD COLUMN city TEXT",
        "emergency_contact": "ALTER TABLE users ADD COLUMN emergency_contact TEXT",
        "verified": "ALTER TABLE users ADD COLUMN verified INTEGER NOT NULL DEFAULT 0",
        "active": "ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1",
    }.items():
        if column not in user_columns:
            db.execute(ddl)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS duplicate_account_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_normalized TEXT NOT NULL,
            primary_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            duplicate_user_ids TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'needs_review',
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_duplicate_account_groups_email ON duplicate_account_groups(email_normalized)")
    repair_normalized_email_index(db)
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_normalized ON users(email_normalized)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_users_duplicate_of ON users(duplicate_of_user_id)")
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

    doctor_availability_columns = table_columns(db, "doctor_availability")
    for column, ddl in {
        "patient_message_policy": "ALTER TABLE doctor_availability ADD COLUMN patient_message_policy TEXT NOT NULL DEFAULT 'accepted_consultation'",
        "allow_voice_requests": "ALTER TABLE doctor_availability ADD COLUMN allow_voice_requests INTEGER NOT NULL DEFAULT 0",
        "allow_video_requests": "ALTER TABLE doctor_availability ADD COLUMN allow_video_requests INTEGER NOT NULL DEFAULT 0",
        "allow_new_consultation_requests": "ALTER TABLE doctor_availability ADD COLUMN allow_new_consultation_requests INTEGER NOT NULL DEFAULT 1",
    }.items():
        if column not in doctor_availability_columns:
            db.execute(ddl)

    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS communication_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requester_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            target_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            context_type TEXT NOT NULL,
            context_id TEXT,
            allow_chat INTEGER NOT NULL DEFAULT 1,
            allow_voice INTEGER NOT NULL DEFAULT 0,
            allow_video INTEGER NOT NULL DEFAULT 0,
            allow_record_sharing INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            expires_at TEXT,
            revoked_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_comm_permissions_pair ON communication_permissions(requester_id, target_user_id, status, revoked_at);
        CREATE INDEX IF NOT EXISTS idx_comm_permissions_context ON communication_permissions(context_type, context_id);

        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_type TEXT NOT NULL DEFAULT 'direct',
            title TEXT,
            created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            context_type TEXT,
            context_id TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_conversations_context ON conversations(context_type, context_id);
        CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at);

        CREATE TABLE IF NOT EXISTS conversation_participants (
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'member',
            joined_at TEXT NOT NULL,
            last_read_at TEXT,
            muted INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (conversation_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_conversation_participants_user ON conversation_participants(user_id, conversation_id);

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            message_type TEXT NOT NULL DEFAULT 'text',
            body TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            edited_at TEXT,
            deleted_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, created_at);

        CREATE TABLE IF NOT EXISTS message_receipts (
            message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'delivered',
            delivered_at TEXT NOT NULL,
            read_at TEXT,
            PRIMARY KEY (message_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_message_receipts_user ON message_receipts(user_id, read_at);

        CREATE TABLE IF NOT EXISTS message_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
            attachment_type TEXT NOT NULL,
            record_id INTEGER REFERENCES medical_records(id) ON DELETE SET NULL,
            url TEXT,
            title TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        """
    )

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

    # Milestone 8 is additive so existing M1-M7 databases remain valid.
    for table, additions in {
        "agent_approvals": {
            "requested_by_agent": "TEXT NOT NULL DEFAULT 'ZENDOC Core Agent'",
            "requested_by_user_id": "INTEGER REFERENCES users(id) ON DELETE SET NULL",
            "action_type": "TEXT",
            "task_id": "INTEGER REFERENCES agent_tasks(id) ON DELETE SET NULL",
            "payload_summary": "TEXT",
            "risk_level": "TEXT NOT NULL DEFAULT 'owner_approval'",
            "approver_user_id": "INTEGER REFERENCES users(id) ON DELETE SET NULL",
            "resolved_at": "TEXT",
            "resolved_by": "INTEGER REFERENCES users(id) ON DELETE SET NULL",
            "resolution_note": "TEXT",
            "expires_at": "TEXT",
            "created_at": "TEXT",
        },
        "platform_events": {
            "event_type": "TEXT",
            "payload_json": "TEXT NOT NULL DEFAULT '{}'",
            "correlation_id": "TEXT",
            "idempotency_key": "TEXT",
        },
        "agent_tasks": {
            "duration_ms": "INTEGER",
        },
        "agent_task_attempts": {
            "duration_ms": "INTEGER",
        },
        "agent_alerts": {
            "acknowledged_by": "INTEGER REFERENCES users(id) ON DELETE SET NULL",
            "resolved_at": "TEXT",
            "resolved_by": "INTEGER REFERENCES users(id) ON DELETE SET NULL",
            "dedupe_key": "TEXT",
        },
        "model_execution_logs": {
            "privacy_class": "TEXT NOT NULL DEFAULT 'INTERNAL'",
            "fallback_reason": "TEXT",
            "structured_output": "INTEGER NOT NULL DEFAULT 1",
        },
    }.items():
        existing_columns = table_columns(db, table)
        for column, ddl in additions.items():
            if column not in existing_columns:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    db.execute(
        """
        UPDATE agent_approvals
        SET created_at=COALESCE(NULLIF(created_at, ''), requested_at),
            action_type=COALESCE(action_type, operation_type),
            requested_by_user_id=COALESCE(requested_by_user_id, actor_id),
            resolved_at=COALESCE(resolved_at, decided_at),
            resolution_note=COALESCE(resolution_note, decision_note)
        """
    )
    db.execute("UPDATE platform_events SET event_type=action WHERE event_type IS NULL OR event_type=''")
    db.execute("CREATE INDEX IF NOT EXISTS idx_agent_approvals_status ON agent_approvals(status, requested_at)")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_platform_events_idempotency ON platform_events(idempotency_key) WHERE idempotency_key IS NOT NULL")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_alerts_dedupe ON agent_alerts(dedupe_key) WHERE dedupe_key IS NOT NULL AND status='active'")
    db.execute("CREATE INDEX IF NOT EXISTS idx_model_exec_logs_privacy ON model_execution_logs(privacy_class, created_at)")
    db.execute(
        "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES ('m8_agent_platform_v1', ?)",
        (now_iso(),),
    )
    db.execute(
        "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES ('m8_1_local_ai_runtime_v1', ?)",
        (now_iso(),),
    )
    db.commit()


def repair_normalized_email_index(db):
    rows = db.execute("SELECT id, email, active, created_at FROM users ORDER BY id ASC").fetchall()
    groups = {}
    for row in rows:
        normalized = (row["email"] or "").strip().lower()
        if not normalized:
            continue
        groups.setdefault(normalized, []).append(row)
    now = now_iso()
    for normalized, items in groups.items():
        primary = sorted(items, key=lambda row: (0 if row["active"] else 1, row["id"]))[0]
        duplicate_ids = [row["id"] for row in items if row["id"] != primary["id"]]
        db.execute(
            """
            UPDATE users
            SET email_normalized=?, duplicate_of_user_id=NULL, duplicate_detected_at=NULL
            WHERE id=?
            """,
            (normalized, primary["id"]),
        )
        for duplicate_id in duplicate_ids:
            db.execute(
                """
                UPDATE users
                SET email_normalized=NULL, duplicate_of_user_id=?, duplicate_detected_at=COALESCE(duplicate_detected_at, ?)
                WHERE id=?
                """,
                (primary["id"], now, duplicate_id),
            )
        if duplicate_ids:
            db.execute(
                """
                INSERT INTO duplicate_account_groups
                (email_normalized, primary_user_id, duplicate_user_ids, status, notes, created_at, updated_at)
                VALUES (?, ?, ?, 'needs_review', ?, ?, ?)
                ON CONFLICT(email_normalized) DO UPDATE SET
                    primary_user_id=excluded.primary_user_id,
                    duplicate_user_ids=excluded.duplicate_user_ids,
                    updated_at=excluded.updated_at
                """,
                (
                    normalized,
                    primary["id"],
                    json.dumps(duplicate_ids),
                    "Automatically detected during normalized-email repair; no accounts were deleted.",
                    now,
                    now,
                ),
            )


def _legacy_admin_non_privileged_role(db, user_id):
    """Return a deterministic pre-Admin role only when account metadata proves it."""
    provider = db.execute(
        "SELECT provider_type FROM provider_profiles WHERE user_id=?",
        (user_id,),
    ).fetchone()
    if provider and provider["provider_type"] in {"doctor", "hospital", "pharmacy"}:
        return provider["provider_type"], "restored_provider_profile_role"
    return LEGACY_ADMIN_FALLBACK_ROLE, "fallback_no_reliable_role_metadata"


def _owner_identity_matches(row, owner_email, normalize_email):
    return owner_email in {
        normalize_email(row["email"]),
        normalize_email(row["email_normalized"]),
    }


def _create_single_admin_index(db):
    # This is deliberately called only after legacy rows have been reconciled.
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_single_admin
        ON users((CASE WHEN role='admin' THEN 1 END))
        WHERE role='admin'
        """
    )


def seed_admin():
    """Bootstrap the owner and reconcile only legacy multi-Admin databases."""
    from .auth import normalize_email
    from .config import ConfigError

    db = get_db()
    owner_email = normalize_email(current_app.config.get("ADMIN_EMAIL"))
    owner_password = current_app.config.get("ADMIN_PASSWORD")
    users = db.execute(
        "SELECT id, email, email_normalized, role FROM users ORDER BY id"
    ).fetchall()
    admin_rows = [row for row in users if row["role"] == "admin"]

    if not owner_email:
        if admin_rows:
            raise ConfigError(
                "Owner integrity violation: ZENDOC_ADMIN_EMAIL is required because Admin account data exists; "
                "no owner was selected automatically."
            )
        return

    owner_matches = [
        row for row in users if _owner_identity_matches(row, owner_email, normalize_email)
    ]
    if len(owner_matches) > 1:
        raise ConfigError(
            "Owner integrity violation: ZENDOC_ADMIN_EMAIL matches more than one normalized account; "
            "owner identity is ambiguous and no account was selected or merged."
        )

    if len(admin_rows) > 1:
        if not owner_matches or owner_matches[0]["role"] != "admin":
            raise ConfigError(
                "Owner integrity violation: ZENDOC_ADMIN_EMAIL does not match any legacy Admin account; "
                "configure the legitimate owner explicitly before retrying."
            )

        owner = owner_matches[0]
        now = now_iso()
        try:
            db.execute("BEGIN IMMEDIATE")
            for legacy_admin in admin_rows:
                if legacy_admin["id"] == owner["id"]:
                    continue
                new_role, role_source = _legacy_admin_non_privileged_role(db, legacy_admin["id"])
                db.execute(
                    "UPDATE users SET role=?, updated_at=? WHERE id=? AND role='admin'",
                    (new_role, now, legacy_admin["id"]),
                )
                db.execute(
                    """
                    INSERT INTO audit_logs (actor_id, action, entity_type, entity_id, created_at)
                    VALUES (?, ?, 'user', ?, ?)
                    """,
                    (
                        owner["id"],
                        f"security.legacy_admin_demoted.admin_to_{new_role}.{role_source}",
                        str(legacy_admin["id"]),
                        now,
                    ),
                )

            db.execute(
                "UPDATE users SET verified=1, active=1, email_normalized=?, updated_at=? WHERE id=?",
                (owner_email, now, owner["id"]),
            )
            remaining_admins = db.execute(
                "SELECT id FROM users WHERE role='admin' ORDER BY id"
            ).fetchall()
            if [row["id"] for row in remaining_admins] != [owner["id"]]:
                raise ConfigError(
                    "Owner integrity violation: legacy Admin reconciliation did not produce exactly the configured owner."
                )
            _create_single_admin_index(db)
            db.execute(
                "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (LEGACY_ADMIN_RECONCILIATION_VERSION, now),
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        return

    if admin_rows:
        if not owner_matches or owner_matches[0]["id"] != admin_rows[0]["id"]:
            raise ConfigError(
                "Owner integrity violation: configured owner does not match the existing Admin account."
            )
        try:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE users SET verified=1, active=1, email_normalized=? WHERE id=?",
                (owner_email, admin_rows[0]["id"]),
            )
            _create_single_admin_index(db)
            db.commit()
        except Exception:
            db.rollback()
            raise
        return

    if owner_matches:
        raise ConfigError(
            "Owner bootstrap refused: the configured Admin email belongs to a non-Admin account. "
            "Choose a new owner email or resolve the account collision server-side."
        )
    if not owner_password:
        raise ConfigError("ZENDOC_ADMIN_PASSWORD is required to create the configured owner account.")

    now = now_iso()
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            """
            INSERT INTO users (name, email, email_normalized, password_hash, role, verified, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'admin', 1, ?, ?)
            """,
            (
                "ZENDOC Admin",
                owner_email,
                owner_email,
                generate_password_hash(owner_password),
                now,
                now,
            ),
        )
        _create_single_admin_index(db)
        db.commit()
    except Exception:
        db.rollback()
        raise


def _seed_exercises_safe():
    """Seed the exercise library.  Imported here to avoid circular imports."""
    try:
        from .exercise_library import seed_exercises
        seed_exercises()
    except Exception:
        pass  # Exercise seeding failure must not block app startup
