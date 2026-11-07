# ZENDOC 2.0 â€” Deployment & Infrastructure Runbook

**Product:** ZENDOC 2.0 Rebuild  
**Document version:** 2.0.0  
**Target Environments:** Vercel (Edge & Serverless Next.js) + Supabase (PostgreSQL, Auth, Storage)  
**Status:** Authoritative Operations Runbook  

---

## 1. Overview & Architecture Transition

ZENDOC 2.0 deprecates legacy IaaS infrastructure (AWS EC2, OCI Compute, Render, and custom Caddy reverse-proxy setups) in favor of a modern, serverless, globally distributed healthcare web application:

- **Frontend & Server Actions**: Hosted natively on **Vercel** with Next.js 15+ App Router.
- **Database, Auth & Storage**: Hosted on **Supabase** (PostgreSQL 15+, Supabase Auth SSR, Supabase Private Storage).
- **Optional Python Services**: Decoupled microservice boundary for heavy ML/Whisper ASR, invoked via secure authenticated HTTP.

---

## 2. Environment Variables & Configuration

A `.env.example` file is maintained in the repository root. All required variables are documented below:

| Environment Variable | Description | Client/Server | Required | Example Value |
|---|---|---|---|---|
| `NEXT_PUBLIC_APP_URL` | Canonical public URL of the application | Client & Server | Yes | `https://zendoc.vercel.app` |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase Project API endpoint | Client & Server | Yes | `https://xyzproject.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Public client anonymous JWT key | Client & Server | Yes | `eyJhbGciOi...` |
| `SUPABASE_SERVICE_ROLE_KEY` | Privileged admin key for backend operations | Server Only | Yes | `eyJhbGciOi...` (NEVER EXPOSE TO CLIENT) |
| `ZENDOC_AI_PROVIDER` | AI completion engine provider | Server Only | Optional | `anthropic`, `openai`, `gemini`, `mock` |
| `ZENDOC_AI_API_KEY` | API key for the chosen AI provider | Server Only | Optional | `sk-ant-api03-...` |
| `ZENDOC_AI_MODEL` | Default model identifier | Server Only | Optional | `claude-3-5-sonnet-20241022` |
| `PYTHON_WORKER_URL` | Optional internal Python worker endpoint | Server Only | Optional | `https://worker.internal.zendoc.io` |
| `PYTHON_WORKER_SECRET` | Secret bearer token for worker calls | Server Only | Optional | `sec_hex64_...` |

### Security Invariants
1. `SUPABASE_SERVICE_ROLE_KEY` must **never** be prefixed with `NEXT_PUBLIC_`.
2. Do not commit `.env.local`, `.env.production`, or real API secrets to Git.
3. Vercel Preview Deployments inherit preview-specific environment variables in the Vercel dashboard.

---

## 3. Supabase Setup & Database Migration

