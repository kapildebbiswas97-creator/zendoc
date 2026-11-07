# ZENDOC 2.0 — OPERATOR DEPLOYMENT GUIDE
**Step-by-Step Staging Launch, Cloud Environment Provisioning & Verification Runbook**

- **Project:** ZENDOC 2.0 — AI-Powered Healthcare Coordination Platform
- **Target Branch:** `rebuild/zendoc-2.0-vercel`
- **Lead Operations Role:** Principal Cloud Architect & SRE

---

## 1. Required Cloud Services & Free-Tier Options

To operate ZENDOC 2.0 in staging without incurring cloud costs, use the following free-tier services:

1. **Vercel (Hobby Tier):** Hosts the Next.js 15 App Router web application.
2. **Supabase (Free Tier):** Provides PostgreSQL 15, PostgREST API, Auth, and Storage.
3. **Upstash Redis (Serverless Free Tier):** Provides REST-based distributed rate limiting (10,000 commands/day free).
4. **Python Worker Container:** Runs on a low-cost or free container host (e.g., local Docker, Fly.io free allowance, Render web service, or existing VM).

---

## 2. Environment Variables Checklist

Set these environment variables in your Vercel Project Settings (Environment: **Preview & Development**):

```ini
# Application Domain
NEXT_PUBLIC_APP_URL=https://<your-preview-domain>.vercel.app

# Supabase Staging Project
NEXT_PUBLIC_SUPABASE_URL=https://<your-project-id>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
DATABASE_URL=postgresql://postgres.<your-project-id>:<db-password>@aws-0-ap-south-1.pooler.supabase.com:6543/postgres

# Distributed Rate Limiting (Upstash Redis)
UPSTASH_REDIS_REST_URL=https://<your-redis-name>.upstash.io
UPSTASH_REDIS_REST_TOKEN=AX...

# Python Worker Service (ASR & OCR)
PYTHON_WORKER_ENABLED=true
PYTHON_WORKER_URL=http://<worker-ip-or-domain>:8000
PYTHON_WORKER_SECRET=<generate-with-openssl-rand-hex-32>

# AI Advisory Engine
ZENDOC_AI_PROVIDER=mock
ZENDOC_AI_MODEL=claude-3-5-sonnet-20241022
ZENDOC_AI_TIMEOUT=20
```

---

## 3. Step-by-Step Launch Sequence

### Step 1: Initialize Supabase Staging Database
1. Create a new project at [database.new](https://database.new) (Region: `ap-south-1` recommended for India deployments).
2. Navigate to **SQL Editor** in the Supabase Dashboard.
3. Run the core schema migration:
   - Copy file contents from: [`supabase/migrations/20261107000000_zendoc_2_0_core_schema.sql`](file:///C:/Users/SAMSUNG%20USER/Documents/zendoc/supabase/migrations/20261107000000_zendoc_2_0_core_schema.sql)
   - Paste into SQL Editor and click **Run**.
4. Run the schema corrections and index migration:
   - Copy file contents from: [`supabase/migrations/20261108000000_zendoc_2_0_schema_corrections.sql`](file:///C:/Users/SAMSUNG%20USER/Documents/zendoc/supabase/migrations/20261108000000_zendoc_2_0_schema_corrections.sql)
   - Paste into SQL Editor and click **Run**.
5. Create the private storage bucket:
   - Go to **Storage** ➡️ **New Bucket**.
   - Name: `medical-records`.
   - Toggle **Public bucket** to `OFF` (Private).
   - Click **Save bucket**.

### Step 2: Deploy Python Worker Microservice
On your container host or local server:
```bash
# 1. Clone repository or copy worker directory
cd zendoc

# 2. Set worker secret
export PYTHON_WORKER_SECRET="your-generated-32-byte-secret"
export PORT=8000

# 3. Launch via Docker Compose
docker compose -f docker-compose.worker.yml up -d --build

# 4. Verify health check
curl http://localhost:8000/api/health
```

### Step 3: Configure Upstash Redis
1. Sign up at [console.upstash.com](https://console.upstash.com).
2. Create a new Database (select nearest region to Vercel deployment).
3. In the database details page, locate **REST API** section.
4. Copy `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN`.

### Step 4: Deploy Next.js to Vercel Preview
```bash
# Push branch to GitHub
git push origin rebuild/zendoc-2.0-vercel
```
1. Open [vercel.com](https://vercel.com) ➡️ Import repository `zendoc`.
2. Set Production Branch to: `rebuild/zendoc-2.0-vercel`.
3. Add the environment variables from Section 2 above.
4. Click **Deploy**.

---

## 4. Post-Deployment Verification Commands

Run these smoke tests against your preview deployment URL:

```bash
# 1. Application Diagnostic Health
curl -s https://<preview-domain>/api/health | jq .

# 2. Check Emergency Triage Interception (Bypasses rate limit)
curl -X POST https://<preview-domain>/api/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "I have crushing chest pain and numbness in my left arm"}' | jq .

# 3. Check Worker Proxy Health
curl -s https://<preview-domain>/api/workers/health | jq .
```
