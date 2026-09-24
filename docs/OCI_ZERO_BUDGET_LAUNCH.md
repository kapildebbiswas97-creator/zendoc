# OCI zero-budget beta deployment

This runbook describes a self-managed, PostgreSQL-compatible launch path for ZENDOC on an Oracle Cloud Infrastructure compute VM. It intentionally does not port ZENDOC to Oracle Database. ZENDOC's tested production database boundary is PostgreSQL, so the zero-budget path keeps that engine and moves the application and database together onto one VM.

This is an early-stage cost-control option, not a claim of managed HA, managed PITR, regulatory certification, or permanent free capacity. Oracle account eligibility, free capacity and service limits remain external operator facts and must be checked in the OCI console.

## Architecture

Browser -> Vercel public URL -> HTTPS OCI origin -> Caddy on 80/443 -> ZENDOC web container -> PostgreSQL 16 on an internal-only Docker network. PostgreSQL is never exposed to Vercel.

PostgreSQL has no published host port. Do not open TCP/5432 in OCI security lists, NSGs, or the VM firewall.

Persistent local state includes the PostgreSQL Docker volume, an uploads volume, Caddy TLS state, and /var/backups/zendoc as a local backup staging area. Off-instance copies are still required; a VM-local volume is not disaster recovery.

## 1. Harden the VM

Use a supported Linux image and install current Docker Engine plus Docker Compose from trusted packages. OCI network rules should allow SSH only from a trusted operator source where practical, public 80/443 for HTTPS, and no public 5432. Use SSH keys rather than enabling password SSH for convenience.

## 2. Point the domain

Create an A record for the chosen ZENDOC domain pointing to the VM public IPv4 address. Add AAAA only when IPv6 is configured correctly. Do not begin public onboarding until HTTPS resolves and the release checks pass.

## 3. Prepare ZENDOC

Clone the repository and deploy only a reviewed main commit:

    git clone https://github.com/kapildebbiswas97-creator/zendoc.git
    cd zendoc
    git checkout main
    git pull --ff-only
    git rev-parse HEAD

Create the private environment file:

    cp deploy/oci/.env.example deploy/oci/.env
    chmod 600 deploy/oci/.env

Generate separate strong random secrets. Hex is recommended for POSTGRES_PASSWORD because the Compose database URL interpolates it directly:

    openssl rand -hex 32

Set ZENDOC_DOMAIN to the OCI origin hostname, ZENDOC_PUBLIC_BASE_URL to the Vercel production URL, plus ZENDOC_TLS_EMAIL, ZENDOC_GIT_COMMIT, POSTGRES_PASSWORD, ZENDOC_SECRET_KEY, ZENDOC_ADMIN_EMAIL and ZENDOC_ADMIN_PASSWORD. Keep ZENDOC_PERSISTENCE_VERIFIED, ZENDOC_BACKUP_VERIFIED and ZENDOC_PUBLIC_RELEASE_REQUIRED false initially. Never flip verification flags only to satisfy startup checks.

## 4. Start PostgreSQL, ZENDOC and HTTPS

From deploy/oci:

    docker compose --env-file .env -f compose.yaml config --quiet
    docker compose --env-file .env -f compose.yaml up -d --build
    docker compose --env-file .env -f compose.yaml ps

Check:

    curl -fsS https://YOUR_DOMAIN/api/v1/health
    curl -fsS https://YOUR_DOMAIN/api/v1/ready

Readiness must truthfully report PostgreSQL, a reachable database, ready migrations/schema, deployment.platform=oci and the expected Git commit.

Automated verification:

    python scripts/verify_deployment.py https://YOUR_DOMAIN --expected-commit COMMIT_SHA --require-platform oci --require-engine postgresql

Do not add --require-persistence-verified until the manual persistence test has actually passed.

## 5. Migrate the current database before the trial expires

Freeze writes during cutover. For a current PostgreSQL source, set DATABASE_URL only in the operator shell; never paste it into Git, logs, screenshots or command-line arguments.

    export DATABASE_URL='postgresql://...'
    python scripts/postgres_backup.py --output-dir ./migration-backup
    unset DATABASE_URL

Verify checksum and archive structure:

    python scripts/verify_postgres_backup.py ./migration-backup/zendoc-postgres-YYYYMMDDTHHMMSSZ.dump

A checksum/catalog check is not a restore drill. Restore into an isolated PostgreSQL target first, preserve IDs and foreign keys, reset sequences where required, run idempotent schema initialization/migrations, and compare table counts plus representative owner, user, role, provider, appointment, Health Memory, message, notification and audit records. Do not delete the source database after first success.

## 6. Prove persistence

