# ZENDOC 2.0 — Deployment Readiness & Ops Runbook

> Target Environments: Vercel (Next.js 15 Frontend & Server Actions) + Supabase (PostgreSQL 15+, Auth, Storage)  
> Branch: `rebuild/zendoc-2.0-vercel`

---

## 1. Production Build & Architecture Verification

- **Framework:** Next.js 15.5.29 App Router (Turbopack / Webpack production compilation)
- **Node Runtime:** Node.js 18+ (tested on Node.js 22 LTS)
- **TypeScript:** Strict Type Checking enabled (`strict: true`), zero errors reported
- **Total Compiled Routes:** 40 Next.js routes (33 static pages, 7 server-rendered dynamic API endpoints)
- **Total Automated Vitest Tests:** 115 passing tests across 10 test suites
- **E2E Automation:** Playwright Chromium test suites in `./e2e`

---

## 2. Environment Variables Specification

The production environment on Vercel requires the following variables:

```bash
# -----------------------------------------------------------------------------
# Canonical Hostname
# -----------------------------------------------------------------------------
NEXT_PUBLIC_APP_URL=https://zendoc.vercel.app

# -----------------------------------------------------------------------------
# Supabase Configuration
# -----------------------------------------------------------------------------
NEXT_PUBLIC_SUPABASE_URL=https://[YOUR_PROJECT_REF].supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOi...[PUBLIC_ANON_KEY]
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOi...[SERVER_ONLY_SERVICE_ROLE_KEY]
DATABASE_URL=postgresql://postgres.[YOUR_PROJECT_REF]:[PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:6543/postgres

# -----------------------------------------------------------------------------
# AI Advisory Configuration
# -----------------------------------------------------------------------------
ZENDOC_AI_PROVIDER=mock   # 'mock' for synthetic; 'anthropic', 'openai', or 'gemini' for live
ZENDOC_AI_API_KEY=        # Required only if provider is not mock
ZENDOC_AI_MODEL=claude-3-5-sonnet-20241022

# -----------------------------------------------------------------------------
# Optional Python Heavy ML / Whisper Worker
# -----------------------------------------------------------------------------
PYTHON_WORKER_ENABLED=false
PYTHON_WORKER_URL=https://worker.internal.zendoc.com
PYTHON_WORKER_SECRET=[HMAC_SHARED_SECRET_256_BITS]
```

---

## 3. Step-by-Step Vercel Deployment Procedure

1. **Connect GitHub Repository to Vercel:**
   - Log in to Vercel Dashboard.
   - Click **Add New...** -> **Project**.
   - Select `kapildebbiswas97-creator/zendoc`.
   - Set **Production Branch** to `rebuild/zendoc-2.0-vercel`.
2. **Configure Environment Variables:**
   - In the Vercel project settings, paste the required variables from `.env.example`.
   - Ensure `SUPABASE_SERVICE_ROLE_KEY` is unchecked for "Preview" and "Client-exposed" contexts.
3. **Trigger Deployment:**
   - Deploy. Vercel will run `npm run build`.
   - Verify that all 40 routes compile and SSR middleware is provisioned.

---

## 4. Supabase Staging Provisioning

1. Create a Supabase project in the desired region (e.g., `ap-south-1` Mumbai).
2. Execute migration `supabase/migrations/20261107000000_zendoc_2_0_core_schema.sql` in Supabase SQL Editor.
3. Execute corrective migration `supabase/migrations/20261108000000_zendoc_2_0_schema_corrections.sql`.
4. Create Private Storage Bucket:
   - Navigate to **Storage** -> **New Bucket**.
   - Name: `medical-records`.
   - Set to **Private** (authenticated user RLS only).
5. Configure Supabase Auth Redirects:
   - Navigate to **Authentication** -> **URL Configuration**.
   - Add Site URL: `https://zendoc.vercel.app`.
   - Add Redirect URL: `https://zendoc.vercel.app/api/auth/callback`.

---

## 5. Rollback & Disaster Recovery Runbook

1. **Vercel Instant Rollback:**
   - If a regression occurs, open Vercel Dashboard -> **Deployments**.
   - Click the three dots on the previous healthy deployment and click **Rollback to this Deployment**.
   - Traffic routes instantly to the previous build artifact.
2. **Database Point-in-Time Recovery (PITR):**
   - Supabase automatically provides continuous physical WAL archiving.
   - In the event of schema corruption, restore to a timestamp preceding the event.
3. **Legacy Preservation:**
   - Legacy Flask and AWS/OCI configurations remain intact on the untouched `main` branch.
