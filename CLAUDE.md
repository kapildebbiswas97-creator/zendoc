# ZENDOC — AgentFoundry / M13 Engineering Context

## Mission
Build ZENDOC into a real, production-grade healthcare company and platform. Graduate every current BETA or externally blocked capability toward a verified production state while preserving all existing WORKING capabilities. Entrepreneurship, user value, healthcare safety and long-term product quality are the primary goals; hackathons are only temporary development, tooling and visibility opportunities.

The governing tracker is GitHub issue #114: M13 — Beta Graduation, External Activation & Global Healthcare Coverage.

## Non-negotiable truth rules
- Never mark an external action complete without authoritative external evidence.
- Never fabricate provider availability, inventory, price, payment, dispatch, insurance approval, booking confirmation, delivery, identity verification, or user traction.
- Emergency safety runs before LLM/model routing.
- Models are advisory; server-side policy controls tools.
- No autonomous diagnosis, prescribing, medicine substitution, emergency dispatch, payments, permission escalation, or destructive clinical actions.
- Consequential actions require existing consent/confirmation/provider/owner/clinician gates.
- Do not read, print, commit, or expose secrets from .env or credential files.

## Stability rule
Everything already marked WORKING must stay working.
Every bug fix needs a regression test.
No merge when a known reproducible P0/P1 defect remains in the changed flow.
Production Gate must be green before merge.

## Current priority order
1. Finder reliability and source truth.
2. Report Intelligence extraction/review pipeline.
3. Voice/video + telehealth reliability and TURN/STUN verification.
4. AI runtime health, failover, multilingual evaluation and replayable evals.
5. IoT adapter standardization and provenance.
6. Fitness camera / pose-analysis adapter with non-clinical boundaries.
7. External activation: OCI/Vercel, object storage, messaging, payment, Places and partner APIs.
8. Global healthcare feature-gap coverage from the user's workbook.

## Agent architecture
Use specialized bounded agents rather than one unrestricted super-agent:
- Safety/Triage Agent
- Care Navigation Agent
- Provider Discovery Agent
- Booking/Coordination Agent
- Health Memory Agent
- Report Intelligence Agent
- Medication Safety Agent
- Pharmacy Agent
- Diagnostics Agent
- Mental Wellness Agent
- Family Care Agent
- CareFin Agent
- Telehealth Agent
- IoT Agent
- Nutrition/Fitness Agent
- Operations/Reliability Agent

Each agent must define:
- accepted intent/input schema;
- allowed tools;
- privacy/context requirements;
- risk class;
- human/provider gate;
- expected output schema;
- fallback behavior;
- audit metadata;
- eval cases.

No agent may self-grant new tools or permissions.

## Hackathon / AgentFoundry principle
- Do not reshape ZENDOC merely to fit a hackathon theme.
- Do not weaken healthcare ethics, truthfulness, safety or product architecture for judging criteria.
- Use free AgentFoundry access as engineering infrastructure to accelerate the real ZENDOC roadmap.
- Any hackathon submission must reflect genuine ZENDOC work, not a disposable demo fork.
- Winning is optional; production improvement is mandatory.
- Visibility, ecosystem access or funding are possible benefits, never assumptions or reasons to fabricate traction.

## AgentFoundry workflow
For every meaningful agent change:
1. inspect the real files before editing;
2. write or update tests first where practical;
3. make the smallest coherent patch;
4. run the relevant tests;
5. run the full ZENDOC Production Gate before merge;
6. create replayable/evaluable representative cases;
7. document any external dependency that prevents a truthful WORKING status.

Use AgentFoundry Run/Trace/Evals/Tools/Replay to capture agent behavior, especially:
- safe routing;
- provider/model failure;
- malformed structured output;
- emergency precedence;
- human approval;
- waiting_provider state;
- retry/idempotency;
- privacy/context minimization.

## Healthcare AI quality requirements
- Show provenance/freshness where information came from datasets/providers.
- Low-confidence extraction or identity matching must fail closed to review_required.
- User-entered values and model-extracted values must never be mislabeled as clinician-verified.
- Health guidance must be educational/coordination support unless authoritative licensed-provider evidence exists.
- Preserve patient/provider/tenant isolation and Health Memory access controls.

## Finder graduation criteria
- no 500/502 for ordinary upstream/source failures;
- graceful partial/degraded states;
- valid GPS/location normalization;
- deduplication;
- distance calculation only when coordinates are valid;
- source tier, provenance and freshness visible;
- no external listing promoted to ZENDOC verified/bookable without evidence;
- mobile and desktop smoke verification.

## Report Intelligence graduation criteria
Target pipeline:
upload -> type/signature validation -> extraction adapter -> structured candidates -> confidence/provenance -> patient review -> clinician/provider verification where applicable -> Health Memory.

- Never silently trust OCR/model text.
- Store extraction provider/version/source metadata.
- Keep low-confidence/ambiguous fields review_required.
- Do not diagnose from extracted results.
- Keep manually entered, extracted and clinically verified sources distinguishable.

## Calling/telehealth graduation criteria
- authenticated signaling and scoped authorization;
- device/mic/camera permission errors handled;
- reconnect/cleanup/stale-call handling;
- TURN/STUN configuration health verifier;
- two-device public-network evidence before WORKING;
- no claim of successful consultation solely from a browser call attempt.

## External activation rule
Repository code can prepare integrations but cannot manufacture:
- credentials;
- provider approval;
- regulatory approval;
- real partner inventory/slots;
- real payment settlement;
- real eKYC/ABDM confirmation;
- production TURN reachability;
- real SMTP/SMS/WhatsApp delivery;
- Play Console approval;
- real hardware/vendor telemetry.

Keep these statuses evidence-bound.

## Global coverage workbook workflow
When the workbook is added:
- treat it as the canonical feature inventory input;
- research India + global healthcare/health-AI products;
- record product/company, country, workflow, source, ZENDOC coverage, dependency type and gap;
- classify each as PRESENT / PARTIAL / MISSING / NOT-APPROPRIATE;
- turn only material missing capabilities into scoped engineering issues;
- do not copy branding, proprietary text, or unsafe clinical claims.

## Git workflow
Work only on this hackathon/M13 branch or child branches.
Do not bypass main branch release gates.
Do not merge directly into main without green CI and review of truth/safety boundaries.

## Definition of done
"Fully complete" means:
- implementation exists;
- relevant tests pass;
- full Production Gate passes;
- deployment verification passes when runtime-dependent;
- external evidence exists when external-dependent;
- zero known reproducible P0/P1 defects in the flow.

It does not mean claiming software can never contain any future bug.
