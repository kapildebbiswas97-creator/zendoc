# ZENDOC 2.0 — MONITORING, RELIABILITY & INCIDENT RUNBOOK
**Structured Telemetry, HIPAA / DPDP Privacy Controls & Operational Recovery Procedures**

- **Project:** ZENDOC 2.0 — AI-Powered Healthcare Coordination Platform
- **Scope:** Staging & Production Operational Readiness
- **Applicable Regulations:** HIPAA Security & Privacy Rules, India DPDP Act 2023

---

## 1. Structured Logging Architecture

ZENDOC 2.0 uses structured JSON logging (`src/lib/monitoring/logger.ts`) across all App Router routes and backend workers.

### 1.1 Log Format Specification
Each log line is emitted as a single-line JSON string to standard output, compatible with Datadog, AWS CloudWatch, Logflare, and Vercel Log Drains:

```json
{
  "timestamp": "2026-11-07T17:15:30.123Z",
  "level": "INFO",
  "service": "zendoc-app",
  "message": "Operation completed: record_download_signature",
  "duration_ms": 42,
  "metadata": {
    "user_id": "usr_78a1bc92",
    "record_id": "rec_09f3d1"
  }
}
```

### 1.2 Automated PHI / PII Redaction
In strict adherence to medical privacy standards, the logging pipeline passes all messages and string metadata through automated redaction regexes before output:

| Data Type | Detection Pattern | Redaction Token |
| :--- | :--- | :--- |
| **Email Addresses** | `[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}` | `[EMAIL_REDACTED]` |
| **Phone Numbers** | 10-digit mobile, international formats (`+91...`, `(555)...`) | `[PHONE_REDACTED]` |
| **Bearer / JWT Tokens** | `Bearer [A-Za-z0-9\-._~+/]+=*` | `Bearer [TOKEN_REDACTED]` |
| **Passwords & Secrets** | `password=...`, `"secret": "..."` | `[REDACTED]` |

---

## 2. Latency Thresholds & Service Level Objectives (SLOs)

All critical clinical paths are monitored using `startOperationTimer()` to track latency percentiles:

| Endpoint / Operation | Target p50 | Target p95 | Hard SLA Threshold | Alert Trigger |
| :--- | :---: | :---: | :---: | :--- |
| **Emergency Triage Check** | < 5 ms | < 15 ms | 50 ms | Alert if p95 > 25 ms over 5m window |
| **Health Check (`/api/health`)** | < 20 ms | < 50 ms | 150 ms | Alert if failure rate > 1% |
| **AI Advisory Response (`/api/ai/chat`)** | < 450 ms | < 1200 ms | 2500 ms | Alert if p95 > 1800 ms over 5m |
| **Document Upload & Hash (`/api/records/upload`)** | < 150 ms | < 500 ms | 1500 ms | Alert if error rate > 2% |
| **Database Server Actions (Vitals, Appointments)** | < 60 ms | < 180 ms | 500 ms | Alert if p95 > 300 ms over 5m |

---

## 3. Incident Response Runbooks

### Runbook A: Python Worker Service Down or Unreachable
- **Symptoms:** `/api/health` reports `services.worker = "unreachable"`. Calls to `/api/workers/asr` or `/api/workers/ocr` return HTTP 502/503.
- **Impact:** Real-time speech transcription and OCR extraction unavailable. UI falls back to manual text entry. Core patient records and emergency triage are unaffected.
- **Recovery Steps:**
  1. Inspect container logs:
     ```bash
     docker compose -f docker-compose.worker.yml logs -f worker
     ```
  2. Verify network connectivity between Next.js and worker:
     ```bash
     curl -I http://<worker-host>:8000/api/health
     ```
  3. Check memory exhaustion (OOM) on host: Whisper models require at least 1.5GB RAM.
  4. Restart container:
     ```bash
     docker compose -f docker-compose.worker.yml restart worker
     ```

### Runbook B: Rate Limiter Saturation or Redis Partition
- **Symptoms:** High rate of HTTP 429 Too Many Requests, or Redis connection errors in Next.js logs.
- **Impact:** Malicious abuse attempts are blocked. If Redis is down, the built-in failover activates automatically.
- **Recovery Steps:**
  1. Check Redis failover status: Verify in logs that `[RateLimiter] Distributed store unreachable, degrading to in-memory fallback` is firing cleanly.
  2. If legitimate traffic is being blocked, increase sliding window quota in `src/lib/security/rate-limiter.ts` (e.g. from 20 req/min to 60 req/min).
  3. Inspect Upstash Redis dashboard for credit exhaustion or bandwidth limits.

### Runbook C: Database Connection Pool Exhaustion (PostgREST / Supabase)
- **Symptoms:** Database queries take > 1000ms; HTTP 500 errors on server actions.
- **Impact:** Profile loading, vitals logging, and appointment scheduling delayed.
- **Recovery Steps:**
  1. Open Supabase Dashboard ➡️ Database ➡️ Connection Pooling (PgBouncer / Supavisor).
  2. Verify pool mode is set to `Transaction` mode, not `Session` mode, for serverless compatibility.
  3. Ensure max client connections does not exceed PostgreSQL tier limit.
  4. Inspect active locks:
     ```sql
     SELECT pid, age(clock_timestamp(), query_start), usename, query 
     FROM pg_stat_activity 
     WHERE state != 'idle' AND query NOT ILIKE '%pg_stat_activity%' 
     ORDER BY age DESC;
     ```
  5. Terminate lingering hung transactions if necessary:
     ```sql
     SELECT pg_terminate_backend(<pid>);
     ```
