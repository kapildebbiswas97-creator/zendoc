# Milestone 8.2: Base Model Evaluation Lab and ZENDOC-SLM Foundation

## Scope

Milestone 8.2 adds a provider-neutral, owner-only framework for evaluating possible open-weight base models against a small, versioned, synthetic ZENDOC test set. It does not train, fine-tune, download, bundle, certify, or select a production model. No model is evaluated automatically at startup or by automated tests.

Ollama is a model runtime: it loads and serves separately obtained models. It is not a ZENDOC model. Likewise, the current `phi4-mini:3.8b` entry is a development baseline candidate, not ZENDOC intellectual property, a medical model, or a declared winner.

An agentic system and a language model are different layers. A language model proposes text or structured advisory output. The ZENDOC agentic system owns deterministic safety, authentication, authorization, consent, planning, permissioned tools, approvals, execution, and audit. Evaluation output is never allowed to execute tools.

## Architecture

```text
Owner Evaluation Lab
  -> fixed candidate registry
  -> fixed, versioned synthetic dataset
  -> dry-run | mock | explicitly confirmed real-local runner
  -> deterministic validators and scoring
  -> safety disqualification gate
  -> optional process-level resource observation
  -> metadata-only persistence
  -> multi-dimensional comparison and readiness report
  -> human review before any model decision
```

The runner uses the M8.1 `SLMProvider` interface for real-local calls. It inherits the configured local provider endpoint and does not accept a URL, filesystem path, arbitrary model identifier, or credentials from an HTTP request.

## Candidate Registry

`zendoc/model_candidates.py` owns a fixed, validated registry. Entries include:

- stable model ID and display name;
- family, parameter class, and quantization;
- provider and exact local runtime model name;
- license name and reference, with upstream verification status;
- context window and structured/tool-output notes;
- multilingual, hardware, intended-use, and medical-claim notes;
- evaluation enablement and development-baseline flags.

Only explicitly enabled entries can be run. Candidate and local model identifiers are restricted to a conservative character set; traversal-like identifiers and caller-created candidates fail closed. Phi, Qwen, Gemma, and Llama family entries are registry metadata only. M8.2 downloads none of them and makes no unverified license, multilingual, clinical, or performance claims.

## Dataset and Governance

The repository-owned `evaluation_data/zendoc_eval_v1.json` is loaded from a fixed path and validated before use. It contains synthetic examples only and covers:

- platform knowledge;
- intent understanding;
- structured output;
- summarization;
- multilingual/Indian-user communication;
- bounded agent-planning assistance;
- hallucination resistance;
- healthcare safety;
- privacy;
- prompt injection.

Each case records an ID, category, prompt, synthetic context, privacy class, expected behavior, required and forbidden concepts, structured schema, risk level, deterministic-handling requirement, critical rules, human-review dimensions, and notes. Dataset metadata records name, version, provenance/license statement, allowed use, PHI/PII status, and quality/safety review status. Validation rejects a dataset that is not explicitly synthetic, contains disallowed identifier markers, omits governance, duplicates case IDs, or violates bounded fields.

These examples are for evaluation framework development only. They are not training data, medical advice, patient records, or evidence of clinical validation.

## Scoring and Human Review

Machine-checkable scoring covers:

- JSON/schema validity, including unexpected fields;
- required and forbidden content;
- instruction following and selected grounding signals;
- model-generated action/tool structures;
- emergency, prescribing, privacy, credential, and Admin-boundary failures;
- timeout, provider failure, latency, and run failure rates.

The summary retains separate safety, capability, and efficiency scores plus category-level signals. Multilingual quality and other subjective dimensions can remain unscored until a human reviews them. A response hash supports result identity without persisting the response itself.

Human-review scores are bounded to 0-100. Notes are length-limited and rejected if they resemble common credential formats. A human score supplements rather than overrides deterministic critical-safety failures.

## Safety Gate and Readiness

Case and run safety states are `PASS`, `CONDITIONAL`, `FAIL`, or `DISQUALIFIED` (with `NOT_EVALUATED` for a dry plan). Critical failures disqualify a run, including:

- emergency-safety bypass;
- autonomous diagnosis or prescribing behavior;
- model-generated tool execution that bypasses policy;
- credential or secret leakage;
- Admin privilege escalation;
- privacy-boundary violation;
- prompt-injection boundary failure.

Comparison applies the critical safety gate first, then safety status, capability, and efficiency/resource suitability. Mock and dry runs are never eligible recommendations. A real-local result can be reported as an eligible leader for human review, never an automatic winner.

Readiness labels are `NOT READY`, `BASE MODEL CANDIDATE`, `ADAPTATION CANDIDATE`, and `REJECTED`. They describe evaluation evidence only. They do not convert an upstream model into a proprietary ZENDOC model.

## Laptop-Safe Execution

The default is dry run or mock. Automated tests use mocks and never contact Ollama. Real-local evaluation requires all of the following:

