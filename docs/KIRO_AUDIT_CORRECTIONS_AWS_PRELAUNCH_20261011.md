# ZENDOC AWS/Vercel prerelease — Kiro audit reconciliation (2026-10-11)

**Current code review base:** \`fix/form-submit-review-safety-20261011\`, above draft PRs #130–#133.  
**Purpose:** preserve older local Kiro/Codex work, correct findings from the older \`deployment/aws-production\` checkout, and prepare *non-production* code for a manual owner-led AWS/Vercel launch.

## Summary

The Kiro Crew report inspected **C:\zendoc** at local branch \`deployment/aws-production\`, not the current PR #130 → #131 → #132 → #133 release stack. Some of its claims were real bugs; others refer to files absent from the current stack. **Do not cherry-pick all of the older deployment commits or blindly copy Kiro's recommended commands.**

The separate local directory **C:\zendoc-kiro** did not exist when Kiro IDE tried to open it. Kiro IDE's shell returned exit code -1. This is a local tooling/workspace problem, not proof that GitHub PRs #129–#133 do not exist. Preserve all local work on \`deployment/aws-production\` and any Codex working tree.

### Item-by-item adjudication

| Kiro finding | Current proposed branch truth | Safe response |
| --- | --- | --- |
| A-1: app Docker runs as root | Confirmed in old shared Dockerfile | **Fixed in this PR**: unprivileged UID 10001, owned upload/instance paths; Docker build and runtime checks in CI |
| A-2: interactive rollback in \`deploy/aws/deploy.sh\` | **That file does not exist** on current release stack | No fake fix. Old local branch script requires independent review only if deliberately migrated |
| A-3: Caddy overrides \`X-Frame-Options\` to SAMEORIGIN | **Not in current \`deploy/aws/Caddyfile\`**; Flask header is DENY | Existing policy preserved; regression guard checks it |
| A-4: CSP allows unsafe inline script | Confirmed, but templates currently depend on inline JS | **Open hardening item**: enumerate and migrate inline scripts, then introduce request nonces and full browser payment tests. Do not abruptly block scripts or break healthcare flows |
| A-5: rate limiter is per-process | Need an actual production run, storage backend and load test | Cannot claim Redis or Caddy plugin configured; backlog |
| A-6: scope-based access regression | Prior draft PR #133 fixed family-care cross-purpose grants | Existing tests preserved and included in new CI |
| A-7: gateway token rotation | Runbook work outstanding | Rotate only with planned two-token window; never publish tokens |
| B-1: no pgvector | Standard \`postgres:16-bookworm\` does **not** ship pgvector | **Not silently fixed**: local lexical RAG remains available. Semantic vector extension needs a reviewed image/volume migration, model, and evaluation before launch |
| B-2 through B-5: clinical emergency triggers, local fallback and provenance | Need targeted model/safety tests; no unsafe automatic medication changes | Remain backlog; do not claim clinical validation |
| C-1: TURN uses host network | Confirmed in current Compose | **Fixed in this PR**: optional bridged TURN, explicit 3478 TCP/UDP and relay UDP port range; must still pass two-device real-network verification |
| C-2: Caddy runtime healthcheck missing | Confirmed in Compose | Startup depends on healthy Flask. Caddy TLS/DNS still needs external manual HTTPS probe; a local config probe is not a TLS certificate guarantee |
| C-3: off-instance backup not verified | **Confirmed**: \`postgres_backup.py\` explicitly generates local archive, SHA and manifest only | **Owner blocker**: arrange encrypted off-instance copies plus an isolated restore rehearsal. Do not set \`ZENDOC_BACKUP_VERIFIED=true\` until tested |
| C-4: \`~/.aws:/root/.aws\` backup mount | **Not present** in current Compose | Existing backup has no host AWS credentials bind mount. Prefer EC2 IAM instance role for any future S3 upload; not implemented |
| C-5: excessive DB connections | Needs measured traffic and pool size | Backlog; do not add PgBouncer without a measured need |
| C-6: old GitHub Actions hardcodes AWS region | \`.github/workflows/aws-deployment.yml\` **does not exist** on this release branch | No action on absent file; review IAM/region in future approved deploy workflow |
| C-7: CI \`pytest ... || echo\` mask | Not present in current strict stacked release workflow | Fail-closed tests preserved |
| C-8: cloud log aggregation absent | External services not configured | Owner decision tomorrow |
| D-1: no hospital bed board | **Incorrect for current release stack**: \`hospital_bed_board.py\` is in PR #132 (BETA) | Preserve tested operator-attested bed board; *not* full ADT/IPD or verified public bed availability |
| D-5: no organization verification route | Existing \`organization_health_routes.py\` includes owner verification routes | No speculative bypass or direct DB edit; require explicit signed-off action |

## Changes safely implemented in this PR

1. App + operations-worker Docker image runs as the unprivileged \`zendoc\` user (UID/GID 10001). Upload and app-instance directories are owned by the same user.
2. New \`.dockerignore\` explicitly excludes source-control history, private \`.env\`, key files, personal upload data, database files, caches and local cloud credentials from Docker **build context**. This is defense-in-depth; still audit source archives for secrets.
3. Optional TURN profile is moved from \`network_mode: host\` to a Docker bridge, with only configured TCP/UDP 3478 and configured relay UDP range forwarded. TURN secrets are optional for the **default** stack; starting TURN without them is still rejected by \`turn-entrypoint.sh\`.
4. New offline regression checks verify those invariants and avoid fabricated claims about backups or public TLS.
5. CI builds an image, checks UID at runtime, checks Compose normal/realtime profiles and ensures no private config is copied into the image. Uses synthetic non-production values; **nothing gets deployed**.

## Tomorrow: owner-driven AWS and Vercel checklist

**A — Local checkout before deployment**

1. Open **PowerShell outside Kiro**. Preserve \`C:\zendoc\` and its old local commits. Run \`git status\`, \`git branch -avv\`, \`git worktree list\`, and \`git fetch origin\`.
2. Review the new draft PR and full suite **on the exact final combined commit**. Do not merge automatically; the Stitch frontend PR must be integrated and re-tested separately.
3. Confirm Docker CLI available where you will deploy. Windows Docker Desktop is optional if building directly on Linux EC2.

**B — AWS billing, identity and network**

4. In AWS Console confirm account, billing alerts/free-tier eligibility, correct region, EC2 instance type, root EBS size and public IP. **Do not assume all AWS accounts remain free.**
5. Create/verify security group only exposing SSH (restricted to operator IP), TCP 80/443, and TURN **only if later enabled and tested**. Never publish PostgreSQL 5432. Require an HTTPS hostname/DNS for the origin.
6. Use EC2 IAM instance role with least privileges if off-instance backup to S3 is commissioned. Never copy AWS long-lived keys into Git or Docker image.

**C — Application runtime**

7. Create \`deploy/aws/.env\` on the instance based on \`.env.example\`; generate distinct strong secrets. Keep file owner-readable only. Do not post its contents into chat.
8. Verify \`docker compose -f deploy/aws/compose.yaml config --quiet\`, build non-root app image, and test service health on disposable staging data.
9. Confirm PostgreSQL schema, exact Git SHA and real persistence before changing \`ZENDOC_PERSISTENCE_VERIFIED\`; test a rollback on non-production data.

**D — Backups are a release blocker**

10. Create a \`/var/backups/zendoc\` directory with restrictive permissions. Execute a PostgreSQL custom-format backup and \`verify_postgres_backup.py\`; then copy it to a separate encrypted storage location and restore into a disposable separate database.
11. Set \`ZENDOC_BACKUP_VERIFIED=true\` only with recorded off-instance copies, usable restore results and owner review; archive validity alone does not prove recovery. Current Compose has no automated S3 upload.

**E — Vercel and final verification**

12. Reauthorize the **existing** Vercel project; do not create a third project by default. Confirm origin HTTPS and the gateway configuration on the correct SHA.
13. Probe browser URL and \`/api/v1/health\` and \`/api/v1/ready\`; test patient and provider flows and tenant isolation with **synthetic accounts**.
14. No real patient release before security review, consent evidence, clinician/legal controls, verified external services and field trials.

## Explicit blockers that this PR does NOT resolve

- No live AWS EC2 / domain / Vercel READY deployment evidence; no verified public staging URL.
- Real secret values, IAM role, DNS, TLS, backup offload and restore need **human console access tomorrow**.
- Turning on TURN requires real public IP/firewall configuration and two-device STUN/TURN behavior checks. Bridge NAT relay behavior is unverified.
- RAG pgvector is not installed; lexical retrieval remains the truthful status. Do not switch images on a persistent production database without reviewed migration/restore plan.
- CSP \`unsafe-inline\` must be removed with a browser-verified script nonce/migration, not by breaking current forms or checkout.
- Cloud provider integrations, insurance, payments, clinical workflows, WhatsApp and FHIR exchange still require real authorized contracts, credentials and end-to-end evidence.

**Release rule:** Green unit CI ≠ verified staging ≠ licensed clinical use. Keep drafts unmerged until reviewed, approved and evidenced.