Use synthetic accounts/data. Create a synthetic patient and representative records, restart containers, verify the same ID/data, rebuild/redeploy the same reviewed commit, verify again, then test a synthetic provider and patient/provider isolation. Confirm exactly one configured owner. Only after this passes may ZENDOC_PERSISTENCE_VERIFIED=true be set.

## 7. Create and verify backups

The backup profile receives only the database connection it needs; it does not inherit ZENDOC admin, SMTP, model-provider or other application secrets.

    sudo install -d -m 700 /var/backups/zendoc
    cd deploy/oci
    docker compose --env-file .env -f compose.yaml --profile ops run --rm backup

The tool creates a PostgreSQL custom-format dump, SHA-256 sidecar and non-secret JSON manifest.

Verify an archive without modifying a database:

    docker compose --env-file .env -f compose.yaml --profile ops run --rm --entrypoint python backup /opt/zendoc/scripts/verify_postgres_backup.py /backups/zendoc-postgres-YYYYMMDDTHHMMSSZ.dump

Then copy an encrypted backup off the VM to an independent durable location such as OCI Object Storage. Keep the encryption key outside the VM and repository.

A real backup verification requires local archive/checksum verification, a successful encrypted off-instance copy, downloading that copy, restoring into an isolated temporary PostgreSQL database, and comparing row counts plus representative records.

ZENDOC already includes a guarded destructive-to-scratch restore drill. Point it only at an isolated scratch database whose name contains `verify` or `scratch`:

    export DATABASE_URL='postgresql://SOURCE...'
    export ZENDOC_BACKUP_VERIFY_DATABASE_URL='postgresql://SCRATCH.../zendoc_verify'
    export ZENDOC_BACKUP_VERIFY_ALLOW_RESET=true
    python scripts/verify_postgres_backup_restore.py
    unset DATABASE_URL ZENDOC_BACKUP_VERIFY_DATABASE_URL ZENDOC_BACKUP_VERIFY_ALLOW_RESET

The script refuses to reset the source database, requires the explicit reset opt-in, compares fixed core-table counts after restore, and removes the scratch schema again by default. Database utility subprocesses receive only a minimal libpq environment rather than unrelated ZENDOC secrets.

Only after the off-instance recovery path and restore drill pass should `ZENDOC_BACKUP_VERIFIED=true` be set.

## 8. Uploaded files

Database durability does not preserve uploaded report/media bytes. Before real public onboarding, configure ZENDOC's existing S3-compatible storage boundary against a real durable object store, verify write/read/delete behavior, and only then set ZENDOC_STORAGE_PROVIDER=s3_compatible and ZENDOC_STORAGE_VERIFIED=true. Keep object-storage credentials outside Git.

## 9. Email and public release

Real public registration also needs working email verification. Configure and verify the existing SMTP boundary before setting ZENDOC_EMAIL_PROVIDER=smtp and ZENDOC_EMAIL_VERIFIED=true.

When persistence, backups, durable object storage, email, HTTPS and the remaining public-release requirements are genuinely verified, set ZENDOC_PUBLIC_RELEASE_REQUIRED=true. If startup then fails, fix the missing integration; do not weaken the gate.

## 10. PWA/mobile launch

ZENDOC already has a web manifest route, service worker and install-prompt logic. Authenticated HTML and API responses stay network-only so private health data is not cached by the service worker. Test installability on Android Chrome, desktop Chrome/Edge and a low-bandwidth mobile-network session. The zero-cost first launch can therefore be the secure web app plus installable PWA; native-store distribution can follow later.

## 11. Release verification

For each reviewed deployment, record the exact Git commit in deploy/oci/.env, rebuild, then run scripts/verify_deployment.py against that exact commit. Never claim a release is deployed merely because GitHub merged it.

## 12. Failure and rollback

Keep the previous database backup, stop writes before restoring, never operate two writable production databases during rollback, clear ZENDOC_PERSISTENCE_VERIFIED after changing database target/restore point until persistence is re-proven, and clear ZENDOC_BACKUP_VERIFIED if the backup destination/process changes until a new restore drill succeeds.

If an OCI VM is reclaimed or unavailable, restore from the off-instance backup to a replacement PostgreSQL target rather than assuming local disk state survived.

This path is intentionally conservative: zero-cost infrastructure can support a beta launch, but truth, privacy, recoverability and access control remain release requirements.


## Vercel gateway

After the OCI origin, restored data, readiness, and persistence checks pass, configure the Vercel project with only:

    ZENDOC_ORIGIN_URL=https://YOUR_OCI_ORIGIN

Do not put DATABASE_URL or any OCI/PostgreSQL application secret into Vercel. See docs/VERCEL_OCI_GATEWAY.md.
