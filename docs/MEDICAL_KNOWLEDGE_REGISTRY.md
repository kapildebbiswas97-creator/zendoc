# ZENDOC Medical Knowledge Source Registry v1

## Purpose

This is the governance boundary before healthcare RAG ingestion.

A source family can be **approved for discovery/review** without any claim that:

- its full website may be bulk copied;
- every document is current;
- every document is clinically applicable to a user;
- ZENDOC has already downloaded or indexed it;
- ZENDOC has an official integration with the publisher;
- a model may answer from it without evidence retrieval.

The registry is implemented in `zendoc/medical_knowledge_registry.py` and is visible to the configured owner through `/owner/medical-knowledge-sources` and `/owner/intelligence-manifest`.

## Initial primary-authority source families

The initial discovery-approved families are:

1. World Health Organization guideline publications — `https://www.who.int/publications/who-guidelines`
2. Ministry of Health and Family Welfare, Government of India — `https://www.mohfw.gov.in/`
3. Indian Council of Medical Research guidelines — `https://www.icmr.gov.in/guidelines`
4. National Centre for Disease Control technical guidelines — `https://ncdc.mohfw.gov.in/includes/Resource_Library/index.php?tab=Technical+Guidelines`
5. National Health Authority / Ayushman Bharat Digital Mission policy and interoperability material — `https://abdm.gov.in/`

These are publisher/source-family entries, not ingested corpora.

## Required document handoff metadata

Before a later ingestion service may even review a concrete document, the handoff must include:

- `source_id`
- `document_title`
- HTTPS `document_url`
- `publication_date`
- `retrieved_at`
- SHA-256 `content_sha256`
- `usage_basis`
- `version`

The validator returns `REVIEWABLE`, **not** `INGESTION_ALLOWED`.

## Next gate

A separate PR must implement document-level acquisition and approval. That gate must record at least:

- exact artifact/snapshot;
- publisher/source family;
- licence, terms or other legitimate usage basis;
- retrieval timestamp;
- publication/version date;
- cryptographic digest;
- content type and parser;
- clinical/public-health applicability metadata;
- supersession/freshness policy;
- human review outcome.

Only an approved concrete artifact may move to parsing/chunking/embedding.

## Required RAG safety sequence

The intended later sequence is:

`APPROVED SOURCE FAMILY`
→ `DOCUMENT ACQUISITION`
→ `USAGE + PROVENANCE REVIEW`
→ `VERSIONED SNAPSHOT`
→ `PARSING`
→ `CHUNKING`
→ `INDEXING`
→ `HYBRID RETRIEVAL`
→ `EVIDENCE RANKING`
→ `GROUNDED ANSWER`

If retrieval fails, ZENDOC must not represent a medical-knowledge answer as grounded.

## What v1 deliberately does not do

This registry does **not**:

- download medical guidance;
- scrape websites;
- create embeddings;
- enable pgvector;
- answer medical questions;
- diagnose;
- give a model autonomous healthcare actions;
- claim government or WHO integration.

Those are separate, testable milestones.
