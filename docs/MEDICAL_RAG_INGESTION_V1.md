# Medical RAG Ingestion Foundation v1

This stage begins the deterministic ingestion pipeline after source-family governance and document-level approval.

## Required order

`APPROVED source family`
→ `registered immutable document`
→ `explicit APPROVED review`
→ `bounded parser output`
→ `normalized extracted text`
→ `deterministic overlapping chunks`
→ `provenance-bound storage`

No later retrieval or embedding component should accept raw text or an arbitrary URL directly.

## Stored ingestion provenance

Each ingestion records:

- approved `document_uid`;
- parser name and version;
- SHA-256 of normalized extracted text;
- chunking strategy and parameters;
- chunk count;
- owner identity;
- creation timestamp.

Each chunk records:

- deterministic chunk UID;
- ingestion UID;
- document UID;
- ordinal;
- chunk text and SHA-256;
- word count;
- source/document/version/parser provenance metadata.

## Safety behavior

- PENDING, REJECTED, SUPERSEDED and unknown documents fail closed.
- Repeating the same exact extraction/parser/chunking configuration is idempotent.
- Superseded document chunks may remain in the audit database, but retrieval-facing access fails because the source document is no longer APPROVED.
- Ingestion is owner-only.
- Input size and chunk-size parameters are bounded.

## Deliberately not included yet

This stage does not add:

- embeddings;
- pgvector;
- semantic retrieval;
- evidence ranking;
- model answering;
- clinical diagnosis;
- automatic web fetching.

Those remain separate reviewed PRs.
