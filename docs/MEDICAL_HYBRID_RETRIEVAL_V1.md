# Medical Hybrid Retrieval v1

This stage adds evidence-first lexical retrieval and a truthful pgvector capability boundary.

## Retrieval eligibility

Only chunks whose parent medical-knowledge document is currently `APPROVED` are searchable. `PENDING`, `REJECTED`, `SUPERSEDED` and unknown document versions are excluded.

Every returned result carries evidence metadata including:

- source family;
- document UID/title/URL;
- publication date and version;
- immutable document SHA-256;
- chunk SHA-256;
- parser/chunk provenance metadata.

## Lexical baseline

A deterministic lexical scorer provides a safe baseline on SQLite and PostgreSQL. It ranks approved chunks by query-term coverage and bounded term density.

This is a retrieval baseline, not a claim of clinical relevance or diagnostic correctness.

## pgvector boundary

ZENDOC reports pgvector as `WORKING` only when:

1. PostgreSQL is the configured database; and
2. the PostgreSQL `vector` extension is actually installed.

Otherwise the capability is `INTEGRATION_REQUIRED` and vector storage/search fails closed. Standard PostgreSQL without pgvector is never mislabeled as vector-enabled.

When pgvector is available, vector results may be combined with lexical scores. When it is not available or no query embedding is supplied, the response mode is explicitly `LEXICAL_ONLY`.

## Still not implemented here

- embedding generation/provider calls;
- vector extension installation/operations provisioning;
- ANN index tuning;
- medical answer generation;
- evidence synthesis;
- clinical decision making.
