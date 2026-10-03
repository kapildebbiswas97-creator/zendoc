# Vercel + OCI gateway launch

ZENDOC's zero-budget deployment path is:

Browser -> Vercel -> HTTPS OCI origin -> Caddy -> Flask -> PostgreSQL 16.

PostgreSQL stays private inside OCI. Vercel never receives DATABASE_URL, PostgreSQL credentials, ZENDOC admin credentials, SMTP secrets, payment secrets, storage secrets, or AI provider secrets. Vercel receives only the public OCI origin and a dedicated gateway-only token used to prevent direct bypass of the edge path.

## Why this split

Vercel is the public edge/domain gateway. The application and PostgreSQL remain together on OCI so the database can stay on an internal-only Docker network without exposing port 5432 to the public internet.

This avoids rewriting ZENDOC to Oracle Database and preserves the PostgreSQL engine already covered by production migration/readiness tests.

## Safe merge state

The repository keeps automatic Vercel Git deployments disabled in `vercel.ts` until the OCI origin has been restored and verified. This allows the gateway code to live in `main` without an accidental broken deployment.

When the real OCI origin is verified and the Vercel project has `ZENDOC_ORIGIN_URL` and `ZENDOC_GATEWAY_TOKEN`, remove the `git.deploymentEnabled: false` guard in a reviewed change, run the Production Gate, then deploy/promote the verified build.

## Build/runtime requirements

The gateway build is pinned to Node.js 24 through `package.json`. This avoids
creating new deployments with Node.js 20 after Vercel disabled Node.js 20 for
new builds on 2026-10-01.

CI validates `vercel.ts` with the pinned `@vercel/config` SDK using a
non-secret placeholder HTTPS origin. That proves the repository configuration
compiles; it does **not** prove the real OCI hostname is reachable.

## Required Vercel variables

Set only these gateway-scoped values in both Preview and Production:

    ZENDOC_ORIGIN_URL=https://YOUR_OCI_ORIGIN_HOSTNAME
    ZENDOC_GATEWAY_TOKEN=<long-random-gateway-only-secret>

Use the same gateway token in the OCI `deploy/oci/.env`. It must not be reused for the database, admin account, application secret key, SMTP, payments, storage, or AI providers.

The config fails closed when the origin value is missing, contains credentials, is not HTTPS, or contains a query/fragment. The token is injected into the origin request through Vercel's deployment-environment reference rather than committed in source.

External rewrite caching is explicitly disabled so authenticated healthcare responses are not cached by the Vercel rewrite layer.

## OCI variables

In deploy/oci/.env:

    ZENDOC_DOMAIN=origin.zendoc.example
    ZENDOC_PUBLIC_BASE_URL=https://zendoc-sage.vercel.app
    ZENDOC_GATEWAY_TOKEN=<same-long-random-gateway-only-secret>

ZENDOC_DOMAIN is the HTTPS hostname served by Caddy on the OCI VM.

ZENDOC_PUBLIC_BASE_URL is the browser-facing Vercel/custom-domain URL used when ZENDOC generates public links.

Caddy permits unauthenticated access only to `/api/v1/health` and `/api/v1/ready` for deployment probes. Normal application traffic must carry the dedicated Vercel gateway token. After Caddy verifies it, the secret header is stripped before Flask and a non-secret internal verification marker is added so rate limiting can safely use Vercel's client-IP header.

Keep the existing restore safety flag false during normal operation:

    ZENDOC_POSTGRES_RESTORE_ALLOW_RESET=false

## Cutover order

1. Export Render using the guarded PostgreSQL backup tooling before 2026-09-30.
2. Verify the archive and sidecars.
3. Prepare OCI and start PostgreSQL only.
4. Restore using the guarded restore command from docs/RENDER_TO_OCI_CUTOVER.md.
5. Start Flask + Caddy on OCI.
6. Verify the direct OCI origin with scripts/verify_deployment.py.
7. Verify data parity and persistence.
8. Only then set ZENDOC_ORIGIN_URL and the matching ZENDOC_GATEWAY_TOKEN in Vercel.
9. Deploy the Vercel gateway.
10. Verify login, Finder, healthcare APIs, Messages, Mental Wellness, Payments, Health Shop, uploads, and PWA behavior through the public Vercel URL.

## Release truth

Merging gateway code does not provision Oracle Cloud, create DNS, restore historical Render data, or prove live readiness. The expired Render free deployment is no longer treated as the production fallback or deployment-verification default. Keep ZENDOC_PERSISTENCE_VERIFIED, ZENDOC_BACKUP_VERIFIED, and ZENDOC_PUBLIC_RELEASE_REQUIRED false until their real checks pass.
