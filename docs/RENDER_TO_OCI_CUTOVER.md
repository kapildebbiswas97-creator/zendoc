# Render PostgreSQL -> OCI PostgreSQL cutover

Render's current notice says the free `zendoc-db` becomes inaccessible on 2026-09-30. This runbook preserves the existing PostgreSQL engine and moves the data to the self-managed PostgreSQL 16 service in `deploy/oci/compose.yaml`.

This is a data-preservation procedure. It does not by itself prove a public production launch.

## Safety rules

- Keep the Render source until OCI has passed readiness, persistence and representative-record checks.
- Freeze writes during the final dump. Do not allow two writable production databases during cutover.
- Never paste database URLs into Git, screenshots, PR comments or logs.
- PostgreSQL port 5432 remains private on OCI.
- Start the OCI `db` service **before** the first restore, but do not start the ZENDOC `web` service first. That keeps the target empty and avoids needing a destructive reset.
- `ZENDOC_POSTGRES_RESTORE_ALLOW_RESET` stays `false` during normal operation.

## 1. Export Render before 2026-09-30

Use Render's external PostgreSQL connection URL from the database dashboard. Read it silently into the shell rather than placing it directly in a command:

    read -rsp "Render DATABASE_URL: " DATABASE_URL; echo
    export DATABASE_URL
    mkdir -p migration-backup
    chmod 700 migration-backup
    python scripts/postgres_backup.py --output-dir ./migration-backup
    unset DATABASE_URL

The command prints the generated archive path. The backup directory contains:

- `zendoc-postgres-*.dump`
- `zendoc-postgres-*.dump.sha256`
- `zendoc-postgres-*.dump.json`

Verify the exact archive before moving it:

    python scripts/verify_postgres_backup.py ./migration-backup/zendoc-postgres-YYYYMMDDTHHMMSSZ.dump

Do not continue if checksum/catalog verification fails.

## 2. Preserve another copy before cutover

Keep an encrypted/off-machine copy of the archive and sidecars. A local laptop copy plus an OCI VM copy is better than having the only copy on the new VM.

The archive contains application data. Treat it as sensitive and do not place it in the Git repository.

## 3. Prepare OCI without starting the app

On the OCI VM:

    cd zendoc
    cp deploy/oci/.env.example deploy/oci/.env
    chmod 600 deploy/oci/.env

Fill the required OCI environment values. Keep:

    ZENDOC_POSTGRES_RESTORE_ALLOW_RESET=false
    ZENDOC_PERSISTENCE_VERIFIED=false
    ZENDOC_BACKUP_VERIFIED=false
    ZENDOC_PUBLIC_RELEASE_REQUIRED=false

Create the protected backup staging directory and start PostgreSQL only:

    sudo install -d -m 700 /var/backups/zendoc
    cd deploy/oci
    docker compose --env-file .env -f compose.yaml up -d db
    docker compose --env-file .env -f compose.yaml ps db

Copy the verified `.dump`, `.sha256` and `.json` files into `/var/backups/zendoc`.

## 4. Verify the copied archive on OCI

Build the operations container and verify the copied archive:

    docker compose --env-file .env -f compose.yaml --profile ops build backup
    docker compose --env-file .env -f compose.yaml --profile ops run --rm \
      --entrypoint python backup \
      /opt/zendoc/scripts/verify_postgres_backup.py \
      /backups/zendoc-postgres-YYYYMMDDTHHMMSSZ.dump

This catches transfer corruption before any target database is changed.

## 5. Restore into the fresh OCI database

With `web` still stopped:

    docker compose --env-file .env -f compose.yaml --profile ops run --rm \
      --entrypoint python backup \
      /opt/zendoc/scripts/postgres_restore.py \
      /backups/zendoc-postgres-YYYYMMDDTHHMMSSZ.dump

The restore tool:

- verifies the archive and sidecars again;
- checks the target database name against `POSTGRES_DB`;
- keeps the target URL/password out of `pg_restore` arguments;
- uses `--single-transaction` and `--exit-on-error`;
- refuses to overwrite an already-populated target while reset permission is false.

If it reports that application tables already exist, stop and investigate why. Do not enable reset merely to get past the guard.

For an intentionally disposable/recreated OCI target only, the operator can temporarily set:

    ZENDOC_POSTGRES_RESTORE_ALLOW_RESET=true

Run the restore once, then return the value to `false`. Never use this against the surviving Render source.

## 6. Start ZENDOC and let migrations run

After the restore succeeds:

    docker compose --env-file .env -f compose.yaml up -d --build web caddy
    docker compose --env-file .env -f compose.yaml ps

Check the direct OCI origin:

    curl -fsS https://YOUR_OCI_ORIGIN/api/v1/health
    curl -fsS https://YOUR_OCI_ORIGIN/api/v1/ready

Then:

    python scripts/verify_deployment.py https://YOUR_OCI_ORIGIN \
      --expected-commit COMMIT_SHA \
      --require-platform oci \
      --require-engine postgresql

Do not require persistence verification yet.

## 7. Compare real records before switching traffic

Check representative records rather than only table existence:

- owner/admin account and role;
- patient accounts and isolation;
- provider/organization data;
- appointments and booking ownership;
- Health Memory / medical records / timeline data;
- messages and notifications;
- payment/ledger/audit records that existed before cutover.

Compare source and target counts for the important tables while Render is still accessible. Investigate any difference before routing users to OCI.

## 8. Prove persistence

Create synthetic test data on OCI, restart the containers, verify the same IDs/data, rebuild the same reviewed commit, and verify again. Only after that evidence passes may `ZENDOC_PERSISTENCE_VERIFIED=true` be considered.

Backup verification remains separate: make an off-instance copy of an OCI backup and run the isolated restore drill before setting `ZENDOC_BACKUP_VERIFIED=true`.

## 9. Switch Vercel only after OCI passes

The Vercel gateway must not receive `DATABASE_URL`. It receives only:

    ZENDOC_ORIGIN_URL=https://YOUR_OCI_ORIGIN

After the OCI origin is verified, configure that variable in the ZENDOC Vercel project and deploy the reviewed gateway commit. Test the browser-facing Vercel URL for:

- login/logout and session continuity;
- redirects and generated links;
- Find Care and location search;
- API readiness/health behavior;
- report/media upload and retrieval using the configured durable object-storage path;
- messages/calls where the configured providers permit them;
- Android/desktop PWA behavior.

Keep the Render database untouched until this public-path verification and data parity check pass.

## 10. Rollback rule

If OCI or the Vercel gateway fails before final cutover, route users back to the still-valid Render deployment and do not write to both databases.

If data has already begun changing on OCI after cutover, do not blindly restore the old Render snapshot over it. Stop writes, preserve both states, and reconcile before any rollback.
