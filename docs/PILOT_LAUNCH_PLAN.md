# ZenDoc Nexus Controlled Pilot Launch Plan

## Purpose

Move ZenDoc Nexus from software-complete feature work into a controlled, measurable real-user pilot without changing the product vision or overstating external readiness.

Operating sequence:

**STABILIZE -> VERIFY -> DEPLOY -> PILOT -> MEASURE -> IMPROVE**

ZenDoc remains a healthcare intelligence, trust, orchestration and execution operating system. The pilot exists to prove that real people can complete real, safe healthcare workflows.

## Pilot scope

### Consumer pilot

Validation target: **20-50 initial users**.

Primary journeys:
- register and accept policies;
- sign in and maintain a session;
- use Find Care with current-location or manual-location fallback;
- inspect trustworthy provider/facility results and provenance;
- start a care journey;
- request an appointment or provider action where supported;
- use Health Memory and reports within consent boundaries;
- use messages/calls only where the corresponding channel is actually available;
- use Mental Wellness as a non-diagnostic guidance surface;
- give feedback or report a problem.

### Provider pilot

Validation target: **3-5 doctors/providers**.

Primary journeys:
- provider onboarding;
- profile and evidence submission;
- verification-state visibility;
- schedule management;
- appointment/request queue;
- patient-authorized record access;
- messaging/telehealth entry where configured;
- follow-up and care-journey tasks;
- notifications;
- basic operational analytics.

Verification labels must remain truthful:
- self-submitted;
- evidence submitted;
- under review;
- verified;
- integration connected.

### Pharmacy / lab pilot

Validation target: **2-3 partner locations**.

Pharmacy flows:
- onboarding and location;
- service coverage;
- prescription-linked medicine request queue;
- accept / reject / pending;
- fulfilment status;
- authoritative acknowledgement.

Lab flows:
- onboarding;
- service/test catalogue;
- test request;
- appointment/status lifecycle;
- report linking;
- freshness/provenance;
- completion acknowledgement.

No live inventory, price, availability, verification or fulfilment may be fabricated.

### Clinic / small hospital pilot

Validation target: **1 clinic or small hospital if obtainable**.

Pilot layer:
- organization profile and locations;
- services and providers;
- schedules;
- request/appointment queue;
- operational tasks;
- patient-authorized records;
- messaging;
- basic analytics.

Do not attempt to replace the institution's full HIS/EMR during this pilot.

## Pilot release channel

Use an explicit controlled-beta mode such as:

`ZENDOC_RELEASE_CHANNEL=pilot`

Pilot UI and owner tools should distinguish:
- connected;
- unconnected;
- experimental;
- demo/simulated.

Synthetic/demo data must remain isolated from live pilot data, and demo actions must never hit live connectors.

## Pre-pilot release gate

Do not invite external pilot users until the exact release commit passes:

- compile/import checks;
- targeted regressions;
- full SQLite suite;
- PostgreSQL readiness and migration checks;
- authorization tests;
- IDOR tests;
- CSRF tests;
- production gate;
- deployment identity verification;
- public-launch verification;
- mobile smoke tests;
- desktop smoke tests.

Launch-critical patient journeys need regression coverage.

## Find Care P0/P1 pilot gate

Before each pilot wave, verify:

- current-location detection;
- permission-denied state;
- location fallback;
- manual location;
- state/district/sub-district/block/village/locality search;
- hospital/clinic/doctor/lab/pharmacy search;
- public and private facilities;
- malformed queries and typo tolerance;
- empty results;
- upstream timeout handling;
- stored/official fallback;
- OSM/Nominatim fallback where enabled;
- Google Places adapter only if configured;
- deduplication;
- source provenance;
- freshness;
- distance calculation;
- mobile rendering.

Truth states:
- VERIFIED;
- PUBLIC DIRECTORY;
- CONNECTED;
- LIVE CONFIRMED;
- STALE;
- UNKNOWN;
- INTEGRATION REQUIRED.

A third-party provider failure must degrade gracefully rather than take down Find Care.

## Recruitment and outreach workflow

1. Build a small named cohort rather than opening unrestricted public access.
2. Explain that ZenDoc is in a controlled production-pilot/beta stage.
3. Explain which integrations are connected and which are not.
4. Obtain required account/policy/consent acceptance.
5. Assign pilot tags in owner administration.
6. Give the participant one or two realistic tasks, not a scripted demo.
7. Record completion, failure, latency and feedback.
8. Review severe issues before expanding the cohort.

Suggested cohort tags:
- Pilot-Patient-01;
- Doctor-Pilot;
- Pharmacy-Pilot;
- Lab-Pilot;
- Clinic-Pilot.

## Onboarding

### Patient
- account creation;
- consent/policy orientation;
- Find Care walkthrough;
- Health Memory boundaries;
- how to report wrong information or a broken flow;
- emergency disclaimer and escalation boundaries.