1. the environment gate `ZENDOC_MODEL_EVALUATION_REAL_ENABLED=true`;
2. an authenticated session belonging to the environment-configured owner;
3. an enabled fixed registry candidate;
4. the owner-only prepare route;
5. a short-lived, one-time session token bound to that candidate and limits;
6. the exact confirmation phrase on a second form.

The API deliberately refuses real-local mode. Runs are sequential with concurrency fixed at one, no automatic retries, at most 20 cases, at most 256 output tokens per case, at most 30 seconds per call, and at most a 2-second cooldown. The runner checks a persistent stop request between cases and continues safely after categorized provider errors or timeouts.

Optional resource observation samples only the current ZENDOC Python process when an already-installed `psutil` is available. It does not probe or stress a GPU. Missing metrics are explicit. `SAFE`, `CAUTION`, and `NOT_RECOMMENDED` are conservative workload suitability labels, not hardware-damage diagnoses.

## Persistence and Privacy

M8.2 adds additive SQLite structures:

- `model_candidates`;
- `evaluation_case_versions`;
- `model_evaluation_runs`;
- `model_evaluation_results`.

Stored records contain candidate/dataset identity, immutable metadata snapshots, bounds, status, scores, latency, categorized failures, resource observations, response hashes, and optional human review. They do not contain raw prompts, model responses, hidden chain-of-thought, provider credentials, or medical records. The fixed synthetic dataset remains version-controlled instead of being copied into result rows.

Catalog seeding is idempotent and startup-safe. It adds evaluation metadata without changing existing user, health, owner, M8, or M8.1 data. No evaluation runs at startup.

## Owner Lab and APIs

The owner interface is `/admin/model-evaluation`. Normal users and non-owner staff receive 403. The owner can inspect candidate metadata, dataset governance/categories, prior runs, safety/readiness, component scores, failures, latency, resource class, and comparison results.

Owner bearer-token APIs provide read access and dry/mock execution only:

- `GET /api/v1/admin/model-evaluation`
- `POST /api/v1/admin/model-evaluation/runs`
- `GET /api/v1/admin/model-evaluation/runs/{run_id}`

All privileged actions use the existing environment-bound owner check and audit trail. The Evaluation Lab introduces no generic model, endpoint, SQL, shell, filesystem, or tool-execution API.

## Security Review

- Prompt injection is treated as test content, never as instruction to ZENDOC.
- Model output is parsed as untrusted data and cannot invoke agent tools.
- Candidate IDs are fixed and validated; arbitrary local model names are rejected.
- The provider URL comes only from existing M8.1 configuration and remains subject to its local/private-network policy; evaluation routes cannot select an endpoint, preventing an evaluation-specific SSRF surface.
- SQL uses parameter binding; case/run/result IDs are bounded or converted to integers.
- Dataset loading uses one fixed repository path; no request controls filesystem access.
- Owner web and API controls use existing server-side owner authorization.
- Raw prompts/responses and secrets are not written to result tables or audit events.
- Strict structured validation rejects excess nesting, excess list size, invalid types, and forbidden action keys.
- Schema migration is additive and compatible with an M8.1 database.

## Manual Real-Local Procedure

Only perform this after automated verification and a human safety review:

1. Install/download nothing as part of ZENDOC. Separately verify that the intended local runtime and exact registry model already exist.
2. Configure the M8.1 `ZENDOC_LOCAL_AI_*` values for that local runtime. Keep private-network access disabled unless a separately reviewed local deployment needs it.
3. Set `ZENDOC_MODEL_EVALUATION_REAL_ENABLED=true` only for the planned session.
4. Start ZENDOC and sign in as the environment-configured owner.
5. Open `/admin/model-evaluation`, choose one enabled candidate, and keep conservative defaults for the first run.
6. Select **Prepare Real Local Evaluation**, review the bound candidate and limits, then type the exact confirmation phrase on the second page.
7. Monitor the laptop and stop before the next case if responsiveness or temperature is concerning. ZENDOC does not diagnose hardware safety.
8. Review critical failures and raw behavior directly at the runtime if needed; do not paste secrets or real patient data into the lab.
9. Record bounded human-review scores only after reviewing language and domain quality.
10. Disable `ZENDOC_MODEL_EVALUATION_REAL_ENABLED` after the session and use the runtime's documented stop/unload controls if desired.

## Capability Matrix

| Capability | Status | Boundary |
|---|---|---|
| Registry, dataset validation, dry run, mocked evaluation | WORKING | Synthetic and bounded |
| Deterministic scoring, safety gate, persistence, comparison | WORKING | Framework evidence, not clinical validation |
| Owner Evaluation Lab | BETA | Manual review required |
| Real local evaluation | INTEGRATION REQUIRED | Default-off; requires existing runtime/model and explicit owner confirmation |
| Candidate performance results and base-model selection | INTEGRATION REQUIRED | No real benchmark has been run by M8.2 automation |
| Adapted ZENDOC-SLM v0.x | FUTURE | Requires governed data, adaptation, independent evaluation, and approvals |
| Clinical certification or autonomous diagnosis/prescribing | FUTURE | Not implemented or claimed |

