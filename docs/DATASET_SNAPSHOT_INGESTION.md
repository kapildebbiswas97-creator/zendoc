# ZENDOC Immutable Dataset Snapshot Ingestion

## Purpose

ZENDOC should not treat a transformed list of rows as the only proof of where production data came from. For official/public datasets, the preferred workflow is:

1. obtain the exact permitted source artifact from the official/public source;
2. retain that artifact outside Git in controlled raw/object storage when the licence/terms permit retention;
3. compute its SHA-256 checksum before transformation;
4. record a dataset snapshot manifest;
5. map/adapt source columns into ZENDOC canonical records;
6. preview the exact snapshot and records;
7. explicitly apply only that same previewed snapshot;
8. keep the ingestion batch, source record IDs, and snapshot provenance available for audit.

This supplements the existing provenance-aware importer and does not replace it.

## Snapshot manifest

The snapshot contract records:

- `source_id`
- public `source_url`
- `retrieved_at` with timezone
- `dataset_version` and/or `published_at`
- `file_name`
- `file_format`
- `file_size_bytes`
- `file_sha256`
- `usage_basis`
- `license_or_terms`
- optional public `license_url`
- optional non-secret `storage_ref`

ZENDOC computes `manifest_sha256` and a stable `snapshot_uid` from the validated manifest.

The manifest is provenance metadata. It does **not** by itself prove that every source row is factually correct or current and it does not convert an external listing into `ZENDOC_VERIFIED` status.

## API workflow

All snapshot-management endpoints are owner-only.

### 1. Validate a manifest

`POST /api/v1/admin/ingestion/snapshots/validate`

The endpoint checks source identity, URL safety, timestamps, checksum shape, file metadata, and usage-basis metadata.

### 2. Adapt/map source rows

Use the existing dataset adapter/connector mapping APIs where needed. Mapping normalizes a source schema; it does not verify the source's truth.

### 3. Preview the snapshot

`POST /api/v1/admin/ingestion/snapshots/preview`

Supply the canonical records and `dataset_snapshot`. ZENDOC binds the record-payload checksum to the snapshot manifest and creates a dry-run batch.

Save the returned `batch_uid`.

### 4. Apply the exact preview

`POST /api/v1/admin/ingestion/snapshots/apply`

Supply:

- the same `source_id`;
- the same `ingestion_type`;
- the same canonical records;
- the same `dataset_snapshot`;
- the previous preview `batch_uid` as `preview_batch_uid`;
- `apply: true`.

If the records or snapshot manifest changed after preview, the apply request is rejected and a new preview is required.

## Healthcare-entity provenance

For imported public healthcare entities, ZENDOC stores source snapshot information inside entity metadata, including:

- snapshot UID;
- manifest SHA-256;
- source-file SHA-256;
- dataset version;
- publication date when supplied;
- retrieval timestamp.

The batch summary also retains the complete validated manifest and links an apply batch to its preview batch.

## Truth and safety rules

- Public/government directory data is not automatically ZENDOC-verified.
- A directory listing does not prove live appointment availability, beds, medicine stock, staffing, certification validity, or booking connectivity.
- Patient medical records and other private health data do not belong in this public-data pipeline.
- Secrets, API keys, signed/private download URLs, passwords, and access tokens must not be persisted in snapshot URLs or storage references.
- Do not bulk-copy Google Places/Maps content into ZENDOC merely because it is visible through an API. Use third-party map/place data only according to the provider's current storage and licence terms.
- Do not commit raw large datasets to Git by default. Git should contain importer code, mappings, manifests without secrets, tests, and documentation; permitted raw artifacts should normally live in controlled object/raw storage.

## Operational recommendation

For the first real pilot, prioritize exact dated snapshots for canonical geography and facility/provider directories in the pilot geography. Import a narrow verified dataset correctly before attempting all-India breadth. Track rejected rows and unresolved geography rather than silently inventing or repairing source facts.
