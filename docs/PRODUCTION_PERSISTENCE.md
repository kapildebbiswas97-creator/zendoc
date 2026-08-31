# Production Persistence

## Required release condition

ZENDOC is ready for external testers only after a durable production database is configured, existing data is migrated safely, and a controlled account survives a real service restart/redeploy. Automated temporary-database tests prove application restart behavior; they cannot prove the external platform's durability.

Never put a database URL, password, or real user credential in source, tests, documentation, templates, or logs.

## Recommended path: managed PostgreSQL

1. Create a managed PostgreSQL database in the same Render region as the web service.
2. Back up the current SQLite file before changing any service configuration.
3. Rehearse the SQLite-to-PostgreSQL import against a non-production database. Compare row counts per table, normalized user identities, owner identity, roles, foreign-key relationships, and representative patient/provider records.
4. Configure the web service's secret `DATABASE_URL` with the provider's internal PostgreSQL URL. Do not paste it into Git or a Blueprint value.
5. Leave `ZENDOC_PERSISTENCE_VERIFIED=false` during migration and initial smoke testing.
6. Deploy during a controlled maintenance window. Confirm schema migration `m8_3_auth_persistence_v1`, exactly one configured owner, and expected user/data counts.
7. Complete the manual restart/redeploy procedure below.
8. Only after it passes, set `ZENDOC_PERSISTENCE_VERIFIED=true` and record the operator, time, database backup, deployed commit, and test account ID in the private release record.
9. Consider `ZENDOC_REQUIRE_DURABLE_DATABASE=true` after the cutover so later configuration drift fails closed.

The application recognizes `postgresql://`, Render's legacy `postgres://` alias, and `postgresql+psycopg://`. The URL is used only by the database driver and is never returned by owner status APIs.

## Compatible fallback: persistent SQLite mount

A paid single-instance service may use SQLite on a verified persistent disk:

```text
ZENDOC_DATABASE_PATH=/var/data/zendoc.db
ZENDOC_PERSISTENCE_MODE=durable
ZENDOC_PERSISTENCE_VERIFIED=false
```

Attach the disk at `/var/data` before starting the service. Render free web services do not support persistent disks. This option cannot scale to multiple service instances and needs SQLite-aware backup/recovery. Managed PostgreSQL is the preferred production route.

Do not mark this path verified until a real restart/redeploy preserves the account and data.

## Current compatibility strategy

Unsafe production SQLite does not stop startup by default because an immediate strict failure would take the existing demo offline. Instead:

- startup logs a critical persistence warning;
- the owner Command Center reports **INTEGRATION REQUIRED**;
- `ZENDOC_REQUIRE_DURABLE_DATABASE=true` enables strict startup failure;
- external tester readiness remains blocked.

## Existing SQLite data migration

Treat the cutover as a controlled data migration:

1. Stop writes or enter a maintenance window.
2. Copy the SQLite database to a versioned, access-controlled backup.
3. Run `PRAGMA integrity_check` on the copy.
4. Inventory row counts for every application table and capture the configured owner's stable ID/email.
5. Import into a non-production PostgreSQL target using a reviewed tool or migration program that preserves IDs and foreign-key order.
6. Reset PostgreSQL identity sequences to at least each table's maximum imported ID.
7. Run schema migrations idempotently.
8. Compare row counts, normalized email uniqueness, owner identity, password-hash presence, roles, provider profiles, schedules, appointments, health data, conversations/messages, notifications, and audit records.
9. Perform patient, provider, and owner login/isolation smoke tests.
10. Back up both sides, then repeat the reviewed process for production.

M8.3 intentionally does not auto-copy an unknown production database at startup. Automatic cross-database copying could partially migrate sensitive records or mutate the wrong target.

## Manual restart/redeploy verification

Use only a controlled synthetic account and synthetic data:

1. Confirm owner status reports the expected engine and `manual verification required`.
2. Register a synthetic patient through the normal public flow.
3. Record the stable user ID in the private release record; do not record the password in Git.
4. Add a synthetic profile field, health measurement, appointment, notification, and message.
5. Log out and log in again. Confirm the same ID, role, and data.
6. Restart the service. Log in again and recheck.
7. Redeploy the same reviewed commit. Log in again and recheck.
8. Register and test a synthetic provider. Confirm profile, verification state, schedule, booking, and permitted messages.
9. Confirm patient/provider isolation and exactly one configured owner.
10. Confirm no duplicate account was created and no password hash or database credential appeared in logs.
11. Mark the verification in the private release record, then set `ZENDOC_PERSISTENCE_VERIFIED=true`.

## Rollback

- Keep the pre-migration SQLite backup read-only and retain the PostgreSQL backup/snapshot.
- Do not point two writable deployments at different databases during rollback.
- If validation fails before cutover, restore the prior configuration and prior service version; do not delete either datastore.
- If writes occurred after cutover, stop and reconcile them deliberately. Blindly reverting to the old SQLite file would lose those writes.
- Clear `ZENDOC_PERSISTENCE_VERIFIED` whenever the database target, mount, service, region, or restore point changes.

## Known remaining limitations

- Live managed-PostgreSQL provisioning and migration rehearsal were not available in M8.3.
- Local uploaded medical files also require durable object storage or a persistent mount; database durability alone does not preserve file bytes.
- Distributed rate limiting, backups, recovery drills, monitoring, and regulatory/clinical review remain production hardening work.
