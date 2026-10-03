# ZENDOC Agent Architecture

## Core Rule

The ZENDOC Core Agent coordinates workflows through permissioned tools. It does not receive unrestricted database, filesystem, deployment, billing, payment-secret, or health-record access.

ZENDOC is designed as a **multi-agent health operating ecosystem**, not one unrestricted AI doctor. Every important product domain has an explicit specialist, capability allowlist, provenance requirements and a human/clinical/owner gate where consequences become irreversible.

## Personal Agent Layer

Every authenticated ZENDOC account now has a deterministic personal coordinator identity derived from its account id and role. Patient, doctor, hospital, pharmacy, government and configured-owner accounts receive different missions, memory scopes, proactive capabilities and specialist delegates.

The personal agent is deliberately a **coordinator, not a superuser**. It cannot widen the account's permissions. It routes work to the existing specialist fleet and every candidate tool is checked again by the Tool Registry, domain authorization, consent and approval layers. Personal context remains actor-owned or explicitly granted, minimum-necessary and provenance-preserving.

## Global Health Intelligence Fabric

ZENDOC's governed data plane represents 195 country jurisdictions without pretending every jurisdiction already has a live national feed. The source registry distinguishes country support from source maturity, and source-gap reporting tells the Research/Data workforce where authoritative discovery is still needed.

Organization intelligence begins with authoritative legal-entity/filing registries (GLEIF globally, SEC EDGAR for U.S. public filers, Companies House for the UK, and MCA official company/LLP services for India). A discovered company's official newsroom, investor-relations feed, regulatory filing stream, healthcare regulator record or authorized partner API is attached as evidence only after HTTPS, usage/terms and schema review. Company announcements never become clinical or regulatory truth merely because they are official corporate speech.

## Agent OS Coverage Contract

The product capability registry and Agent OS are now linked by an explicit coverage contract. Every declared capability must map to a registered specialist owner and may also name an internal AI-workforce owner. CI fails if a capability is added without an Agent OS mapping, if a mapping points to an unknown specialist/workforce agent, or if a stale mapping survives after a capability is removed.

Coverage modes distinguish executable specialist tools from coordination-only, integration-dependent, operations-monitored, safety-guarded and future-blocked capabilities. This prevents "Agent OS everywhere" from becoming a false claim that every feature has autonomous write authority: responsibility is universal, while execution remains permissioned and risk-bounded.

## AI Company / Backend Workforce

ZENDOC also defines an internal AI workforce: Incident, Engineering, Root Cause, Repair, Security, Test, QA, Infrastructure, Data, Integration, Product, Support, Communications, Research, Manager, Release and Knowledge agents.

The operations worker automatically converts privacy-safe failed/error platform events into deduplicated persistent incident cases. The intended pipeline is detect/classify -> reproduce in sandbox -> root cause -> repair proposal -> security review -> regression tests -> preview QA -> release evidence -> configured-owner production approval -> post-release verification -> sanitized knowledge capture.

Automation is deliberately strongest before the irreversible boundary. The workforce may analyze, retry safe work, refresh approved public data, run probes, prepare repairs/tests and verify previews automatically. It may not silently self-modify production, broaden permissions, read secrets, prescribe, dispatch emergencies, execute payments or bypass the release gate.

## Safety Order

Authenticated command -> deterministic Safety Agent -> bounded planner -> privacy-aware Model Router -> specialized agent -> permissioned tool registry -> bounded-autonomy policy -> approval gate where required -> deterministic executor -> persistent task/event/audit -> user-facing result.

Emergency detection runs before ordinary agent routing and never waits for complex chains.

## Agent Registry

- Safety Agent
- Care Agent
- Provider Discovery Agent
- Booking Agent
- Doctor/Telehealth Agent
- Communication Agent
- Health Memory Agent
- Prevention Agent
- Life-stage Continuity Agent
- Family Care Agent
- Fitness Agent
- Nutrition Agent
- Health Learning Agent
- Video Intelligence Agent
- Pharmacy Agent
- Diagnostics Agent
- Health Commerce Agent
- CareFin Benefits Agent
- Home Health Agent
- Transport Agent
- IoT Agent
- Operations Agent
- Model Improvement Agent

These names are internal responsibility boundaries. They are **not** claims that a third-party booking, merchant, insurer, payment, browser, transport, emergency or device integration exists.

## Bounded Autonomy / “AGI-like” Operation

ZENDOC may autonomously perform reversible work inside a registered tool allowlist:

