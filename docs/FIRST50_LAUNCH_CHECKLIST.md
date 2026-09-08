# ZENDOC First 10 → First 50 Launch Checklist

Use this checklist for the first real pilot users.

## Gate 0 — do not invite users if any blocker exists

Open:

`/owner/first50-readiness`

Do not launch if status is:

`BLOCKED`

Hard blockers include:
- database unreachable/not ready;
- missing required schema/migrations;
- unverified production persistence;
- local backup path failure when SQLite is used;
- elevated recent server-error rate.

## Phase 1 — first 10 users

Invite 10 real users only after the production gate is green.

For each user, verify:
1. registration succeeds;
2. login succeeds;
3. dashboard loads;
4. logout/login works again;
5. user can perform one useful action;
6. no other user's appointments/records/messages are visible;
7. no 500 error is produced.

Recommended useful patient actions:
- upload one report;
- add one health metric;
- search for care;
- ask ZENDOC AI a non-emergency educational question;
- request a provider appointment only when a real provider is available.

Do not promise live stock, slots, beds, ambulance dispatch, or scheme approval unless the corresponding real provider/partner data exists.

## Monitor after the first 10

Check:
- `/owner/first50-readiness`
- `/owner/observability`
- `/owner/pilot-scorecard`

Before expanding, require:
- zero launch blockers;
- no high-severity request-reliability signal;
- no cross-user/security incident;
- no unresolved repeating 500 error;
- database persistence still verified.

Warnings about missing geography/providers may remain during a controlled local pilot, but they must be understood before inviting users from those locations.

## Phase 2 — expand to 50

Expand from 10 to 50 only when:
- the first 10 can register/login/use dashboards reliably;
- user isolation remains intact;
- provider workflows used by the pilot have real providers;
- stale inventory/diagnostic data is refreshed before use;
- incident monitoring is being reviewed.

## Geography

Target official coverage:
- West Bengal;
- Assam;
- Uttar Pradesh.

Geography loading and live provider coverage are separate.

A village existing in ZENDOC does not mean ZENDOC has a hospital, doctor, lab, pharmacy, ambulance, or live service there.

For Dibrugarh competition use, load Assam geography and then prioritize real Dibrugarh provider data separately.

## Password recovery

Until password-reset delivery is integrated:
- tell pilot users to keep their password safely;
- use controlled owner-assisted recovery when needed;
- do not claim automatic email recovery.

This is a pilot warning, not a hidden feature.

## Provider data rule

A provider can be:
- public-directory only;
- ZENDOC verified;
- connected;
- live operationally observed.

These are different states.

Only live/fresh provider observations should power claims such as:
- medicine in stock;
- diagnostic test available;
- current price;
- current slot.

## Expansion beyond 50

Do not use user-count growth alone as the decision.

Before larger expansion, add:
- integrated password recovery;
- production backup/PITR verification;
- provider support workflow;
- basic incident ownership;
- stronger real provider coverage;
- privacy/legal review appropriate to the deployment;
- real external integration testing for any partner feature enabled.

## Launch principle

Small truthful coverage is better than large fabricated coverage.

The first goal is not “all India is live.”

The first goal is:

> real users can register, remain isolated, understand what ZENDOC can and cannot do, and successfully complete useful workflows without hidden failures.
