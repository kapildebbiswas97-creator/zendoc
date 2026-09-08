# ZENDOC Production Release Checklist

Use this checklist before promoting a ZENDOC release to the Render production service.

## 1. Source control checkpoint

- Confirm the release commit SHA.
- Confirm the release comes from the intended production branch.
- Do not force-push the production branch.
- Keep a known-good rollback commit SHA.
- Confirm there are no uncommitted/local-only changes being treated as production work.

Recommended branch policy:
- require the ZENDOC Production Gate before merge;
- require review before merging to `main`;
- block force-pushes;
- block deletion of the production branch.

## 2. Blocking CI gates

The following must be green for the exact release commit:

- Critical Safety & Security Gate
- Full SQLite Test Suite
- PostgreSQL Production Migration & Readiness
- Static Security & Dependency Audit
- Release Gate

Do not weaken security, privacy, truthfulness, CSRF, IDOR, tenant isolation, emergency precedence, or medical-safety tests merely to make CI green.

An external Vercel status is not a ZENDOC release gate because ZENDOC production hosting is Render.

## 3. Render deployment verification

GitHub repository variable required:

`ZENDOC_DEPLOYMENT_URL=https://<current-render-domain>`

Verify:

- `GET /api/v1/ready` returns ready.
- deployment platform reports Render when Render metadata is present.
- deployed Git commit matches the intended release commit.
- database backend is the expected production backend.
- persistence/durability readiness is true.
- required schema tables exist.
- migrations completed successfully.
- no secret values are exposed by readiness output.

If `ZENDOC_DEPLOYMENT_URL` is not configured, deployment-health CI may skip. A skipped deployment check is not equivalent to a verified deployment.

## 4. Database and migration safety

Before deployment:

- PostgreSQL readiness gate green.
- New tables/columns included in `migrate_schema()` where required for existing installations.
- SQLite compatibility retained for tests/development.
- No destructive migration without a verified backup/rollback plan.
- Foreign-key creation order is valid on PostgreSQL.
- New insert tables are supported by the PostgreSQL backend where last-insert IDs are required.

## 5. Healthcare truthfulness checks

Confirm the release does not fabricate:

- providers/doctors;
- beds;
- pharmacy stock;
- prices;
- appointments;
- provider availability;
- ambulance dispatch;
- alerts;
- partner connectivity;
- verification;
- coverage;
- users;
- revenue.

Keep these distinctions explicit:

`publicly listed != ZENDOC verified != connected != bookable != live available`

## 6. Business API privacy boundary

Confirm Business API scopes still exclude:

- patient records;
- medical history;
- prescriptions;
- diagnostic results;
- symptoms;
- diagnoses;
- clinical notes;
- private EMR/EHR;
- ABHA/Aadhaar-linked private clinical information.

Partner access must remain:

- authenticated;
- scoped;
- rate-limited;
- tenant-isolated;
- audited without clinical payloads.

## 7. Booking/handoff safety

Verify:

- partner handoff is not presented as a confirmed patient appointment;
- active slot holds block conflicting coordination requests;
- expired/released holds can be recycled;
- rejection/cancellation releases holds;
- provider/owner status changes use the same hold rules;
- handoff + hold + audit + in-app notification persist atomically;
- cross-partner and cross-provider access remains blocked.

## 8. Provider network

Confirm:

- prospect/invitation counts come only from real stored prospect records;
- registered/verified/activated stages require real linked provider records;
- activation is not manually claimable without real provider verification state;
- doctor/hospital activation requires a real published schedule;
- provider verification evidence remains owner-reviewed.

## 9. Public data quality

Review Data Freshness & Ingestion:

- P0 never-ingested sources;
- P0 stale sources;
- P1 aging sources;
- unresolved geography;
- ambiguous geography;
- rejected records;
- duplicate public entities;
- conflicting approved public-listing claims.

Do not treat reference-only or authorized-integration-required sources as failed ingestion.

## 10. Finder quality

Verify:

- exact high-confidence cross-source duplicates collapse;
- provenance from all official sources remains visible;
- same-name different facilities remain separate;
- authoritative/fresher evidence follows defined precedence;
- approved public claims link only through explicit owner-approved identity;
- an approved claim does not promote an unverified provider;
- conflicting approved claim links remain visible instead of being hidden.

## 11. Notification truthfulness

Delivery lifecycle:

- created: delivery record exists;
- queued: no send is claimed;
- sent: a configured provider accepted the send;
- delivered: delivery/local inbox confirmation exists;
- failed: this delivery attempt failed.

Without a configured external provider:
- email/SMS/WhatsApp/push remains queued;
- never claim sent or delivered.

In-app notifications may be marked delivered only after the local inbox row is successfully created.

## 12. Pilot/startup evidence

Keep clearly separate:

- target;
- owner-entered observed;
- system-derived;
- forecast.

Proposal/LOI is not revenue.

Do not invent:
- users;
- D7/D30 retention;
- provider activation;
- pilot conversion;
- revenue;
- MRR;
- cash;
- runway.

## 13. Rollback

Record before deployment:

- release SHA;
- previous known-good SHA;
- Render deploy identifier if available;
- database backup/readiness status.

If release health fails:
1. stop promotion;
2. inspect exact failing readiness/gate;
3. roll back to the known-good application commit when necessary;
4. do not roll back database schema blindly after irreversible migrations;
5. preserve incident evidence/audit logs;
6. re-run Production Gate before the next deployment.

## Release decision

A release is ready only when:

1. all blocking CI gates are green;
2. Render readiness is verified for the deployed commit;
3. no unresolved critical security/privacy/medical-safety regression exists;
4. required migrations are confirmed;
5. critical public-data freshness risks are understood and truthfully surfaced.
