# Launch ZENDOC on AWS EC2 with the existing Vercel project

**Status:** This runbook prepares the repository; it does not create resources in an AWS account. Vercel's latest `kapildebbiswas97-creator-zendoc` deployment previously failed because `ZENDOC_ORIGIN_URL` was not configured. Do not create a third Vercel project, do not use a dummy HTTPS origin, and do not claim the site is live until the checks below pass.

## Architecture

Browser → Vercel public gateway → `https://YOUR_AWS_ORIGIN` → EC2 Caddy HTTPS → Flask + operations worker → PostgreSQL 16 (`postgres:16-bookworm` on private Docker network).

Initial AWS backend: one Ubuntu EC2 VM with Docker Compose and persistent gp3 EBS. Optional future upgrade: managed PostgreSQL on AWS RDS and uploaded-file storage on S3. This **single VM is not HA**; maintain encrypted off-instance backups.

## 1. Create the AWS EC2 instance

In the [EC2 Console](https://console.aws.amazon.com/ec2/), choose an appropriate region and launch an **Ubuntu 24.04 LTS x86-64** AMI.

### Hardware Sizing, AWS Free Tier Realities & Low-Cost Alternatives
- **AWS Free Tier Reality:** AWS Free Tier includes 750 hours/month of a `t2.micro` or `t3.micro` instance (1 vCPU, 1 GB RAM). Running PostgreSQL 16 (`postgres:16-bookworm`), Flask web backend (Gunicorn), operations worker, and Caddy concurrently within 1 GB RAM creates severe memory pressure.
  > [!WARNING]
  > If using a 1 GB Free Tier instance (`t2.micro` / `t3.micro`), you **MUST** configure a 2 GB to 4 GB swapfile to avoid Out-Of-Memory (OOM) killer terminations:
  > ```bash
  > sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
  > echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
  > ```
  > Set `WEB_CONCURRENCY=1` to limit worker memory usage.
- **AWS Public IPv4 Cost Notice:** Since February 2024, AWS charges $0.005/hour (~$3.65/month) for all public IPv4 addresses, even on Free Tier instances. An EC2 instance is therefore never $0.00/month unless configured IPv6-only.
- **Recommended Low-Cost Staging/Production Tiers (Non-Free Tier):**
  - **`t3.small` (Recommended standard):** 2 vCPU, 2 GB RAM. Compute (~$15.20/mo) + public IPv4 (~$3.65/mo) = **~$18.85/month**. Provides comfortable memory headroom without memory thrashing.
  - **`t4g.small` (AWS Graviton2 ARM64 alternative):** 2 vCPU, 2 GB RAM. Compute (~$12.30/mo) + public IPv4 (~$3.65/mo) = **~$15.95/month**. Requires ARM-compatible container builds.
- **Storage:** Start with at least 30 GB encrypted gp3 EBS (30 GB gp3 is included in AWS Free Tier) and enable IMDSv2. Configure an AWS Budget alert ($20/month) before provisioning.

Configure a public subnet with internet access; security group inbound rules:
- TCP **22** only from your trusted IP for SSH
- TCP **80** and **443** publicly for Caddy HTTPS
- **Never** open PostgreSQL TCP **5432**
- TURN ports only if the optional realtime profile is deliberately deployed later

Use a stable public IP plan and an origin hostname you control (e.g., `origin.example.com`) whose DNS A record resolves to that IP. The origin hostname is not the Vercel-facing website URL. Using a domain isn't required for downloading the repository, but a resolvable TLS hostname is needed for the hardened gateway.

## 2. Log in and prepare Docker

From Windows PowerShell:

```powershell
ssh -i "C:\path\to\ec2-key.pem" ubuntu@AWS_PUBLIC_IP
```

On Ubuntu, use the [official Docker Ubuntu guide](https://docs.docker.com/engine/install/ubuntu/) to install Docker Engine and the Docker Compose plugin, then:

```bash
sudo apt-get update
sudo apt-get install -y git curl
git clone https://github.com/kapildebbiswas97-creator/zendoc.git
cd zendoc
git checkout main
git pull --ff-only
git rev-parse HEAD
```

Only deploy a reviewed commit with a passing **ZENDOC Production Gate**, after the AWS pull request is merged. Do not deploy a branch with unknown test results to a production patient environment.

## 3. Configure backend environment safely

```bash
cp deploy/aws/.env.example deploy/aws/.env
chmod 600 deploy/aws/.env
nano deploy/aws/.env
```

Generate a **different** long random value for each secret with `openssl rand -hex 32`. Fill `ZENDOC_DOMAIN` (AWS HTTPS origin hostname), `ZENDOC_TLS_EMAIL`, `ZENDOC_GATEWAY_TOKEN`, `POSTGRES_PASSWORD`, `ZENDOC_SECRET_KEY`, `ZENDOC_ADMIN_EMAIL`, `ZENDOC_ADMIN_PASSWORD`, `ZENDOC_GIT_COMMIT` (exact reviewed SHA), and `ZENDOC_PUBLIC_BASE_URL` (the existing Vercel browser-facing production URL from **Settings → Domains**).

The password of an existing admin account is not reset simply by changing the environment variable. Never commit the filled `.env`, and never paste credentials or database URLs into chat or code.

Leave **all** verification/release flags **false** until proven: `ZENDOC_PERSISTENCE_VERIFIED`, `ZENDOC_BACKUP_VERIFIED`, `ZENDOC_STORAGE_VERIFIED`, `ZENDOC_EMAIL_VERIFIED`, `ZENDOC_PUBLIC_RELEASE_REQUIRED`, and `ZENDOC_POSTGRES_RESTORE_ALLOW_RESET`.

## 4. Preserve existing Render records

If an old Render database holds accounts or healthcare records, it must be migrated deliberately, not silently replaced with a blank DB. Preserve a verified `zendoc-postgres-*.dump` with `.sha256` and `.json` sidecars. If no archive exists and Render is suspended, first attempt a data recovery/export; do not fabricate migrated data.

Create a restricted backup staging folder, then start the *empty* AWS target PostgreSQL first:

```bash
sudo install -d -m 700 /var/backups/zendoc
cd deploy/aws
sudo docker compose --env-file .env -f compose.yaml up -d db
```

The guarded backup/restore tooling (`scripts/postgres_backup.py`, `scripts/verify_postgres_backup.py`, `scripts/postgres_restore.py`) from the existing PostgreSQL migration runbook can be used **only after the source archive and destination are validated**; replace OCI paths with `deploy/aws`. A restore refuses populated targets while reset is false. Verify patient/owner IDs, role assignments, record counts and foreign keys. If no previous data exists, record that fact explicitly before beginning a synthetic-only pilot.

## 5. Start and verify the AWS origin

After any required restore:

```bash
cd ~/zendoc/deploy/aws
sudo docker compose --env-file .env -f compose.yaml config --quiet
sudo docker compose --env-file .env -f compose.yaml up -d --build db web ops-worker caddy
sudo docker compose --env-file .env -f compose.yaml ps
sudo docker compose --env-file .env -f compose.yaml logs --tail=100 web caddy
curl -fsS https://YOUR_AWS_ORIGIN/api/v1/health
curl -fsS https://YOUR_AWS_ORIGIN/api/v1/ready
```

Verify using the actual reviewed source commit, not the historical main SHA:

```bash
cd ~/zendoc
python3 scripts/verify_deployment.py https://YOUR_AWS_ORIGIN --expected-commit YOUR_REVIEWED_40_CHAR_SHA --require-platform aws_ec2 --require-engine postgresql
```

Direct backend app pages returning HTTP 403 without the gateway token is **expected**. Only `/api/v1/health` and `/api/v1/ready` may be called directly without it.

## 6. Connect to the existing Vercel project

Project: **kapildebbiswas97-creator-zendoc** in team **kapildebbiswas97-creators-projects**. Do not deploy to older **zendoc**. Under **Settings → Environment Variables**, set for Preview and Production:

```text
ZENDOC_ORIGIN_URL=https://YOUR_AWS_ORIGIN
ZENDOC_GATEWAY_TOKEN=THE_SAME_GATEWAY_ONLY_SECRET_USED_ON_EC2
```

Vercel must not contain PostgreSQL credentials, Flask admin passwords, AI/service provider secrets or `DATABASE_URL`. The existing `vercel.ts` intentionally disables automatic Git deployments while the origin is not verified. When AWS health, TLS, data parity and persistence are proven, remove `git.deploymentEnabled: false` **through a reviewed change**, run the Production Gate, then create a *new* production deployment. Adding environment variables does not heal historical ERROR builds.

Vercel team SSO protection on the new project may still restrict public browsing after a successful deploy. Keep access protected during staging; only change protection once a safe public beta is authorized.

## 7. Before real public healthcare onboarding

Test login/logout, sessions, finder, private Health Memory, messages, upload recovery, PWA and user isolation via Vercel. Confirm the same synthetic data persists after restart and a same-commit redeploy. Perform and verify encrypted off-EC2 backups plus scratch restore drills; configure durable object storage and transactional email. Do not enable public release flags until their required evidence passes.

Do **not** delete OCI configuration, old Vercel projects, Render records or backups during this transition; cleanup is a separate step **after** AWS is verified.
