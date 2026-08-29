# ZENDOC-SLM Roadmap

## Product Direction

The long-term system is not an Ollama wrapper. It combines the ZENDOC agentic control plane, a future ZENDOC-adapted language model where justified, specialized agents, permissioned healthcare tools, explicit human/doctor approvals, and privacy/safety/audit controls.

```text
Open-weight base model
  -> reproducible synthetic and governed evaluation
  -> human-reviewed foundation selection
  -> future licensed dataset pipeline
  -> future adaptation/fine-tuning experiment
  -> ZENDOC-SLM v0.x candidate
  -> independent safety, privacy, quality, and resource evaluation
  -> controlled pilot and governance decision
  -> possible future production model
```

An upstream base model remains subject to its own license and provenance. Evaluation does not make it proprietary. A future adapted checkpoint, dataset, configuration, and evaluation record would each need separate legal and technical ownership analysis.

## Current Foundation: M8.2

M8.2 provides:

- a fixed, claim-conscious candidate registry;
- a versioned, synthetic-only evaluation dataset and governance metadata;
- provider-neutral dry, mock, and guarded real-local runner modes;
- deterministic structured-output and safety scoring;
- safety-first comparison and readiness labels;
- owner-only controls and metadata-only persistence;
- conservative laptop safeguards.

It does not provide real candidate results, model downloads, data ingestion, training, fine-tuning, a proprietary checkpoint, clinical validation, or production approval.

## Future Dataset Pipeline

Any future training/adaptation dataset requires, before ingestion:

1. named ownership and accountable reviewers;
2. source category and record-level provenance;
3. license and allowed-use verification;
4. PHI/PII classification and documented exclusion/de-identification controls;
5. deduplication, contamination, and quality checks;
6. healthcare-safety taxonomy and expert review;
7. train/validation/test separation with protected evaluation sets;
8. versioned manifests, hashes, change control, and retention policy;
9. legal/privacy/clinical approval appropriate to intended use.

Patient records must not be repurposed for training merely because ZENDOC stores them. Consent for care is not consent for model training. M8.2 ingests no healthcare dataset.

## Future Adaptation Stages

### Stage 1: Candidate Evidence

Run bounded, reproducible evaluations on already-installed candidates. Safety disqualifications override capability averages. Compare multiple runs and perform human multilingual/domain review. No candidate becomes the winner automatically.

### Stage 2: Experiment Design

Define narrow, non-clinical target behaviors; document baselines, acceptance criteria, compute budget, rollback, licenses, and threat model. Decide whether prompting/retrieval/deterministic logic solves the need without adaptation.

### Stage 3: Governed Adaptation

On suitable infrastructure—not the owner's primary laptop—run explicitly approved training or parameter-efficient adaptation. Isolate environments and datasets, record seeds/configuration/artifacts, and prevent evaluation-set leakage. This stage is FUTURE.

### Stage 4: Independent Evaluation

Re-run protected safety, privacy, injection, hallucination, multilingual, structured-output, latency, and resource tests. Add red-team and qualified healthcare review. Compare against the unadapted base and deterministic fallback.

### Stage 5: Controlled Integration

If approved, expose the model only through the M8.1 provider boundary and Model Router. The model still receives no permission to execute tools. Deterministic emergency handling, authorization, consent, approvals, fallback, and audit remain authoritative.

### Stage 6: Production Governance

Before any healthcare production claim: complete legal/privacy/security review, clinical validation appropriate to intended use, monitoring and incident response, rollback and version retirement, model/data documentation, and regional regulatory analysis.

## Non-Negotiable Safety Boundaries

- No autonomous diagnosis or prescribing.
- No emergency workflow bypass.
- No model-granted Admin or tool authority.
- No secret or credential exposure.
- No external routing of protected data outside policy.
- No hidden chain-of-thought collection requirement.
- No claim of clinical capability based only on benchmark averages.
- No heavy training or stress workloads on the owner's development laptop.

## Decision Record for a Future Base Model

A human selection record should identify the exact model tag/hash, license verification, runtime and quantization, dataset version/hash, run IDs, safety status and critical failures, component scores, human reviews, resource conditions, known limitations, and approval/rejection rationale. “Highest score” alone is insufficient.

