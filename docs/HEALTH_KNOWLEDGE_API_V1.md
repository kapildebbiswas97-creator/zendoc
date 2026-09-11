# Health Knowledge Evidence API v1

Endpoint: `GET /api/v1/health-knowledge/evidence?q=...`

This authenticated endpoint exposes governed retrieval evidence without pretending that an LLM generated a safe medical answer.

## Response contract

The endpoint returns:

- `EVIDENCE_FOUND` or `NO_APPROVED_EVIDENCE`;
- `answer: null`;
- `answer_status: EVIDENCE_ONLY`;
- `medical_advice: false`;
- the actual retrieval mode (`LEXICAL_ONLY` or later `HYBRID`);
- pgvector capability status;
- bounded evidence excerpts;
- document/source/version/hash provenance for every evidence item.

If no approved indexed source matches the query, the endpoint explicitly refuses to represent model memory as retrieved medical knowledge.

## Security and truthfulness

- API authentication is required.
- Only chunks whose parent document is currently APPROVED are eligible.
- Superseded evidence disappears from retrieval without destroying audit history.
- Query length and result count are bounded.
- Excerpts are bounded to avoid returning an entire source document.

## Next layer

A later Knowledge Agent may consume this API/service and synthesize a user-facing explanation only after separate model-output safety, citation grounding and evaluation gates are implemented.
