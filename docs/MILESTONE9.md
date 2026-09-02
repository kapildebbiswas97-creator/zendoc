# ZENDOC M9 — Experience 2.0 and ZENDOC-SLM v1

M9 introduces the product-facing ZENDOC-SLM v1 layer while preserving the M8.1 provider adapters and M8.2 evaluation controls.

## Product AI boundary

```text
User request
  -> deterministic emergency safety gate
  -> privacy classification
  -> intent routing
  -> approved ZENDOC knowledge with provenance
  -> vendor-neutral local model router
  -> strict structured-output validation
  -> post-generation safety validation
  -> advisory guidance and existing permissioned routes
```

ZENDOC-SLM v1 is the language intelligence component, not the Core Agent. The Core Agent owns orchestration, permissions, registered tools, approvals, and audit events. Model output cannot invoke tools, change roles, dispatch transport, prescribe, or claim that a workflow completed.

## Approved knowledge layer

The repository-owned knowledge layer contains only curated ZENDOC product facts and approved synthetic safety guidance. Each retrieved record carries a knowledge identifier, source provenance, version, and approved-use label. There is no web retrieval, patient-record ingestion, training pipeline, or unnecessary prompt copy created by this layer.

## Evaluation scorecard

M9 extends the synthetic-only evaluation dataset to 20 cases while keeping the default benchmark bounded to 12 cases for laptop-safe execution. Results expose safety, structure, relevance, action validity, hallucination penalty, privacy penalty, and a safety-dominant overall score. Critical safety failures force a zero overall score and disqualify a run; mock and dry runs never become model recommendations.

## Truthful runtime status

The UI distinguishes:

- `ZENDOC Core Agent`: orchestration, tools, permissions, and workflows.
- `ZENDOC-SLM v1`: product language intelligence and structured advisory output.
- `Safety Gate`: deterministic emergency and critical-policy handling.
- `Approved Knowledge Layer`: repository-owned, provenance-bearing product context.

The local model runtime remains `BETA` or `INTEGRATION_REQUIRED` until an operator configures and health-checks an already-installed laptop-safe model. M9 does not download models, fine-tune locally, or claim clinical validation or model perfection.
