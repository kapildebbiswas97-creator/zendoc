# ZENDOC Agent Architecture

## Core Rule

The ZENDOC Core Agent coordinates workflows through permissioned tools. It does not receive unrestricted database, filesystem, deployment, billing, or health-record access.

## Safety Order

Authenticated command -> deterministic Safety Agent -> bounded planner -> privacy-aware Model Router -> specialized agent -> permissioned tool registry -> approval gate where required -> bounded executor -> persistent task/event/audit -> user-facing result.

Emergency detection runs before ordinary agent routing and never waits for complex chains.

## Agent Registry

- Care Agent
- Doctor/Telehealth Agent
- Communication Agent (permissioned messaging, contact discovery, record/video sharing)
- Fitness Agent
- Operations Agent
- Family Care Agent
- Pharmacy Agent
- Transport Agent
- Home Health Agent
- IoT Agent
- Video Intelligence Agent
- Safety Agent

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

Every tool must enforce authentication, authorization, ownership, consent, validation, and audit logging. High-impact operations (such as record sharing or irreversible deletions) require explicit confirmation and must not be executed autonomously.

The M8 executor has no generic shell, SQL, Python, filesystem, database, or command tool. Missing handlers fail closed. Plans are limited to 20 steps and synchronous request execution is bounded. See [Milestone 8](MILESTONE8.md) for the live agent/tool/task/approval architecture.

## Model Router

Emergency safety and deterministic-only tasks run before model selection. For allowed low-risk tasks, configured local inference is preferred before explicitly approved cloud inference; deterministic fallback is always available. `HEALTH_SENSITIVE` and `HIGH_RISK` content is never sent to cloud, while `PERSONAL` cloud routing requires consent. Provider configuration never grants permissions and model output never exposes or invokes agent tools directly. Strict structured output is validated before any later planning, permission, approval, or execution stage. Routing logs contain metadata only, not prompts, responses, credentials, or hidden reasoning.

Ollama and OpenAI-compatible local adapters are implemented as beta capabilities. Runtime status is checked against the real server and model inventory; without an installed/running configured model the truthful status remains **Integration Required** or **Unavailable**. See [Milestone 8.1](MILESTONE8_1.md).

## Model Evaluation Boundary

The M8.2 Model Evaluation Lab tests language-model advisory output outside the agent executor. Synthetic prompts can contain hostile requests, but the evaluation adapter exposes no tools, permissions, arbitrary endpoint, SQL, shell, or filesystem capability. Output is treated as untrusted data, strictly validated and scored, then persisted only as metadata and hashes. It cannot create an agent task or bypass the deterministic safety, owner, consent, approval, and tool controls described above.

Dry run and mock are the defaults. Real-local evaluation requires a separate default-off environment gate and explicit two-step owner confirmation, uses the existing M8.1 local-provider boundary, and remains bounded to one candidate/call at a time with no retries. See [Milestone 8.2](MILESTONE8_2.md) and the [ZENDOC-SLM roadmap](ZENDOC_SLM_ROADMAP.md).

## Owner Authority

Admin means the single environment-configured ZENDOC owner. Public registration and self-promotion are blocked. Every privileged route, API, approval, alert, task, and tool checks the configured owner identity server-side.

## Memory Boundaries & Admin Privacy

ZENDOC separates patient health memory, conversation memory, operational memory, agent memory, and audit history.
- The **Admin Agent Command Center** displays aggregate operational metrics, service counts, and task queues.
- **Privacy Boundary**: Admins do not casually gain access to read private patient-doctor clinical chat messages unless granted explicit support authorization.


## M12.5 Agentic Care OS

ZENDOC AI now has an explicit bounded Agentic Care lifecycle:

**OBSERVE → UNDERSTAND → PLAN → ACT → VERIFY → REMEMBER**

This lifecycle is implemented by `zendoc/agentic_care.py` and reuses the existing
deterministic Safety Engine, Core Agent planner, permissioned Tool Registry,
bounded executor, task engine, approval gates, and audit/event memory.

Autonomy is expressed as a truthful per-run level:

- **L0 SAFETY OVERRIDE** — emergency guidance; no autonomous clinical action.
- **L2 PLAN OR GUIDE** — the agent understands and plans but has no safe tool step to execute.
- **L3 SAFE AUTONOMY** — bounded read-only or low-risk permissioned steps execute automatically.
- **L4 CONFIRM AND ACT** — consequential work is staged and waits for explicit human confirmation.

The model router never receives direct tool authority. Models may assist with
advisory language tasks, but deterministic policy, actor permissions, consent,
approval state, and tool handlers remain authoritative.

The product must not describe this as unrestricted autonomy. ZENDOC is agentic
because it can plan, execute permitted steps, verify state, and persist audit
memory — while refusing actions outside its evidence, integration, consent, or
clinical authority boundaries.
