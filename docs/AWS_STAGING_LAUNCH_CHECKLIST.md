# ZENDOC — AWS EC2 + Vercel Staging / Public Beta Release Checklist

**Status: NOT DEPLOYED OR VERIFIED.** This checklist is for the frontend integration built on the AWS-hardened release candidate. It does not authorize a merge, cloud expenditure or public launch. Read the authoritative `docs/AWS_EC2_VERCEL_LAUNCH.md` and `deploy/aws/README.md` before any operator action.

## Verified implementation topology

```text
Browser
  -> existing Vercel public gateway (vercel.ts)
  -> ZENDOC_ORIGIN_URL (verified HTTPS AWS EC2 hostname)
  -> Caddy (valid TLS; gateway token required except public health/readiness)
  -> Gunicorn / Flask app + separate ops-worker
  -> PostgreSQL 16 Docker service (internal-only network)
```

**Do not copy an RDS/ECR/ECS deployment playbook into this release.** The actual `deploy/aws/compose.yaml` includes a private `postgres:16-bookworm` database and Docker named volumes on EC2, not an AWS RDS database. RDS or ECR is an optional future architecture decision that requires a separate design, budget and reviewed change.

## 1. Source code and approval

- [ ] Verify reviewed HEAD and every stacked PR (#130–#134 and frontend PR #136) using GitHub, not old copied commit prefixes.
- [ ] Review the original AI Studio/Stitch exports and final screenshots using **synthetic accounts only**; account/profile pages and permissions remain real.
- [ ] Confirm prior PR #129 is fully represented before closing it. Do not separately merge superseded frontend code.
- [ ] Run final code review and obtain explicit owner approval **before** a merge or live deploy.
- [ ] Preserve old Render/OCI database backups, Vercel projects and branches until migration/rollback is proven.

## 2. Automated and browser evidence

- [ ] Run the `Stitch Frontend Integration` workflow at the **exact latest integration commit**. It must execute both Python test files and Node tests.
- [ ] Run the `Stacked Release Full Regression` workflow at the same SHA: all SQLite tests plus PostgreSQL 16 migration/readiness and hospital schema smoke.
- [ ] Run the AWS Runtime Preflight / production security gates on the final combined revision, including non-root runtime and Docker secret-exclusion checks.
- [ ] Record passing workflow URLs, test totals and exact SHA; a prior passing parent is not proof that a new child SHA passes.
- [ ] Inspect actual rendered screenshots at 375, 768 and 1440 pixels, keyboard accessibility, real protected journeys and visual differences from approved designs. Capturing screenshots alone is not visual acceptance.
- [ ] Test landing page, login, patient dashboard, Find Care, provider detail, appointments, Health Memory, pharmacy, Agent OS, upload/download authorization and role isolation in an **authorized staging session**.

## 3. AWS owner-only prerequisites

- [ ] Review current EC2, gp3 EBS, public IPv4, data transfer, backup and DNS charges in the **actual AWS account and region**; set an AWS Budget alert. Do not assume a $0 bill.
- [ ] Only after explicit approval, provision a suitably sized Ubuntu EC2 instance with durable encrypted EBS. A 1 GB instance may be inadequate for PostgreSQL + Flask + worker + Caddy; consult the main launch runbook before selecting the instance.
- [ ] Restrict SSH TCP 22 to a trusted address; expose only necessary Caddy HTTPS/HTTP TCP 443/80. Do **not** open PostgreSQL port 5432 to the Internet. TURN ports only if the optional reviewed realtime profile is enabled.
- [ ] Configure an origin hostname owned by the user, DNS pointing to the EC2 instance, and valid Caddy-managed TLS.
- [ ] Install Docker Engine and Compose from reviewed vendor instructions; work from the **exact approved commit**, not a moving development branch.

## 4. Secrets — AWS origin only

Copy `deploy/aws/.env.example` to **private** `deploy/aws/.env` with permissions 0600. Fill the actual documented keys:
- `ZENDOC_DOMAIN` (EC2 origin hostname), `ZENDOC_TLS_EMAIL`, `ZENDOC_GATEWAY_TOKEN` (unique random gateway-only secret)
- `ZENDOC_SECRET_KEY`, `ZENDOC_ADMIN_EMAIL`, `ZENDOC_ADMIN_PASSWORD`
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `ZENDOC_PUBLIC_BASE_URL` (existing Vercel public URL), `ZENDOC_GIT_COMMIT` (full approved SHA)

Generate different random secrets; do not paste, commit, print, or upload them in logs or reports. Avoid dumping repository history or environment contents into CI artifacts. Use least privilege, private SSH keys and approved storage for backup secrets.

Leave `ZENDOC_PERSISTENCE_VERIFIED`, `ZENDOC_BACKUP_VERIFIED`, `ZENDOC_STORAGE_VERIFIED`, `ZENDOC_EMAIL_VERIFIED`, `ZENDOC_PUBLIC_RELEASE_REQUIRED` and `ZENDOC_POSTGRES_RESTORE_ALLOW_RESET` at false until the respective **actual** conditions are demonstrated.

Optional email, maps, S3 and AI providers are not required to be silently enabled merely to make a release look complete.

## 5. PostgreSQL 16, backup and restore

- [ ] Validate the old Render data source and archive with checksums; if records exist, make a reviewed migration plan and verify patient identity and record parity. Do not fabricate source data.
- [ ] Confirm `postgres_data`, `uploads`, `caddy_data`, `caddy_config` Docker named volumes and encrypted underlying EBS.
- [ ] Prepare `/var/backups/zendoc` with correct ownership for the **unprivileged backup container UID 10001** and restrictive permissions. Never copy a production backup to GitHub.
- [ ] Run an actual encrypted **off-instance** PostgreSQL 16 backup and test restore on a disposable target before declaring the backup gate verified.
- [ ] Confirm transactions/data survive a web process restart and full EC2 compose restart. Do not falsely mark persistence or backup flags true.

## 6. Validate AWS origin before Vercel cutover

From the reviewed project checkout:

```bash
cd deploy/aws
sudo docker compose --env-file .env -f compose.yaml config --quiet
sudo docker compose --env-file .env -f compose.yaml up -d --build db web ops-worker caddy
sudo docker compose --env-file .env -f compose.yaml ps
sudo docker compose --env-file .env -f compose.yaml logs --tail=100 web caddy
```

Check **real** endpoints on the actual origin:

```bash
curl -fsS https://YOUR_AWS_ORIGIN/api/v1/health
curl -fsS https://YOUR_AWS_ORIGIN/api/v1/ready
```

- [ ] Confirm both health responses, deploy SHA, `aws_ec2` platform and PostgreSQL readiness/persistence using `scripts/verify_deployment.py` as directed by the main runbook.
- [ ] Direct requests to ordinary backend app pages **should return 403 without** `X-Zendoc-Gateway-Token`. Do not weaken Caddy authorization to make an origin browser check pass.
- [ ] Do not publish internal URLs, infrastructure credentials or the gateway token.

## 7. Existing Vercel gateway (not a Flask runtime)

On the **existing correct Vercel project**, configure in protected project settings for the appropriate environments:

```text
ZENDOC_ORIGIN_URL=https://YOUR_VERIFIED_AWS_ORIGIN
ZENDOC_GATEWAY_TOKEN=THE_SAME_PRIVATE_VALUE_CONFIGURED_ON_CADDY
```

**Do not put `DATABASE_URL`, `POSTGRES_PASSWORD`, `ZENDOC_SECRET_KEY`, patient uploads or admin passwords on Vercel.** The inspected `vercel.ts` is a gateway rewrite only; the actual application and database run on EC2.

- [ ] Preserve `git.deploymentEnabled: false` until reviewed origin, production gates, persistence and credentials are confirmed.
- [ ] When authorized, update and redeploy the Vercel gateway through a **reviewed change**; setting environment variables alone will not repair an old failed deployment.
- [ ] Verify public URL and static assets (`/static/stitch-refresh.css`, `/static/app.js`), expected protected routes, cookies, uploads, user permissions and authenticated flows.
- [ ] Verify public health endpoints `/api/v1/health` and `/api/v1/ready`. Do **not** substitute guessed `/health`, `/find-care`, or `/staging` paths for real routes.

## 8. Release / rollback decision

- [ ] Approved exact release SHA and all current-head CI gates green.
- [ ] Real staging mobile/desktop and role-specific smoke tests green.
- [ ] TLS, DNS, database persistence, backups, off-host restore, monitoring and alerts evidenced.
- [ ] Final approved public beta scope excludes unverified payments, autonomous prescribing, official provider integrations and claimed medical certifications.
- [ ] Owner explicitly authorizes production release.

**Rollback:** record previous known-good Git SHA, images, Compose configuration, environment, Vercel deployment and a tested database restore plan. Revert or redeploy the prior **reviewed Compose stack and Vercel deployment**, preserving volumes and migrations. Do **not** blindly use standalone `docker stop/run` commands or `git revert -m 1` on an arbitrary commit; do not reset production healthcare data as an emergency shortcut.

Until all applicable gates are proven: **STATUS = REVIEW / STAGING BLOCKED, NOT LIVE VERIFIED**.
