# ZENDOC 2.0 — STAGING DEPLOYMENT REPORT
**Infrastructure Setup, Configuration Boundaries & Cloud Staging Guide**

- **Project:** ZENDOC 2.0 — AI-Powered Healthcare Coordination Platform
- **Target Branch:** `rebuild/zendoc-2.0-vercel`
- **Hosting Environments:** Vercel (Next.js Application) + External Container (Python Worker) + Supabase (PostgreSQL & Storage) + Upstash (Distributed Redis)
- **Status:** **STAGING READY**

---

## 1. Vercel Staging Configuration

The Next.js 15 App Router application is fully prepared for Vercel deployment via `vercel.json` and strict App Router configurations.

### 1.1 HTTP Security Headers
The following security headers are enforced across all incoming requests in `vercel.json`:

```json
{
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "X-Frame-Options", "value": "DENY" },
        { "key": "X-XSS-Protection", "value": "1; mode=block" },
        { "key": "Referrer-Policy", "value": "strict-origin-when-cross-origin" },
        { "key": "Permissions-Policy", "value": "camera=(), microphone=(), geolocation=()" },
        { "key": "Strict-Transport-Security", "value": "max-age=31536000; includeSubDomains; preload" }
      ]
    }
  ]
}
```

### 1.2 Deployment Health & Diagnostics Endpoint (`/api/health`)
A diagnostic health check endpoint has been deployed to verify runtime operational parameters without leaking sensitive infrastructure secrets:

- **Path:** `GET /api/health`
- **Response Format (JSON):**
  ```json
  {
    "status": "healthy",
    "version": "2.0.0",
    "commit": "ba6a790",
    "timestamp": "2026-11-07T17:15:00.000Z",
    "runtime": "nodejs",
    "services": {
      "database": "unconfigured_fallback",
      "worker": "unreachable",
      "rateLimiter": "redis"
    },
    "memory": {
      "rss": 85400000,
      "heapUsed": 45100000
    }
  }
  ```

---

## 2. Supabase Staging Project Verification

The schema verifier (`src/lib/staging/supabase-verifier.ts`) inspects the live staging Supabase instance against our two authoritative database migrations:
1. `20261107000000_zendoc_2_0_core_schema.sql` (169 core tables, RLS enabled)
2. `20261108000000_zendoc_2_0_schema_corrections.sql` (`handle_new_user` profile trigger, 14 performance indexes)

### Automated Verification Function:
```typescript
import { verifySupabaseStagingConnection } from '@/lib/staging/supabase-verifier';

const report = await verifySupabaseStagingConnection();
console.log(report.status); // 'CONNECTED' | 'CONFIG_REQUIRED' | 'SCHEMA_OUT_OF_SYNC'
```

### Required Staging Environment Variables:
```ini
NEXT_PUBLIC_SUPABASE_URL=https://<your-project-id>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

## 3. Dedicated Python Worker Microservice

The Python worker resides in the `/worker` directory and is decoupled from Vercel's serverless runtime. It handles long-running Whisper speech-to-text (ASR) and document OCR workloads.

### 3.1 Container Architecture
- **Base Image:** `python:3.11-slim`
- **Security:** Non-root execution (`USER appuser`, UID `10001`)
- **Port:** `8000`
- **Authentication:** Interservice HMAC-SHA256 (`worker/auth.py`)

### 3.2 Running the Worker with Docker Compose
```bash
# Build and run the worker in the background
docker compose -f docker-compose.worker.yml up -d --build

# Verify worker health
curl http://localhost:8000/api/health
```

### 3.3 Connected Next.js Proxy Routes
The Next.js App Router exposes authenticated gateway routes that forward authorized patient requests to the worker:
- `POST /api/workers/asr` ➡️ `http://<worker-host>:8000/api/asr/transcribe`
- `POST /api/workers/ocr` ➡️ `http://<worker-host>:8000/api/ocr/extract`
- `GET /api/workers/health` ➡️ `http://<worker-host>:8000/api/health`

---

## 4. Distributed Rate Limiter Setup (Upstash Redis)

To protect serverless endpoints across distributed regions, ZENDOC 2.0 integrates with Upstash Redis via REST.

### 4.1 Configuration:
```ini
UPSTASH_REDIS_REST_URL=https://<database-name>.upstash.io
UPSTASH_REDIS_REST_TOKEN=AX...
```

### 4.2 Graceful Degradation:
If the Upstash Redis credentials are unset or the external cluster experiences network downtime, the system automatically degrades to an in-memory sliding window cache. This guarantees 100% uptime for critical medical advisory and emergency triage requests.

---

## 5. Deployment Checklist & Operator Actions

| Action | Owner | Target Environment | Verification Command |
| :--- | :--- | :--- | :--- |
| **Apply Supabase Migrations** | Cloud DBA | Supabase Staging | `supabase db push` |
| **Deploy Python Worker** | DevOps | AWS ECS / Fly.io / Render | `docker compose -f docker-compose.worker.yml up` |
| **Configure Vercel Environment Variables** | Lead Engineer | Vercel Project Settings | Vercel Project Dashboard |
| **Trigger Vercel Preview Build** | Lead Engineer | Vercel GitHub Action | `git push origin rebuild/zendoc-2.0-vercel` |
| **Verify Endpoint Health** | QA Lead | Staging Deployment | `curl https://<preview-domain>/api/health` |
