# ZENDOC 2.0 — OPERATIONAL RECOVERY & ROLLBACK RUNBOOK
**Disaster Recovery, High-Availability Fallback & Emergency Rollback Runbooks**

- **Project:** ZENDOC 2.0 — AI-Powered Healthcare Coordination Platform
- **Scope:** Staging & Production Incident Remediation
- **Lead Operations Role:** Site Reliability Engineer & Principal Cloud Architect

---

## 1. Fast Rollback Procedure (Vercel & Git)

If a breaking defect or regression is detected on the live staging preview:

### 1.1 Immediate Vercel Instant Rollback
1. Open [vercel.com](https://vercel.com) ➡️ Select `zendoc` project.
2. Navigate to **Deployments**.
3. Locate the previous known-good deployment (Commit `5b1000f` or `ba6a790`).
4. Click the three dots `...` ➡️ **Promote to Production / Instant Rollback**.
5. Traffic routes to the prior deployment in < 5 seconds without triggering a rebuild.

### 1.2 Git Branch Rollback
To revert commits on the rebuild branch:
```bash
# Checkout rebuild branch
git checkout rebuild/zendoc-2.0-vercel

# Create a clean revert commit of the faulty change
git revert <faulty-commit-sha> --no-edit

# Push to trigger clean automated preview build
git push origin rebuild/zendoc-2.0-vercel
```

---

## 2. Subsystem Failure Recovery Runbooks

### Runbook 1: Supabase / PostgreSQL Unavailable
- **Symptoms:** Database queries fail with HTTP 500; `/api/health` indicates `supabase_database: "STANDBY_CONFIGURATION_PENDING"` or timeout.
- **Immediate Mitigation:**
  - The UI automatically falls back to synthetic clinical demo data, allowing navigation without white-screen crashes.
  - Check Supabase status page at [status.supabase.com](https://status.supabase.com).
- **Recovery Actions:**
  1. Check PostgreSQL pooler status in Supabase Dashboard (Database ➡️ Connection Pooling).
  2. Switch from direct connection (port 5432) to PgBouncer / Supavisor pooler (port 6543) if connection ceiling was breached.
  3. Check PostgreSQL slow query logs for table locks.

### Runbook 2: Distributed Redis / Upstash Unavailable
- **Symptoms:** Logs show `[RateLimiter] Distributed store unreachable, degrading to in-memory fallback`.
- **System Behavior:**
  - Automatic circuit-breaker triggers instantaneously.
  - System falls back to in-memory sliding window rate limiting.
  - Zero requests are dropped; patient care and emergency triage continue uninterrupted.
- **Recovery Actions:**
  1. Inspect Upstash console for bandwidth exhaustion or quota limits.
  2. Verify REST URL and Token in Vercel environment variables.

### Runbook 3: Python Worker Service Down
- **Symptoms:** `/api/workers/health` returns HTTP 502/503. Audio transcription (ASR) and document OCR fail.
- **System Behavior:**
  - Web UI displays friendly message: *"Specialized speech processing is temporarily offline. Please enter text manually."*
  - Core patient records, appointments, and emergency triage are 100% unaffected.
- **Recovery Actions:**
  1. Inspect container logs:
     ```bash
     docker compose -f docker-compose.worker.yml logs -f worker
     ```
  2. Check host RAM: Whisper models require at least 1.5 GB memory.
  3. Restart worker container:
     ```bash
     docker compose -f docker-compose.worker.yml restart worker
     ```

### Runbook 4: Unexpected PHI Exposure Incident
- **Symptoms:** Unmasked patient data detected in application logs or external analytics.
- **Immediate Containment:**
  1. Purge external log drains (Datadog, Papertrail, Vercel Log Drains).
  2. Inspect regex patterns in `src/lib/monitoring/logger.ts` and add missing entity patterns.
  3. Rotate exposed session cookies or auth tokens in Supabase Dashboard.
  4. File security incident report following HIPAA/DPDP protocol.

---

## 3. Database Backup & Disaster Recovery Protocol

1. **Daily Automated Backups:** Supabase maintains daily automated point-in-time recovery (PITR) on Pro tiers, and daily snapshots on Free tiers.
2. **Schema State Restoration:** If schema corruption occurs, apply the migration sequence in order:
   ```bash
   # Schema reset
   supabase db reset
   ```
3. **Safe Storage Restoration:** The `medical-records` bucket maintains object versioning; deleted records can be restored from the storage history log.
