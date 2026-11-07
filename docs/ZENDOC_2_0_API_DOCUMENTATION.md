# ZENDOC 2.0 — API Documentation

> Generated: 2026-11-07  
> Framework: Next.js 15 App Router  
> Auth: Supabase Auth (SSR session cookies)

---

## Authentication

All protected endpoints require an active Supabase session cookie set by the
`/api/auth/callback` route. The middleware (`src/middleware.ts`) enforces
authentication on all routes except those in the public allowlist.

**Session lifecycle:**
1. User registers → `POST /api/auth` (Server Action `signUpAction`)
2. Email confirmation → user clicks link → `GET /api/auth/callback?code=…`
3. Session cookie set → all subsequent requests carry it automatically
4. Sign-out → `POST /api/auth/signout` → cookie cleared → redirect to `/login`

---

## API Routes

### Health

#### `GET /api/health`
Application health probe. Used by load balancers and CI.

**Auth:** None required  
**Response `200`:**
```json
{ "status": "ok", "version": "2.0.0", "timestamp": "2026-11-07T12:00:00Z" }
```

---

### Authentication

#### `GET /api/auth/callback`
Supabase email link handler. Exchanges a one-time `code` for a session cookie.

**Auth:** None (this IS the auth flow)  
**Query parameters:**

| Param | Required | Description |
|-------|----------|-------------|
| `code` | ✅ | One-time Supabase exchange code |
| `type` | No | `signup` (default), `recovery`, `magiclink` |
| `next` | No | Redirect path after success (default: `/dashboard`) |

**Redirects:**
- `302 → /dashboard` on success (patient)
- `302 → /reset-password` when `type=recovery`
- `302 → /login?error=invalid-link` on missing/consumed code
- `302 → /login?error=auth-callback-failed` on exchange error

---

#### `POST /api/auth/signout`
Signs the authenticated user out server-side. Clears session cookie.

**Auth:** Session cookie (optional — always redirects)  
**Response:** `303 → /login`

---

### AI Advisory

#### `POST /api/ai/chat`
ZENDOC AI Advisory endpoint. Applies deterministic emergency triage **before**
any AI model is consulted. Returns emergency escalation data if red-flag
symptoms are detected.

**Auth:** None (public — rate limiting applies)  
**Request:**
```json
{
  "message": "string (required, non-empty)",
  "context": {
    "patientId": "uuid (optional)",
    "conditions": ["string"],
    "medications": ["string"]
  }
}
```

**Response `200`:**
```json
{
  "response": "string",
  "is_emergency": false,
  "emergency_level": "GREEN | YELLOW | RED",
  "emergency_numbers": ["102 (Ambulance - India)", "112"],
  "disclaimer": "ZENDOC AI is strictly for educational purposes…",
  "provider": "mock | anthropic | openai | gemini",
  "action_advice": "string"
}
```

**Response `400`:** `{ "error": "Valid query message is required." }`  
**Response `500`:** `{ "error": "Internal Server Error" }`

> [!CAUTION]
> When `is_emergency: true` and `emergency_level: "RED"`, the UI **must** display
> emergency call numbers prominently and suppress any AI advisory text.
> This is enforced in `src/lib/ai/model-router.ts`.

---

### Medical Records

#### `POST /api/records/upload`
Uploads a medical document to Supabase Storage and writes a metadata row to
the `medical_records` table.

**Auth:** Session cookie required (401 if missing)  
**Content-Type:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | File | ✅ | PDF, JPEG, PNG, WEBP, HEIC, or DICOM. Max 25 MB |
| `title` | string | ✅ | Human-readable document name |
| `record_type` | string | No | `lab_result`, `prescription`, `discharge`, `imaging`, `general` |
| `source_facility` | string | No | Hospital / clinic name |
| `record_date` | string | No | ISO date `YYYY-MM-DD` (defaults to today) |

**Response `201`:**
```json
{ "recordId": "uuid", "storagePath": "user-id/2026-11-07/uuid.pdf" }
```

**Response `401`:** `{ "error": "Unauthorized." }`  
**Response `422`:** `{ "error": "File type 'text/html' is not permitted…" }`

---

### Python Worker Boundary

#### `POST /api/workers/asr`
Forwards audio to the Python Whisper ASR worker with HMAC authentication.

**Auth:** Session cookie required  
**Feature flag:** `PYTHON_WORKER_ENABLED=true` (default: `false`)  
**Content-Type:** `multipart/form-data` with audio file  
**Response `503`:** `{ "error": "ASR worker is not enabled…", "code": "WORKER_DISABLED" }` when flagged off  
**Response `200`:** Passthrough from Python worker

---

#### `POST /api/workers/ocr`
Forwards a document to the Python OCR/extraction pipeline.

**Auth:** Session cookie required  
**Feature flag:** `PYTHON_WORKER_ENABLED=true`  
**Response:** Passthrough from Python worker

---

#### `GET /api/workers/health`
Reports the health of the Python worker boundary.

**Auth:** None  
**Response `200` (worker disabled):**
```json
{
  "worker": { "enabled": false, "status": "disabled" },
  "nextjs": { "status": "ok" }
}
```
**Response `200` (worker healthy):**
```json
{
  "worker": { "enabled": true, "status": "ok", "upstreamResponse": {} },
  "nextjs": { "status": "ok" }
}
```
**Response `502`:** Worker unreachable

