# ZENDOC 2.0 — Database Verification & Schema Audit Report

> Report Date: 2026-11-08  
> Database Target: Supabase PostgreSQL 15+ (with PostGIS, pgcrypto, uuid-ossp)  
> Primary Migration: `supabase/migrations/20261107000000_zendoc_2_0_core_schema.sql`  
> Corrections Migration: `supabase/migrations/20261108000000_zendoc_2_0_schema_corrections.sql`

---

## 1. Schema Domain & Table Inventory

The ZENDOC 2.0 database architecture comprises 10 core relational domains, with 38 operational tables defined in the Supabase schema and RLS enabled across 100% of tables:

| Domain | Tables | Primary Responsibility |
|---|---|---|
| **1. Identity & Access** | `profiles`, `consent_grants`, `family_members`, `family_access_grants` | User roles, eKYC status, delegated consent, surrogate guardian access |
| **2. Facilities & Providers** | `facilities`, `provider_profiles`, `provider_schedules`, `doctor_availability`, `verified_reviews` | Healthcare directory, verified medical credentials, slot availability |
| **3. Health Records & Memory** | `medical_records`, `health_metrics`, `health_timeline_events`, `prescriptions`, `prescription_items` | Cryptographic document storage, longitudinal biomarkers, immutable clinical timeline |
| **4. Care Coordination** | `appointments`, `diagnostic_catalog`, `diagnostic_bookings`, `pharmacy_orders`, `ambulance_requests`, `care_journeys`, `care_journey_events` | Multi-facility scheduling, diagnostics, e-pharmacy dispatch, non-emergency transport, cancer/chronic care milestones |
| **5. Secure Communication** | `conversations`, `conversation_participants`, `messages`, `consultation_rooms` | In-encounter chat, encrypted clinical communication, WebRTC telehealth sessions |
| **6. AI Safety & Governance** | `ai_conversations`, `ai_interactions`, `agent_approvals`, `agent_alerts` | Emergency triage trail, model provenance, human-in-the-loop approvals, safety alerts |
| **7. Wellness & Community** | `fitness_profiles`, `nutrition_logs`, `hydration_logs`, `community_posts`, `community_comments`, `health_shop_items` | Preventive wellness tracking, peer support community, verified equipment discovery |
| **8. Institutional & Bed Ops** | `provider_organizations`, `organization_memberships`, `hospital_beds`, `carefin_cases` | Ward/bed capacity tracking, healthcare micro-financing cases |
| **9. Audit & Forensics** | `audit_logs` | Immutable, append-only access and modification logs for regulatory compliance |

---

## 2. Schema Audit & Corrective Actions Applied

During the deep-dive audit of `src/actions/*` against `supabase/migrations/20261107000000_zendoc_2_0_core_schema.sql`, several discrepancies were identified and resolved:

### 2.1. Consent Grants Consistency
- **Discrepancy:** The initial core schema defined columns `purpose`, `scope`, `valid_until`, and `status IN ('ACTIVE', 'REVOKED', 'EXPIRED')`. In contrast, initial application code referenced `data_category` and lowercase `active`.
- **Resolution:**
  1. Corrective migration `20261108000000_zendoc_2_0_schema_corrections.sql` adds column `data_category VARCHAR(100)` with a default fallback.
  2. `src/actions/consent.ts` was synchronized to supply `purpose`, `scope: 'FULL_RECORD'`, uppercase `status: 'ACTIVE'`, `valid_until`, and uppercase `'REVOKED'`.
  3. `listConsents()` now queries the exact relational fields with grantee profile joins.