1. understand an intent;
2. plan a bounded workflow;
3. search authenticated/connected sources;
4. read permitted data;
5. compare truthful options;
6. change search parameters or dates;
7. summarize and explain;
8. retry safe read-only failures;
9. prepare/stage an action;
10. stop at the appropriate human or professional gate.

This provides the useful behavior associated with browser/task agents without granting an LLM unrestricted computer authority.

### Consequential actions

Booking, rescheduling/cancellation, order submission, record sharing, paid-service activation and permission changes require fresh explicit confirmation and a deterministic server-side executor. The model may prepare a preview but may not silently finalize the action.

Payment is a harder boundary: an agent may prepare a checkout or external handoff, but a model does not execute payment and must never receive CVV, UPI PIN, banking passwords or equivalent payment secrets.

### Clinical actions

Diagnosis, prescribing, medicine substitution, dose/frequency/form changes and autonomous emergency dispatch are outside general model authority. Qualified clinical or deterministic emergency workflows retain control.

## Booking Agent

The Booking Agent can search provider options automatically. For connected ZENDOC providers it may read provider-published schedules and current slot/hold state through `get_provider_booking_options`. External/public listings remain discovery-only and cannot be promoted to connected availability.

`confirm_provider_booking` is consent-required. The ordinary autonomous plan executor refuses to execute consent-required tools, so an appointment cannot be finalized merely because a model produced a tool call. The existing provider service revalidates verification and slot availability before an appointment request is persisted.

## Health Commerce Agent

The Health Commerce Agent currently uses ZENDOC's truthful commerce-discovery layer. Merchant results are external search/catalog handoffs only. Current stock, price, seller suitability, affiliate/referral relationship, delivery, order state and payment connectivity are not inferred.

Medicine queries stay in the Pharmacy/Medication Safety path rather than general commerce. Commercial sponsorship/revenue must never change clinical ranking or care recommendations.

## Prevention & Life-stage Continuity

The Prevention Agent and Life-stage Continuity Agent can only use authorized minimum-necessary Health Memory context. They do not infer pregnancy, fertility, postpartum, menopause or other sensitive states from age/gender/model guesses. Sensitive life-stage journeys must be explicitly selected by the user (or authorized guardian where applicable).

Exact newborn/infant stage calculations should use date of birth when available rather than a coarse integer age.

## Health Learning Agent

The Health Learning Agent creates educational journeys and may use truthful configured video/resource discovery. Education is kept separate from diagnosis and treatment. Missing providers/citations/videos are reported as unavailable rather than fabricated.

## Model Improvement Agent

“Self-improvement” is intentionally implemented as **offline proposal + evaluation**, not autonomous production self-modification.

The Model Improvement Agent may, inside the existing no-tools evaluation boundary:
- propose prompt candidates;
- propose model-routing candidates;
- propose model candidates;
- run and score bounded offline/synthetic evaluations;
- compare results and prepare an owner review report.

It cannot:
- rewrite production code or safety policy;
- broaden its own tool permissions;
- read/create secrets;
- disable safety or audit;
- self-promote a model/prompt/routing configuration;
- deploy to production.

Promotion is a deterministic, configured-owner-controlled workflow after evaluation evidence is reviewed.

## Communication Tool Layer

The Core Agent delegates communication actions through strictly validated tools:
- `tool_find_contact`: Discovers permitted contacts with privacy filtering.
- `tool_check_communication_permission`: Checks central policy matrix.
- `tool_start_conversation`: Establishes permissioned threads.
- `tool_send_message`: Sends messages and triggers receipts/notifications.
- `tool_request_doctor_chat`: Evaluates doctor message policy and consultation requirements.
- `tool_request_voice_call` / `tool_request_video_call`: Evaluates calling permissions.
- `tool_share_video`: Attaches educational videos with truthfulness disclosures.
- `tool_share_report_with_consent`: Enforces owner or family consent before attaching health records.

## Tool Controls

Every tool must enforce authentication, authorization, ownership, consent, validation and audit logging. High-impact operations require explicit confirmation and must not be executed autonomously.

The M8 executor has no generic shell, SQL, Python, filesystem, database, browser-control, credential, payment or command tool. Missing handlers fail closed. Plans are limited to 20 steps and synchronous request execution is bounded. See [Milestone 8](MILESTONE8.md) for the live agent/tool/task/approval architecture.

A future browser/operator connector must therefore be a separately authenticated capability with site-specific permissions and deterministic action gates. Merely having an LLM or browser window does not grant ZENDOC permission to log in, book, purchase or pay on a third-party service.

## Jev / System One Decision Layer

