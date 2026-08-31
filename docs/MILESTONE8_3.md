# Milestone 8.3 — Demo Stabilization and Persistent Accounts

## Outcome

Milestone 8.3 fixes the application-side cause of disappearing accounts and makes the remaining infrastructure gap visible. Local development and isolated tests continue to use SQLite. Production can now select managed PostgreSQL through `DATABASE_URL`; the adapter and schema bootstrap are **BETA** until exercised against the actual managed database. The current deployment must remain **INTEGRATION REQUIRED** until a durable database is configured and the documented restart/redeploy check passes.

No model was downloaded, run, trained, benchmarked, or fine-tuned.

## Exact root cause

At the M8.2 baseline, `load_config` read `DATABASE_URL`, but `get_db()` ignored it and always opened `instance/zendoc.db`. Development and production therefore selected the same service-local SQLite path.

The current `render.yaml` uses a free Render web service and does not provision a database or persistent disk. Render documents that free web-service files, including local SQLite databases, are lost on spin-down, restart, and redeploy. A registration committed successfully to the current instance, but a later instance could start with a new empty SQLite file. The account then appeared to have vanished and the user was incorrectly led toward registering again.

Official platform references:

- [Render free-service filesystem](https://render.com/docs/free#local-files-lost-on-redeploy)
- [Render persistent disks](https://render.com/docs/disks)
- [Render Postgres connection guidance](https://render.com/docs/postgresql-creating-connecting)

This was not caused by Flask session expiry, password hashing, logout, normalized-email lookup, startup table creation, or a cleanup job. Existing restart tests reopened the same SQLite path and passed. `CREATE TABLE IF NOT EXISTS` and the additive migrations did not recreate or delete user rows. The failure boundary was replacement of the entire ephemeral filesystem.

## Account persistence versus session persistence

An account is a durable database identity. A session is a revocable browser authentication state. M8.3 keeps those concepts separate:

- successful login clears and rotates all prior session state;
- the session stores only the stable user ID plus bounded authentication metadata;
- role and active state are reloaded from the database on every request;
- idle expiry clears the session and returns the user to login with `Your session expired. Please log in again.`;
- session expiry never redirects to registration;
- production logout uses a CSRF-protected POST;
- the old GET logout remains available only in development/testing for compatibility;
- wrong and nonexistent accounts return the same `Email or password is incorrect.` message.

## Authentication changes

- Email identifiers use Unicode NFKC normalization, outer-whitespace trimming, and case folding.
- Duplicate registration returns `An account with this email already exists. Please log in.`
- Passwords continue to use Werkzeug's secure password hashing and are never stored or displayed as plaintext.
- Reset tokens now have an explicit `password_reset` purpose and 30-minute expiry. They cannot be used as bearer access tokens.
- Password reset revokes outstanding tokens for the account.
- Production password recovery is explicitly **INTEGRATION REQUIRED** until a delivery provider is implemented. Development/testing retains a clearly labeled local-beta token flow.
- Public Admin registration, client role promotion, profile-field promotion, and forged Admin identity remain blocked. The configured owner reconciliation remains server-side and idempotent.

## Persistence architecture

The database target resolver now has an explicit engine and durability state:

| Environment | Target | Status |
| --- | --- | --- |
| Development | Local SQLite path | **WORKING — LOCAL DEVELOPMENT** |
| Testing | Explicit temporary SQLite path | **WORKING — ISOLATED TESTING** |
| Production + no durable target | Service-local SQLite | **INTEGRATION REQUIRED** |
| Production + managed PostgreSQL URL | psycopg adapter | **BETA** pending live migration/redeploy verification |
| Production + explicitly configured persistent SQLite mount | SQLite single-instance fallback | **BETA** pending mount/redeploy verification |

`DATABASE_URL` is no longer silently ignored. PostgreSQL uses a small compatibility adapter that preserves parameter binding, row mappings, generated IDs, additive schema initialization, migration tracking, and transaction control. SQLite behavior remains unchanged apart from a bounded busy timeout.

Production can set `ZENDOC_REQUIRE_DURABLE_DATABASE=true` to fail closed when persistence is unsafe. It defaults to `false` in `render.yaml` so the current demo is not unexpectedly taken offline; the owner Command Center shows a high-visibility warning instead.

The owner view never displays a database URL, hostname, username, or password. It reports only engine, durability, persistence state, and manual verification state.

## Migration behavior

The M8.3 schema migration is additive and idempotent:

- adds `api_tokens.token_type` with an `access` default for legacy rows;
- adds nullable `api_tokens.expires_at`;
- adds a purpose/expiry/revocation index;
- records `m8_3_auth_persistence_v1` in `schema_migrations`;
- preserves every user, role, profile, and associated record;
- performs no database reset and deletes no legacy account.

Switching an existing production service from SQLite to PostgreSQL is a datastore migration, not just an environment-variable change. Do not set `DATABASE_URL` on a service containing accounts until the existing SQLite database has been backed up and imported through a reviewed migration run. See `docs/PRODUCTION_PERSISTENCE.md`.

## Verification added

The focused suite covers:

- Unicode/case/whitespace normalization and duplicate blocking;
- password hashing, wrong password, nonexistent account, malformed and injection-shaped identifiers;
- session rotation, role tampering, expiry-to-login, CSRF-protected logout;
- reset-token purpose, expiry, and bearer-token isolation;
- configured-owner preservation and Admin registration/promotion rejection;
- patient and doctor identity/data across Flask app recreation using the same isolated database;
- health metric, notification, appointment, provider profile/schedule, conversation, and message persistence;
- patient notification isolation after restart;
- legacy M8.2 database migration without row loss;
- development, testing, unsafe-production, managed-PostgreSQL, and mounted-SQLite configuration behavior;
- production fail-closed option and credential-free owner status;
- PostgreSQL SQL translation and migration primitives;
- representative patient and doctor demo routes with local/cloud AI disabled.

## Release status

Application restart persistence is **WORKING** with a stable SQLite file. Managed PostgreSQL support is **BETA**. Actual production persistence is **INTEGRATION REQUIRED** because no hosted durable database credentials or completed redeploy verification were available during this milestone.

**DEMO FREEZE BLOCKED — PERSISTENCE INTEGRATION REQUIRED**
