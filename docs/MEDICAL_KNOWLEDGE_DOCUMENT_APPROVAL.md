# Medical Knowledge Document Approval v1

This stage converts a reviewed source-family candidate into a durable, immutable document record before any RAG indexing exists.

## State machine

`PENDING -> APPROVED`

or

`PENDING -> REJECTED`

An approved older artifact may later become `SUPERSEDED` only when a newer artifact from the same source family is explicitly approved as its replacement.

Reviewed decisions are immutable. If metadata, content, terms or the artifact changes, register a new document/version instead of editing history.

## Durable identity

Each document is bound to:

- source family;
- HTTPS document URL;
- publication date;
- retrieval timestamp;
- exact SHA-256 content digest;
- usage basis;
- version;
- registering owner;
- review status;
- reviewer and review timestamp;
- optional superseded document UID.

The deterministic `document_uid` is derived from immutable provenance fields. Registering the same artifact again is idempotent.

## Security boundary

Only the configured ZENDOC owner may register or review a medical-knowledge artifact. A later parser/indexer must call `get_approved_medical_knowledge_document()` and must fail closed for `PENDING`, `REJECTED`, `SUPERSEDED` or unknown artifacts.

This stage still does not parse, chunk, embed, retrieve or answer from medical content.