ZENDOC supports an optional Jev-compatible System One decision layer between
the deterministic plan and specialist execution. The role of Jev is narrow and
machine-oriented: make typed control decisions such as PROCEED, ASK_HUMAN,
ESCALATE or STOP for work that has already passed ZENDOC's deterministic
authorization and safety policy.

The decision layer is intentionally subordinate to the existing control plane:

- deterministic emergency/safety checks always run first;
- Jev never receives credentials or unrestricted tool access;
- Jev cannot make a blocked action executable;
- explicit booking/order/record-sharing/payment/permission gates remain intact;
- clinical authority remains with qualified clinicians and deterministic policy;
- low-confidence Jev output narrows automation instead of broadening it;
- provider failure falls back to the existing deterministic bounded policy;
- metadata-only mode is the default, so raw user text is not sent to an external
  decision provider;
- health-sensitive/high-risk text requires both a private-verified trust mode
  and the separate `ZENDOC_JEV_ALLOW_HEALTH_TEXT=true` operator opt-in;
- a private verified Jev-compatible endpoint can be configured separately when
  the operator has established the required privacy/compliance boundary.

Each Fleet Agent keeps its own mission, inputs, outputs, deterministic checks,
human gates and forbidden actions. The Jev question is built from that
specialist profile rather than giving one generic model universal authority.

This yields the runtime pattern:

deterministic Safety -> deterministic planner -> specialist profile ->
optional Jev typed control decision -> permissioned tools -> deterministic
executor -> verification -> event/audit -> longitudinal memory.

Jev complements rather than replaces the LLM/SLM layer. Jev is used for
bounded routing/control judgments; LLM/SLM models remain appropriate for
language generation, explanation and open-ended reasoning.

## Runtime resilience and observability

The bounded executor now gives idempotent **READ_ONLY** tools one additional
attempt for transient timeout/provider-connectivity failures. Non-idempotent
writes, consent-required actions, clinician-gated actions and other consequential
operations are never automatically retried by this path.

Each specialist execution receives a correlation/run id and emits privacy-safe
plan/tool events on a best-effort basis. Raw provider exceptions, credentials,
prompts and health content are not returned as orchestration diagnostics.
When an authorized read source remains temporarily unavailable after the bounded
retry, the specialist workflow returns a truthful `degraded` state plus its
configured fallback strategy instead of inventing data or silently completing.
Authorization and human gates still fail closed.

## Model Router

Emergency safety and deterministic-only tasks run before model selection. For allowed low-risk tasks, configured local inference is preferred before explicitly approved cloud inference; deterministic fallback is always available. `HEALTH_SENSITIVE` and `HIGH_RISK` content is never sent to cloud, while `PERSONAL` cloud routing requires consent. Provider configuration never grants permissions and model output never exposes or invokes agent tools directly. Strict structured output is validated before any later planning, permission, approval or execution stage. Routing logs contain metadata only, not prompts, responses, credentials or hidden reasoning.

Ollama and OpenAI-compatible local adapters are implemented as beta capabilities. Runtime status is checked against the real server and model inventory; without an installed/running configured model the truthful status remains **Integration Required** or **Unavailable**. See [Milestone 8.1](MILESTONE8_1.md).

## Model Evaluation Boundary

The M8.2 Model Evaluation Lab tests language-model advisory output outside the agent executor. Synthetic prompts can contain hostile requests, but the evaluation adapter exposes no tools, permissions, arbitrary endpoint, SQL, shell or filesystem capability. Output is treated as untrusted data, strictly validated and scored, then persisted only as metadata and hashes. It cannot create an agent task or bypass the deterministic safety, owner, consent, approval and tool controls described above.

Dry run and mock are the defaults. Real-local evaluation requires a separate default-off environment gate and explicit two-step owner confirmation, uses the existing M8.1 local-provider boundary, and remains bounded to one candidate/call at a time with no retries. See [Milestone 8.2](MILESTONE8_2.md) and the [ZENDOC-SLM roadmap](ZENDOC_SLM_ROADMAP.md).

## Owner Authority

Admin means the single environment-configured ZENDOC owner. Public registration and self-promotion are blocked. Every privileged route, API, approval, alert, task and tool checks the configured owner identity server-side.

## Memory Boundaries & Admin Privacy

ZENDOC separates patient health memory, conversation memory, operational memory, agent memory and audit history.
- The **Admin Agent Command Center** displays aggregate operational metrics, service counts and task queues.
- **Privacy Boundary**: Admins do not casually gain access to read private patient-doctor clinical chat messages unless granted explicit support authorization.