### Provider / organization
- identity/profile setup;
- evidence submission;
- verification-state explanation;
- schedule/service configuration;
- queue/request handling;
- consent-bound record access;
- acknowledgement expectations;
- incident and support contact.

## Training

Keep training task-based and short.

Patients should understand:
- how to find care;
- how to distinguish directory information from live-confirmed information;
- how to request help;
- how to give feedback.

Providers/organizations should understand:
- where requests arrive;
- what requires explicit acknowledgement;
- what ZenDoc does not infer on their behalf;
- how to correct schedules/service information;
- how to report integration or workflow problems.

## Feedback cadence

For the first cohort:
- capture in-product feedback after important journeys;
- review critical/severe issues daily;
- review lower-severity issues at least twice per week;
- conduct a short qualitative check-in after the participant completes multiple real tasks.

Do not store unnecessary health information in feedback.

## Responsible ownership

Founder/owner responsibilities:
- pilot invitations and cohort approval;
- external partner permission;
- release go/no-go;
- incident escalation;
- verification decisions that require human authority.

Engineering/operations responsibilities:
- CI/release checks;
- deployment verification;
- error monitoring;
- data freshness;
- integration readiness;
- regression fixes;
- measurement.

## Success criteria

Primary:
- successful trusted care journeys;
- users completing a useful healthcare action;
- repeat usage.

Secondary:
- Find Care useful-result rate;
- search failure/no-result rate;
- appointment/request conversion;
- provider response time;
- provider response rate;
- completed follow-ups;
- D7/D30 retention only when enough real cohort history exists;
- feedback severity;
- bug rate;
- integration failure rate;
- stale-data rate.

Unknown values stay unknown; they must not be converted to zero.

## Pilot feedback questions

### Patients
- What did you try to do?
- Did you complete it?
- Where did you get stuck?
- Was the information trustworthy?
- Would you use ZenDoc again?
- What feature mattered most?

### Doctors/providers
- Which task saved time?
- Which task created extra work?
- What workflow is still missing?
- What information would you not trust AI to handle?
- What would make you use ZenDoc every day?
- What would you pay for?

### Pharmacy/lab
- Did incoming requests contain enough information?
- Was accept/reject simple?
- Which existing software/process would ZenDoc need to work with?
- What real integration is required before production use?

## Incident escalation

Severity guidance:

### Critical
- unauthorized health-data access;
- auth bypass;
- cross-tenant/IDOR exposure;
- incorrect claim that a consequential external action succeeded;
- unsafe clinical execution;
- payment/identity secret exposure.

Action: stop the affected flow, preserve audit evidence, restrict access and require owner/security review before resuming.

### High
- repeated 500/502 on a core journey;
- incorrect provider/facility state;
- broken appointment acknowledgement;
- consent-boundary failure;
- severe mobile usability blocker.

Action: pause the affected cohort journey and repair before expansion.

### Medium / Low
- recoverable UI issue;
- confusing wording;
- non-critical analytics/reporting issue;
- feature request.

Action: triage through the normal feedback backlog.

## Privacy handling

- minimum-necessary data only;
- no raw clinical text in product analytics;
- no unnecessary health information in feedback;
- owner aggregate views must not expose sensitive health content unless specifically authorized and required;
- preserve consent, purpose limitation, tenancy, audit and human-approval boundaries;
- external providers receive only data necessary for the authorized workflow.

## Pilot exit criteria

A pilot wave may expand only when:
- no unresolved critical safety/privacy/security defects exist;
- core Find Care/auth flows are stable;
- production gate is green on the deployed commit;
- deployment identity and persistence are verified;
- severe feedback is below the team's agreed tolerance;
- external integration states are truthfully represented.

A pilot may graduate toward broader beta only after real usage demonstrates repeatable completion of useful healthcare workflows.

## External integration status rule

Every external dependency must be reported as one of:

- NOT CONFIGURED;
- CONFIGURED;
- REACHABLE;
- VERIFIED;
- PRODUCTION VERIFIED.

If credentials/contracts/authorization are unavailable, complete the software adapter, tests, mocks, error handling, documentation and verification tooling, then mark it **INTEGRATION_REQUIRED**.

Potential dependencies include ABDM/ABHA/HFR/HPR/UHI/NHCX/LGD, maps, Razorpay, object storage, TURN/STUN, email/SMS/WhatsApp/push, eKYC, pharmacy/lab/logistics/hospital/insurer connectors and device SDKs.

## Commercial learning during pilot

Do not force payment during initial validation.

Capture evidence for:
- free consumer essential layer;
- optional future premium family/automation/storage/wellness value;
- provider SaaS needs;
- institution/multi-location needs;
- genuine transaction workflows;
- B2B/B2B2C demand.

Payment, referral or commercial incentives must never override medical relevance or emergency/safety ranking.

## Final pilot principle

**Do not optimize the pilot for screenshots. Optimize it for real users completing real, safe, measurable healthcare work.**
