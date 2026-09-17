# ZENDOC Agent Architecture

## Core Rule

The ZENDOC Core Agent coordinates workflows through permissioned tools. It does not receive unrestricted database, filesystem, deployment, billing, payment-secret, or health-record access.

ZENDOC is designed as a **multi-agent health operating ecosystem**, not one unrestricted AI doctor. Every important product domain has an explicit specialist, capability allowlist, provenance requirements and a human/clinical/owner gate where consequences become irreversible.

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
