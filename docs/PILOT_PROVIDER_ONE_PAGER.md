# ZenDoc Nexus — Provider Pilot One-Pager

## What ZenDoc is

ZenDoc Nexus is a healthcare coordination and execution platform designed to help patients, providers and healthcare organizations complete practical care workflows through one trusted system.

The pilot focuses on useful daily work, not futuristic architecture presentations.

## For doctors

ZenDoc can help manage:
- appointments and patient requests;
- patient communication;
- patient-authorized records;
- follow-ups;
- care-journey tasks;
- schedules;
- notifications;
- telehealth entry where configured;
- basic operational analytics.

What ZenDoc does **not** do:
- autonomous diagnosis;
- autonomous prescribing;
- claim professional verification without evidence/review;
- claim that an external action succeeded without authoritative acknowledgement.

## For pharmacies

ZenDoc can help manage:
- prescription-linked medicine requests;
- request queues;
- accept / reject / pending states;
- customer communication;
- fulfilment status;
- service coverage.

ZenDoc does not fabricate:
- live inventory;
- medicine availability;
- price;
- fulfilment;
- provider acceptance.

A request becomes authoritative only when the pharmacy/system of record acknowledges it.

## For diagnostic labs

ZenDoc can help manage:
- test/service catalogue;
- incoming diagnostic requests;
- appointment/status lifecycle;
- report linking;
- follow-up;
- freshness/provenance information.

ZenDoc will distinguish stored/directory information from connected or live-confirmed states.

## For clinics and hospitals

ZenDoc can help connect:
- discovery;
- appointments;
- patients;
- providers;
- communication;
- care journeys;
- patient-authorized records;
- operational tasks;
- basic analytics.

The first pilot is a practical coordination layer. It is not intended to replace an entire hospital information system on day one.

## Verification and trust states

Provider/organization information may appear as:
- self-submitted;
- evidence submitted;
- under review;
- verified;
- integration connected.

Healthcare discovery may show states such as:
- VERIFIED;
- PUBLIC DIRECTORY;
- CONNECTED;
- LIVE CONFIRMED;
- STALE;
- UNKNOWN;
- INTEGRATION REQUIRED.

These labels are designed to prevent directory data from being mistaken for live operational truth.

## How the pilot works

1. We onboard a small controlled cohort.
2. You configure the minimum profile, services and schedules needed for testing.
3. Real users attempt realistic healthcare tasks.
4. You receive and respond to supported requests.
5. ZenDoc measures workflow completion, response time, failures and product feedback.
6. We review what saved time, what created extra work and what integration is genuinely required.

## What we want to learn from you

- Which task saved you time?
- Which task created extra work?
- What workflow is still missing?
- What information would you not trust AI to handle?
- What would make ZenDoc useful every day?
- What would you pay for if the product consistently delivered that value?
- Which existing software or operational process must ZenDoc integrate with?

## Data and safety boundary

ZenDoc applies identity, authorization, consent, privacy, purpose limitation, minimum-necessary data, human approval and audit controls.

AI/agents must not bypass those controls or directly claim consequential external actions succeeded without authoritative confirmation.

Pilot analytics are aggregate operational/product signals. They are not evidence of clinical efficacy.

## Pilot status

The product should be presented as **Production Pilot / Beta** until the required release, deployment, security and integration checks are verified.

External dependencies are reported truthfully as:
- NOT CONFIGURED;
- CONFIGURED;
- REACHABLE;
- VERIFIED;
- PRODUCTION VERIFIED.

If a connector cannot yet be activated because credentials, contracts or authorization are unavailable, ZenDoc can still complete the software adapter, tests, error handling and verification tooling without pretending the integration is live.

## Pilot contact / next step

The immediate next step for a participating doctor, pharmacy, lab, clinic or hospital is a short workflow review and controlled onboarding into the relevant pilot cohort.

**Goal: prove that ZenDoc reduces friction in real healthcare coordination while preserving trust, safety and human authority.**