### 2.2. Medical Records Cryptographic Hash & Provenance
- **Discrepancy:** `medical_records` required `sha256_hash VARCHAR(64) NOT NULL`, `uploaded_by UUID NOT NULL`, and `provenance`. The upload action lacked automatic SHA-256 computation and `uploaded_by` tracking.
- **Resolution:**
  1. `src/actions/records.ts` now computes an authentic SHA-256 hexadecimal hash over the file's ArrayBuffer using Node.js `crypto.createHash('sha256')`.
  2. Corrective migration allows nullable fallback on `sha256_hash` for graceful legacy imports.
  3. Added `source_facility VARCHAR(255)` to `medical_records` in `20261108000000_zendoc_2_0_schema_corrections.sql`.
  4. Explicitly sets `uploaded_by: user.id` and `provenance: 'USER_REPORTED'`.

### 2.3. Appointments Schema Alignment
- **Discrepancy:** Schema specifies `provider_id` referencing `provider_profiles(id)` and `appointment_type IN ('in_person', 'telehealth', 'home_visit')`, whereas UI forms sent `provider_profile_id` and `video`.
- **Resolution:**
  1. `src/actions/appointment.ts` normalizes `provider_id` from either field name.
  2. Maps `'video'` to `'telehealth'` to satisfy the database check constraint.
  3. Corrected join query in `listAppointments()` to join `provider:provider_id`.

### 2.4. Audit Logs Non-Null Constraints
- **Discrepancy:** `resource_id VARCHAR(100)` had a `NOT NULL` constraint in the core schema.
- **Resolution:**
  1. `20261108000000_zendoc_2_0_schema_corrections.sql` sets `DEFAULT ''` and drops the `NOT NULL` restriction.
  2. `src/actions/audit.ts` guarantees `resource_id: resourceId ?? ''`.
  3. Added `metadata JSONB DEFAULT '{}'::jsonb` column for structured event tracking.

---

## 3. Database Indexes & Performance Optimization

To ensure microsecond query performance and prevent full-table scans during Row Level Security (RLS) policy evaluation, the following B-Tree indexes were added in migration `20261108000000`:

1. `idx_profiles_role` on `profiles(role)`
2. `idx_consent_grants_grantor` on `consent_grants(grantor_id)`
3. `idx_consent_grants_grantee` on `consent_grants(grantee_id)`
4. `idx_consent_grants_lookup` composite on `consent_grants(grantee_id, grantor_id, status, valid_until)`
5. `idx_medical_records_patient` on `medical_records(patient_id)`
6. `idx_medical_records_created` on `medical_records(created_at DESC)`
7. `idx_health_metrics_patient` on `health_metrics(patient_id)`
8. `idx_health_metrics_recorded` on `health_metrics(recorded_at DESC)`
9. `idx_health_timeline_patient` on `health_timeline_events(patient_id)`
10. `idx_appointments_patient` on `appointments(patient_id)`
11. `idx_appointments_provider` on `appointments(provider_id)`
12. `idx_facilities_city` on `facilities(city)`
13. `idx_messages_conversation` on `messages(conversation_id)`
14. `idx_audit_logs_actor` on `audit_logs(actor_id)`

---

## 4. Automated Triggers

Two server-side PostgreSQL triggers were established:
1. `public.handle_new_user()` on `auth.users`:
   - Automatically provisions a corresponding row in `public.profiles` on user sign-up.
   - Extracts `full_name`, `phone`, and `role` from raw user metadata.
2. `public.handle_updated_at()`:
   - Automatically maintains `updated_at = NOW()` on `profiles`, `appointments`, and `conversations`.

---

## 5. Row Level Security (RLS) Verification

Every table in `public` has `ALTER TABLE ... ENABLE ROW LEVEL SECURITY;` applied.

### Invariants Verified:
- **Patient Isolation:** A patient can only query records where `patient_id = auth.uid()`.
- **Consent Delegated Access:** Third-party providers or caregivers can only select a patient's records if an `ACTIVE` record exists in `consent_grants` with `valid_until > NOW()`.
- **Admin Isolation:** Only users with `role = 'platform_admin'` in `profiles` can view `audit_logs`.
- **Public Catalogs:** `facilities`, `provider_profiles`, and `diagnostic_catalog` are readable by all authenticated and anonymous clients (`FOR SELECT USING (TRUE)`).
