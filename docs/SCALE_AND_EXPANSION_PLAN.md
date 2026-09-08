# ZENDOC Scale & Geographic Expansion Plan

## 1. What “large-scale ready” means

ZENDOC does not attach a fixed user count to application correctness.

The software can serve more users as infrastructure scales, but production capacity depends on:
- web CPU/RAM and worker count;
- managed PostgreSQL tier and connection limits;
- external API/provider quotas;
- upload/object-storage capacity;
- traffic pattern;
- AI-provider latency/quotas;
- real provider operations.

Use `/owner/scale-readiness` before broad rollout.

## 2. Current priority geography

### Wave A
- West Bengal
- Assam
- Uttar Pradesh

These remain the first operational geography targets because the ingestion pipeline and representative hierarchy tests already cover them.

### Wave B
After importing the official LGD States registry, enable:
- Delhi
- Kerala
- Karnataka
- Maharashtra

No Python code change is required for these states. Their official LGD state codes come from the imported States/UT snapshot.

### Wave C
Import the remaining Indian states and union territories from the same official registry and run the same state bootstrap.

## 3. India-wide hierarchy

For India, preserve official sourced relationships:

- Country
- State / Union Territory
- District
- Sub-district / Tehsil / Taluk / Revenue Circle / equivalent
- Development Block where applicable
- Gram Panchayat / rural local body
- Urban local body
- Village / locality

Do not force every state into identical naming. Store the official node type/source metadata and use relationships where administrative, block and panchayat boundaries differ.

## 4. Three different coverage layers

A state is not “live” merely because its geography is loaded.

Track separately:

### Layer 1 — Official geography
Districts, sub-districts, local bodies, villages and official codes.

### Layer 2 — Provider directory
Public official hospitals, labs, pharmacies, doctors/facilities where lawful/public data exists.

Directory presence does not mean ZENDOC verification or connectivity.

### Layer 3 — Live operational coverage
Real provider-supported:
- slots;
- stock;
- prices;
- diagnostic availability;
- acknowledgements;
- order/consultation lifecycle.

Only Layer 3 may be described as live operational coverage.

## 5. State rollout procedure

For every new Indian state:

1. import/refresh official LGD state registry;
2. preview state geography;
3. import districts;
4. import sub-districts;
5. import blocks/local bodies/panchayats;
6. import villages and mappings;
7. reconcile counts with the official snapshot;
8. ingest official provider-directory data;
9. select priority districts for provider onboarding;
10. enable live operational observations only when real providers participate;
11. review `/owner/scale-readiness` and observability before promotion.

## 6. Capacity scaling

The application uses:
- durable PostgreSQL for production;
- shared database-backed API rate limiting;
- configurable Gunicorn workers/threads;
- worker recycling;
- request and agent observability;
- readiness gates;
- idempotency/concurrency protections on consequential workflows.

The deployment should scale worker/instance count only together with database capacity and external-provider limits.

Do not increase worker count blindly on a low-memory host.

## 7. Load testing

Before a large public launch, test the actual production/staging environment rather than only unit tests.

Measure:
- requests/second;
- p50/p95/p99 latency;
- registration/login latency;
- provider search latency;
- dashboard latency;
- error rate;
- DB connection saturation;
- CPU/RAM;
- external API timeout rate;
- file-upload behavior;
- rate-limit behavior across instances.

Never use real patient data in load-test fixtures.

## 8. International expansion

Do not assume India's administrative hierarchy applies globally.

The geography import registry is country-code aware, but each new country needs:
- authoritative administrative-boundary source;
- country-specific level mapping;
- healthcare provider registries;
- privacy/data-protection review;
- emergency/medical disclaimers appropriate to the jurisdiction;
- medicine/regulatory data sources;
- local language support;
- local benefits/insurance architecture;
- country-specific external integrations.

International expansion should begin with one country at a time after India operations are stable.

## 9. Product expansion principle

Expand geographic directory coverage broadly, but expand **live operational healthcare coverage deliberately**.

A truthful system with 20 connected providers in a district is more valuable than a nationwide directory that falsely implies every listed provider has real-time ZENDOC connectivity.
