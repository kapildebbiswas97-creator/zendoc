# Vercel + OCI gateway launch

This is the zero-budget public-edge path for ZENDOC after the Render database trial.

## Architecture

Browser -> Vercel -> HTTPS rewrite -> OCI origin -> Caddy -> ZENDOC Flask -> PostgreSQL 16.

PostgreSQL stays inside the OCI Docker backend network. Do not publish port 5432 and do not put DATABASE_URL, POSTGRES_PASSWORD, ZENDOC_SECRET_KEY, admin credentials, SMTP credentials, AI keys, or storage secrets in Vercel.

Vercel is the browser-facing gateway, not the database host. OCI remains the application/database origin because exposing a self-managed PostgreSQL server directly to Vercel's public serverless network would weaken the zero-budget security model.

## Vercel configuration

The repository uses `vercel.ts` and pins `@vercel/config`. It reads one Vercel environment variable:

    ZENDOC_ORIGIN_URL=https://YOUR_OCI_ORIGIN_HOSTNAME

The build fails when the variable is missing, contains credentials, is not HTTPS, or contains query/fragment data.

The gateway rewrites all application paths to the OCI origin. Rewrite caching is explicitly disabled at the Vercel layer. ZENDOC remains responsible for its own browser/static caching policy.

The Vercel environment must not contain `DATABASE_URL`; the database is reachable only by the OCI web container over the internal Docker network.

## OCI origin requirements

1. Create an Always Free-eligible OCI compute VM if your account/home region has capacity.
2. Follow `docs/OCI_ZERO_BUDGET_LAUNCH.md`.
3. Give the OCI origin its own DNS hostname and valid HTTPS certificate.
4. Keep OCI ingress to SSH from trusted operator sources where practical and public 80/443. Do not open 5432.
5. Set `ZENDOC_PUBLIC_BASE_URL=https://zendoc-sage.vercel.app` (or the final custom Vercel domain) in `deploy/oci/.env`.
6. Set `ZENDOC_DOMAIN` to the OCI origin hostname, not the Vercel hostname.

## Cutover sequence

Do not point Vercel at OCI until the origin itself is healthy.

1. Back up the Render PostgreSQL source with `scripts/postgres_backup.py`.
2. Verify checksum/catalog and perform an isolated restore drill.
3. Restore to the OCI PostgreSQL container while writes are frozen.
4. Start ZENDOC on OCI and run:
   
       python scripts/verify_deployment.py https://YOUR_OCI_ORIGIN --expected-commit COMMIT_SHA --require-platform oci --require-engine postgresql

5. Prove synthetic persistence across container restart/rebuild.
6. Only after the OCI origin passes, set the Vercel project environment variable `ZENDOC_ORIGIN_URL`.
7. Redeploy the Vercel production project.
8. Verify the public Vercel URL for login, redirects, Find Care, API readiness, uploads (within the configured durable-storage path), and mobile/PWA behavior.
9. Keep the Render source unchanged until data counts and representative records have been checked on OCI.

## Release truth

Merging this code does not provision Oracle Cloud, migrate data, create DNS, set Vercel environment variables, or prove persistence. Keep `ZENDOC_PERSISTENCE_VERIFIED=false`, `ZENDOC_BACKUP_VERIFIED=false`, and `ZENDOC_PUBLIC_RELEASE_REQUIRED=false` until the corresponding operator checks actually pass.
