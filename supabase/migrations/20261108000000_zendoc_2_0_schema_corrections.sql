-- =============================================================================
-- ZENDOC 2.0 Schema Corrections, Performance Indexes & Triggers
-- Migration: 20261108000000_zendoc_2_0_schema_corrections.sql
-- Target: Supabase PostgreSQL 15+
-- =============================================================================

-- 1. Helper function for updated_at timestamps
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

-- 2. Trigger for auto-creating public.profiles on auth.users sign-up
-- Hardened with explicit search_path to prevent SECURITY DEFINER search_path hijacking
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth, pg_temp
AS $$
BEGIN
    INSERT INTO public.profiles (
        id,
        full_name,
        email,
        phone,
        role,
        data_mode
    )
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email, '@', 1)),
        NEW.email,
        NEW.raw_user_meta_data->>'phone',
        COALESCE(NEW.raw_user_meta_data->>'role', 'patient'),
        'LIVE'
    )
    ON CONFLICT (id) DO UPDATE SET
        full_name = EXCLUDED.full_name,
        phone = COALESCE(EXCLUDED.phone, public.profiles.phone),
        updated_at = NOW();

    RETURN NEW;
END;
$$;

-- Safe attachment to auth.users if auth schema exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'auth' AND table_name = 'users') THEN
        DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
        CREATE TRIGGER on_auth_user_created
            AFTER INSERT ON auth.users
            FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
    END IF;
END;
$$;

-- 3. Schema Adjustments & Safe Defaults
DO $$
BEGIN
    -- consent_grants: add data_category column for category-based grants
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'consent_grants' AND column_name = 'data_category') THEN
        ALTER TABLE public.consent_grants ADD COLUMN data_category VARCHAR(100) DEFAULT 'ALL_HEALTH_DATA';
    END IF;

    -- medical_records: sha256_hash allow nullable for client-side multi-part uploads
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'medical_records' AND column_name = 'sha256_hash' AND is_nullable = 'NO') THEN
        ALTER TABLE public.medical_records ALTER COLUMN sha256_hash DROP NOT NULL;
    END IF;

    -- medical_records: uploaded_by allow nullable fallback
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'medical_records' AND column_name = 'uploaded_by' AND is_nullable = 'NO') THEN
        ALTER TABLE public.medical_records ALTER COLUMN uploaded_by DROP NOT NULL;
    END IF;

    -- medical_records: add source_facility if not present
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'medical_records' AND column_name = 'source_facility') THEN
        ALTER TABLE public.medical_records ADD COLUMN source_facility VARCHAR(255);
    END IF;

    -- audit_logs: resource_id allow nullable or default to empty
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'audit_logs' AND column_name = 'resource_id' AND is_nullable = 'NO') THEN
        ALTER TABLE public.audit_logs ALTER COLUMN resource_id SET DEFAULT '';
        ALTER TABLE public.audit_logs ALTER COLUMN resource_id DROP NOT NULL;
    END IF;

    -- audit_logs: metadata JSONB field
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'audit_logs' AND column_name = 'metadata') THEN
        ALTER TABLE public.audit_logs ADD COLUMN metadata JSONB DEFAULT '{}'::jsonb;
    END IF;

    -- health_metrics: add measured_at alias column or default sync
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'health_metrics' AND column_name = 'measured_at') THEN
        ALTER TABLE public.health_metrics ADD COLUMN measured_at TIMESTAMPTZ DEFAULT NOW();
    END IF;

    -- health_metrics: add device_source if not present
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'health_metrics' AND column_name = 'device_source') THEN
        ALTER TABLE public.health_metrics ADD COLUMN device_source VARCHAR(100);
    END IF;
END;
$$;

-- 4. Foreign Key Performance Indexes (B-Tree Indexes for fast joins & RLS evaluation)
CREATE INDEX IF NOT EXISTS idx_profiles_role ON public.profiles(role);
CREATE INDEX IF NOT EXISTS idx_consent_grants_grantor ON public.consent_grants(grantor_id);
CREATE INDEX IF NOT EXISTS idx_consent_grants_grantee ON public.consent_grants(grantee_id);
CREATE INDEX IF NOT EXISTS idx_consent_grants_lookup ON public.consent_grants(grantee_id, grantor_id, status, valid_until);
CREATE INDEX IF NOT EXISTS idx_medical_records_patient ON public.medical_records(patient_id);
CREATE INDEX IF NOT EXISTS idx_medical_records_created ON public.medical_records(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_health_metrics_patient ON public.health_metrics(patient_id);
CREATE INDEX IF NOT EXISTS idx_health_metrics_recorded ON public.health_metrics(recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_health_timeline_patient ON public.health_timeline_events(patient_id);
CREATE INDEX IF NOT EXISTS idx_appointments_patient ON public.appointments(patient_id);
CREATE INDEX IF NOT EXISTS idx_appointments_provider ON public.appointments(provider_id);
CREATE INDEX IF NOT EXISTS idx_appointments_scheduled ON public.appointments(scheduled_at DESC);
CREATE INDEX IF NOT EXISTS idx_facilities_city ON public.facilities(city);
CREATE INDEX IF NOT EXISTS idx_facilities_category ON public.facilities(category);
CREATE INDEX IF NOT EXISTS idx_provider_profiles_facility ON public.provider_profiles(facility_id);
CREATE INDEX IF NOT EXISTS idx_provider_profiles_specialty ON public.provider_profiles(specialty);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON public.messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conversation_participants_user ON public.conversation_participants(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON public.audit_logs(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON public.audit_logs(created_at DESC);

-- 5. Attach updated_at triggers to mutable tables
DO $$
BEGIN
    DROP TRIGGER IF EXISTS trg_profiles_updated_at ON public.profiles;
    CREATE TRIGGER trg_profiles_updated_at
        BEFORE UPDATE ON public.profiles
        FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

    DROP TRIGGER IF EXISTS trg_appointments_updated_at ON public.appointments;
    CREATE TRIGGER trg_appointments_updated_at
        BEFORE UPDATE ON public.appointments
        FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

    DROP TRIGGER IF EXISTS trg_conversations_updated_at ON public.conversations;
    CREATE TRIGGER trg_conversations_updated_at
        BEFORE UPDATE ON public.conversations
        FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();
END;
$$;

-- 6. Storage Bucket Provisioning (Idempotent for Supabase Storage)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'storage' AND table_name = 'buckets') THEN
        INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
        VALUES (
            'medical-records',
            'medical-records',
            FALSE,
            26214400, -- 25 MB
            ARRAY['application/pdf', 'image/jpeg', 'image/png', 'image/webp', 'image/heic', 'application/dicom']
        )
        ON CONFLICT (id) DO UPDATE SET
            public = FALSE,
            file_size_limit = 26214400;
    END IF;
END;
$$;
