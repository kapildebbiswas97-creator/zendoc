# ZENDOC — AWS + Vercel Staging & Production Launch Checklist

> **Branch:** `feat/stitch-frontend-complete-20261013`  
> **Based on:** `hardening/aws-runtime-preflight-20261011` (PR #134)  
> **Author:** Frontend / DevOps Lead — ZENDOC  
> **Date:** 2026-10-13  
> **Status:** PRE-LAUNCH — owner approval required before production rollout

---

## 0. Pre-flight Constraints (MANDATORY)

- [ ] Owner has reviewed and approved this PR in GitHub — **DO NOT MERGE WITHOUT APPROVAL**
- [ ] No AWS resource changes (RDS, EC2, S3, IAM) have been made by this branch — confirm via `git diff origin/main -- terraform/`
- [ ] No production `DATABASE_URL` or secrets were logged, printed, or committed — confirm via `git log -p | grep -i password`

---

## 1. Environment Variables

### 1.1 Required Secrets (all environments)
| Variable | Description | Set in |
|---|---|---|
| `SECRET_KEY` | Flask session key — must be ≥64 random bytes | AWS SSM / Vercel Env |
| `DATABASE_URL` | PostgreSQL connection string (DSN format) | AWS SSM / Vercel Env |
| `UPLOAD_FOLDER` | Absolute path for patient file uploads | EC2 env / EFS mount |
| `FLASK_ENV` | `production` | Vercel / EC2 systemd |
| `REDIS_URL` | Cache/session backend (if applicable) | AWS SSM |
| `SENDGRID_API_KEY` | Transactional email | AWS SSM |
| `AWS_REGION` | e.g., `ap-south-1` | EC2 instance profile |

### 1.2 Rotate Before Launch
- [ ] `SECRET_KEY` — generate fresh: `python -c "import secrets; print(secrets.token_hex(64))"`
- [ ] `DATABASE_URL` password — rotate RDS master password, update SSM Parameter Store
- [ ] Any API keys present in `.env.example` — confirm they are placeholders only

### 1.3 Verify No Secrets in Repo
```bash
git log --all -p | grep -Ei "(password|secret_key|api_key|token)\s*=" | grep -v "placeholder\|example\|your_"
```
Expected: **zero results**

---

## 2. Docker Image (EC2 / ECS)

### 2.1 Non-root UID (already enforced in PR #134)
- [ ] `Dockerfile` uses `USER 10001` (non-root) — confirmed in PR #134 commit `e839ff4`
- [ ] Backup image uses `UID 10001` — confirmed in PR #134 commit `f629785`

### 2.2 Secret Exclusion (already tested)
- [ ] `.dockerignore` excludes `.env`, `*.pem`, `*.key`, `*.p12` — confirmed in PR #134
- [ ] CI gate `ci(secrets)` passes — test seeds synthetic private files and asserts they are absent from built image

### 2.3 Build & Tag
```bash
# Build production image (run on CI or dev machine — NOT production server)
docker build --no-cache -t zendoc:718532b -f Dockerfile .

# Verify non-root
docker run --rm --entrypoint id zendoc:718532b
# Expected: uid=10001

# Verify secrets excluded
docker run --rm zendoc:718532b ls /app/.env 2>&1
# Expected: "No such file"
```
- [ ] Image passes all assertions above
- [ ] Image tagged as `zendoc:<commit-sha>` and pushed to ECR:
  ```bash
  docker tag zendoc:718532b <ECR_URI>/zendoc:718532b
  docker push <ECR_URI>/zendoc:718532b
  ```

---

## 3. Database (RDS PostgreSQL)

### 3.1 Migration
- [ ] **No new database migrations** in this branch — frontend-only change
- [ ] Confirm with: `git diff origin/hardening/aws-runtime-preflight-20261011 -- migrations/`
  - Expected: no changes

### 3.2 Backup Verification
- [ ] RDS automated backups enabled (7-day retention minimum)
- [ ] Manual snapshot taken immediately before staging deploy:
  ```bash
  aws rds create-db-snapshot \
    --db-instance-identifier zendoc-prod \
    --db-snapshot-identifier zendoc-pre-stitch-frontend-718532b
  ```
- [ ] Snapshot status: `available` before proceeding

### 3.3 Connection
- [ ] `DATABASE_URL` points to RDS endpoint (not `localhost`)
- [ ] RDS security group allows inbound from EC2 security group only — **not** `0.0.0.0/0`

---

## 4. Vercel Gateway

### 4.1 Environment Variables in Vercel Dashboard
- [ ] `SECRET_KEY` set in Vercel → Settings → Environment Variables (Production + Preview)
- [ ] `DATABASE_URL` set (same RDS as EC2, or read replica)
- [ ] `FLASK_ENV=production` set
- [ ] `UPLOAD_FOLDER` set to the EFS/S3 path (not `/tmp` for persistent uploads)

### 4.2 Static Asset Delivery
- [ ] `static/stitch-refresh.css` is served — verify via `curl https://<vercel-domain>/static/stitch-refresh.css`
  - Expected: HTTP 200, content-type `text/css`
- [ ] `static/app.js` is served — verify `curl https://<vercel-domain>/static/app.js`
  - Expected: HTTP 200

### 4.3 Routing
- [ ] `vercel.json` (or `vercel.ts`) rewrites route all non-static paths to Flask
- [ ] Health endpoint responds: `curl https://<vercel-domain>/health`
  - Expected: `{"status": "ok"}` or equivalent

---

## 5. Static Assets & CDN

### 5.1 CSS/JS Integrity
- [ ] `static/stitch-refresh.css` — 992 lines, no build step required (plain CSS)
- [ ] `static/app.js` — includes WAI-ARIA tab keyboard navigation
- [ ] Google Fonts load in production (Inter, Plus Jakarta Sans) — verify no CSP blocking:
  ```
  Content-Security-Policy: font-src 'self' https://fonts.gstatic.com;
  style-src 'self' https://fonts.googleapis.com;
  ```

### 5.2 Cache Headers
- [ ] Static files have `Cache-Control: public, max-age=31536000, immutable` (via Flask / Vercel config)
- [ ] Version-busted via cache-buster query string or content hash if needed

---

## 6. CI Gates (Must All Pass Before Merge)

| Gate | Command | Expected |
|---|---|---|
| Python unit tests | `pytest --tb=short -q` | 0 failures |
| Asset presence | `pytest tests/test_stitch_refresh_assets.py` | 8 passed |
| Frontend integration | `pytest tests/test_frontend_integration_v1.py` | 10 passed |
| JS behavior | `node --test tests/js/app_behavior.test.cjs` | 6 passed |
| Milestone 1 | `pytest tests/test_milestone1.py` | 11 passed |
| Docker smoke | CI workflow `stitch-frontend-integration.yml` | pass |
| Security scan | `bandit -r app.py routes/ -ll` | no HIGH findings |
| Secrets scan | `trufflehog git file://.` | 0 verified secrets |

---

## 7. Post-Deploy Smoke Tests

Run these against the **staging** URL immediately after deploy:

```bash
STAGING=https://staging.zendoc.in   # replace with actual

# 1. Public homepage loads
curl -s -o /dev/null -w "%{http_code}" $STAGING/
# Expected: 200

# 2. Stitch CSS served
curl -s -o /dev/null -w "%{http_code}" $STAGING/static/stitch-refresh.css
# Expected: 200

# 3. Find Care page
curl -s -o /dev/null -w "%{http_code}" $STAGING/find-care
# Expected: 200

# 4. Auth: register page reachable
curl -s -o /dev/null -w "%{http_code}" $STAGING/register
# Expected: 200

# 5. Patient dashboard (must redirect to login — not 500)
curl -s -o /dev/null -w "%{http_code}" $STAGING/dashboard
# Expected: 302

# 6. Health check
curl -s $STAGING/health
# Expected: {"status":"ok"} or 200

# 7. No ABDM / mock hospital content on public pages
curl -s $STAGING/ | grep -i "Aster CMI\|NABH Golden\|JCI Accredited"
# Expected: zero matches
```
- [ ] All 7 smoke tests pass on staging

---

## 8. Accessibility (a11y) Verification

- [ ] WAVE or axe-core scan on `/` — 0 critical errors
- [ ] Tab key navigation works through landing page tabs (verified by `tests/js/app_behavior.test.cjs`)
- [ ] Mobile dock navigation visible and functional on 375px viewport
- [ ] Skip-to-content link present in `base.html`

---

## 9. PR Stacking Reconciliation

| PR | Branch | Target | Status | Action |
|---|---|---|---|---|
| #129 | `design/stitch-visual-refresh-20261011` | `launch/aws-ec2-vercel-launch-complete-20261010` | Superseded | **Close** — all changes absorbed into this PR |
| #130 | AWS launch branch | `main` | Likely merged | Verify closed |
| #131 | AWS launch branch | `main` | Likely merged | Verify closed |
| #132 | AWS launch branch | `main` | Likely merged | Verify closed |
| #133 | AWS hardening | `main` | Likely merged | Verify closed |
| #134 | `hardening/aws-runtime-preflight-20261011` | `main` | Open — base of this PR | Merge when ready |
| **This PR** | `feat/stitch-frontend-complete-20261013` | `hardening/aws-runtime-preflight-20261011` | **Draft** | Review → approve → merge |

**Recommended merge order:**
1. Approve + merge PR #134 (`hardening/aws-runtime-preflight-20261011`) to `main`
2. Rebase this PR onto `main` (or update base to `main` after #134 merges)
3. Approve + merge this PR to `main`
4. Close PR #129 with comment referencing this PR

---

## 10. Production Launch Authorization

- [ ] Owner (@kapildebbiswas97-creator) has reviewed this PR and approved
- [ ] All CI gates pass (see §6)
- [ ] All staging smoke tests pass (see §7)
- [ ] RDS snapshot taken (see §3.2)
- [ ] `SECRET_KEY` rotated (see §1.2)
- [ ] No mock/prototype hospital data visible on any public page
- [ ] Team notified of deployment window
- [ ] Rollback plan: `docker run zendoc:<previous-sha>` or Vercel "Promote" previous deployment

---

## 11. Rollback Procedure

If staging smoke tests fail after deploy:

```bash
# Option A: Vercel — instant rollback via dashboard
# Vercel Dashboard → Deployments → previous deployment → "Promote to Production"

# Option B: EC2 — revert container
docker stop zendoc-app
docker run -d --name zendoc-app <ECR_URI>/zendoc:<previous-sha>

# Option C: Git rollback (do NOT force-push main)
git revert 718532b -m 1
git push origin main
```

---

*This checklist was generated for commit `718532b` on branch `feat/stitch-frontend-complete-20261013`.*  
*Owner action required: Review PR → approve → execute launch steps above.*