### 3.1 Initial Project Provisioning
1. Log in to the [Supabase Dashboard](https://supabase.com/dashboard) and create a new project `zendoc-production` (or `zendoc-preview` for staging).
2. Note the Project URL, Anon Key, and Service Role Key from **Project Settings â†’ API**.
3. Under **Database â†’ Extensions**, ensure `postgis` and `uuid-ossp` are enabled.

### 3.2 Running Migrations
The database schema and RLS policies are tracked as reproducible migrations in `supabase/migrations/`:
```bash
# Using the Supabase CLI
supabase login
supabase link --project-ref <your-project-id>
supabase db push
```
Alternatively, apply `supabase/migrations/20261107000000_zendoc_2_0_core_schema.sql` directly using the Supabase SQL Editor.

### 3.3 Storage Bucket Configuration
Create the following private storage buckets under **Storage â†’ Buckets**:
- `medical-records` (Private, 10MB limit, Allowed MIME: `application/pdf, image/jpeg, image/png`)
- `lab-reports` (Private, 10MB limit, Allowed MIME: `application/pdf, image/jpeg, image/png`)
- `prescriptions` (Private, 10MB limit, Allowed MIME: `application/pdf, image/jpeg, image/png`)
- `consultation-attachments` (Private, 15MB limit)
- `community-media` (Public, 5MB limit, Allowed MIME: `image/jpeg, image/png, image/webp`)

Apply storage RLS policies to restrict uploads and signed URL generation to authorized subjects.

---

## 4. Vercel Deployment Guide

### 4.1 Initial Setup via Vercel Dashboard or CLI
1. Import the repository `kapildebbiswas97-creator/zendoc` into Vercel.
2. Select Framework Preset: **Next.js**.
3. Root Directory: `./` (Repository root).
4. Build Command: `npm run build`.
5. Output Directory: `.next`.
6. Install Command: `npm install`.

### 4.2 Preview Branch Configuration
- For development on the rebuild branch, ensure branch `rebuild/zendoc-2.0-vercel` is assigned to a Preview Environment with linked Supabase staging credentials.
- Every commit pushed to `rebuild/zendoc-2.0-vercel` automatically generates an isolated preview URL (e.g. `https://zendoc-git-rebuild-zendoc-2-0-vercel.vercel.app`).

### 4.3 Production Deployment Gate
- Production deployments from `main` or release branches are **strictly gated** on:
  1. Full TypeScript strict compilation passing with 0 errors (`npm run build`).
  2. Complete automated test suite passing (`npm test`).
  3. Security check and lint pass with 0 audit flags.
  4. Explicit clinical and architectural sign-off.

---

## 5. AWS & OCI Infrastructure Retirement Plan

To eliminate redundant infrastructure costs and security overhead without risking data loss:

### 5.1 Safe Deprecation Checklist
- [ ] **Step 1: Backup Verification**
  - Run `pg_dump` on the legacy AWS EC2 / OCI PostgreSQL instance.
  - Export all S3/Object Storage buckets to an encrypted offline archive.
  - Verify archive integrity using SHA-256 checksums.
- [ ] **Step 2: DNS & Traffic Cutover**
  - Update public domain DNS records (CNAME/A records) to point directly to `cname.vercel-dns.com`.
  - Monitor HTTP 5xx error rates and edge latency in the Vercel dashboard.
- [ ] **Step 3: Gateway Deprecation**
  - Delete `vercel.ts` and remove `@vercel/config` proxy dependencies.
  - Confirm requests resolve directly to Next.js App Router handlers.
- [ ] **Step 4: IaaS Instance Termination**
  - Stop (do not immediately terminate) the EC2 / OCI compute instances for 14 days to observe any lingering dependencies.
  - Terminate compute instances only after formal operator authorization.
  - Retain cold database snapshot backups in cold storage for 90 days.

---

## 6. Smoke Testing & Verification Runbook

After any deployment to preview or production, execute the following verification steps:

1. **System Health Check**: Visit `/api/health` â€” verify JSON response `{ "status": "healthy", "version": "2.0.0" }`.
2. **Authentication Flow**:
   - Register a synthetic test patient.
   - Confirm session cookies are issued with `HttpOnly` and `SameSite=Lax`.
   - Log out and verify session tokens are destroyed.
3. **Provider Discovery**:
   - Navigate to `/find-care`.
   - Search for "Cardiology" or "Kolkata".
   - Confirm results load without network errors and no fake ratings are rendered.
4. **Health Memory & Document Upload**:
   - Upload a test PDF document at `/records/upload`.
   - Confirm upload succeeds, file SHA-256 is recorded, and signed download URL functions.
5. **Deterministic Emergency Gate**:
   - Submit "I have crushing chest pain and shortness of breath" in `/ai`.
   - Verify that AI generation is aborted and the emergency diversion banner displays emergency phone numbers (102/108/911/999).
6. **Row Level Security (RLS) Verification**:
   - Attempt an unauthorized API fetch requesting another user's `medical_records` ID.
   - Verify that the response returns `403 Forbidden` or empty dataset.