---

## Server Actions

Server Actions run entirely server-side via React's `'use server'` directive.
They are called from Client Components using `useActionState` and from Server
Components directly.

### Auth Actions (`src/actions/auth.ts`)

| Action | Description |
|--------|-------------|
| `signInAction(prevState, formData)` | Validates credentials, calls `supabase.auth.signInWithPassword`, redirects by role |
| `signUpAction(prevState, formData)` | Validates registration, calls `supabase.auth.signUp`, inserts `profiles` row, redirects |
| `signOutAction()` | Calls `supabase.auth.signOut`, redirects to `/login` |
| `getCurrentUser()` | Server helper — returns authenticated user or `null` |

**FormData fields for `signInAction`:** `email`, `password`  
**FormData fields for `signUpAction`:** `fullName`, `email`, `phone`, `password`, `role`

---

### Patient Actions (`src/actions/patient.ts`)

| Action | Description | Returns |
|--------|-------------|---------|
| `listHealthMetrics()` | Fetch all health metrics for current patient | `{ success, data[] }` |
| `addHealthMetric(prevState, formData)` | Insert new metric row | `{ success, data: { id } }` |
| `listMedicalRecords()` | Fetch medical record metadata | `{ success, data[] }` |
| `getSignedRecordUrl(recordId)` | Generate 5-min signed download URL | `{ success, data: { url } }` |
| `listHealthTimeline()` | Fetch timeline events | `{ success, data[] }` |
| `getPatientProfile()` | Fetch profile row | `{ success, data }` |
| `updatePatientProfile(prevState, formData)` | Update profile fields | `{ success }` |

---

### Appointment Actions (`src/actions/appointment.ts`)

| Action | Description | Returns |
|--------|-------------|---------|
| `listAppointments()` | List appointments with provider + facility join | `{ success, data[] }` |
| `bookAppointment(prevState, formData)` | Create appointment row with status `requested` | `{ success, data: { id } }` |
| `cancelAppointment(appointmentId)` | Set status to `cancelled` | `{ success }` |

**FormData fields for `bookAppointment`:** `provider_profile_id`, `facility_id`, `appointment_type`, `scheduled_at`, `chief_complaint`, `consultation_mode`

---

### Consent Actions (`src/actions/consent.ts`)

| Action | Description |
|--------|-------------|
| `grantConsent(granteeId, dataCategory, expiresAt?)` | Create active consent grant |
| `revokeConsent(consentId)` | Set consent status to `revoked` |
| `listConsents()` | List all outgoing consents for current user |

---

### Discovery Actions (`src/actions/discovery.ts`)

| Action | Params | Description |
|--------|--------|-------------|
| `searchFacilities(query)` | `{ city?, facility_type?, name?, limit? }` | Search verified facilities |
| `searchProviders(query)` | `{ specialisation?, city?, name?, limit? }` | Search verified providers |

> [!IMPORTANT]
> These actions return only real database rows. They **never** fabricate
> provider ratings, distances, verification status, or availability slots.

---

### Record Actions (`src/actions/records.ts`)

| Action | Description |
|--------|-------------|
| `uploadMedicalRecord(formData)` | Validates file, uploads to Supabase Storage bucket `medical-records`, inserts metadata row |

---

### Audit Actions (`src/actions/audit.ts`)

| Action | Description |
|--------|-------------|
| `appendAuditLog(action, resourceType, resourceId?, metadata?)` | Append-only server-side audit entry. Never throws — failures are silently swallowed to prevent blocking calling flows |
| `listAuditLogs(limit?, offset?)` | Paginated audit log listing (admin-only via RLS) |

---

## Middleware (`src/middleware.ts`)

Runs on every request matching `/((?!_next/static|_next/image|favicon.ico).*)`.

**Behaviour when Supabase is NOT configured** (placeholder URL/key):  
All requests pass through — the app renders its synthetic-data UI.

**Behaviour when Supabase IS configured:**

| Condition | Action |
|-----------|--------|
| Unauthenticated → protected route | Redirect to `/login?redirectTo=<path>` |
| Authenticated → `/login` or `/register` | Redirect to role home |
| Non-admin → `/admin/*` | Redirect to role home |
| Non-provider + non-admin → `/provider/*` | Redirect to role home |

**Public routes (no auth required):**  
`/`, `/login`, `/register`, `/find-care`, `/shop`, `/community`,  
`/api/health`, `/api/ai/chat`, `/api/auth/callback`

---

## Security Notes

- **Service role key** (`SUPABASE_SERVICE_ROLE_KEY`) is **never** in browser code.  
  Used only in server-side contexts (Server Actions, API routes) when elevated
  privilege is explicitly required.
- **Signed URLs** for medical records have a 5-minute TTL and are generated
  server-side only.
- **HMAC tokens** (`X-Zendoc-Hmac`) protect the Next.js → Python worker
  boundary using `PYTHON_WORKER_SECRET`.
- **File upload validation** rejects non-allowlisted MIME types and enforces a
  25 MB ceiling before the file reaches Supabase Storage.
- **RLS** is the final enforcement layer — even if application code has a bug,
  Supabase Row Level Security prevents cross-tenant data leakage.
