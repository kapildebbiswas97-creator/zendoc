# Nadia pilot source plan

The first controlled ZENDOC data slice is **India → West Bengal → Nadia**. This
plan is a collection decision record; it does not claim that any source has
been downloaded, that a facility is current, or that a provider is ZENDOC
verified.

## Source classification

| Source | Classification | Intended Nadia use | Current state |
| --- | --- | --- | --- |
| Local Government Directory (`lgd`) | `DOWNLOADABLE_SNAPSHOT` | Stable country/state/district/subdivision/block/local-body/village identifiers | Not acquired |
| data.gov.in hospital directory (`data_gov_hospitals`) | `MANUAL_VERIFICATION_REQUIRED` | Public hospitals and health facilities filtered to Nadia | Exact artifact not established; current resource view marked sandbox |
| West Bengal Health Scheme HCO (`wbhs_empanelled_hco`) | `MANUAL_VERIFICATION_REQUIRED` | Scheme-empanelled facilities where a permitted dated export exists | Not acquired |
| Swasthya Sathi hospital search (`swasthya_sathi_hospitals`) | `PUBLIC_LOOKUP_ONLY` | Runtime discovery only | Lookup only |
| PMBJP Kendra locator (`pmbjp_kendras`) | `PUBLIC_LOOKUP_ONLY` | Pharmacy-location discovery only | Lookup only |
| NABL laboratory directory (`nabl_labs`) | `PUBLIC_LOOKUP_ONLY` | Accreditation lookup evidence | Lookup only |
| data.gov.in blood-bank directory (`data_gov_blood_banks`) | `DOWNLOADABLE_SNAPSHOT` | Dated blood-centre directory metadata | Not acquired |
| State Drugs Control gateway (`cdsco_state_drug_control`) | `PUBLIC_LOOKUP_ONLY` | Pharmacy-licence lookup where permitted | Lookup only |
| National Medical Register (`nmc_imr`) | `PUBLIC_LOOKUP_ONLY` | Individual professional evidence checks | Lookup only |

The registry's `official_url`, trust level, and live-fetch status remain the
source metadata. A lookup page is not treated as a bulk API. If a permitted
download or authorised API cannot be confirmed, the source stays in a gap
state and is not scraped.

See [dated source evidence](NADIA_SOURCE_EVIDENCE.md) for inspected acquisition
paths and unresolved access/permission gaps. A classification is not proof that
a current, complete Nadia export exists.

## Controlled acquisition

The acquisition service reads an exact operator-selected local artifact. It
does not fetch arbitrary web pages. Example:

```text
python scripts/acquire_dataset.py \
  --source-id data_gov_hospitals \
  --source-url https://www.data.gov.in/resource/<dated-resource> \
  --input C:\\controlled-downloads\\nadia-hospitals.csv \
  --storage-root C:\\controlled-raw \
  --dataset-version 2026-09-11 \
  --usage-basis official_public_download \
  --license-or-terms "Use under the published data.gov.in terms."
```

The command writes a content-addressed raw copy below the supplied storage
root and prints a manifest without row values. The resulting `dataset_snapshot`
object is passed to the existing owner-only snapshot preview endpoint:

`POST /api/v1/admin/ingestion/snapshots/preview`

Only the exact same snapshot, canonical records, and returned preview batch may
be applied. Raw artifacts are deliberately excluded from Git.

Supported acquisition formats are CSV, JSON, XLSX, and ZIP. XLS is retained as
an exact artifact but requires an approved parser for schema inspection. ZIP
inspection rejects traversal and encrypted members and lists supported inner
datasets without extracting untrusted paths.

## Nadia data-quality gate

Before any Nadia snapshot is treated as a pilot dataset, the report must pass
source validation, hashing, licence/usage recording, schema mapping, dry run,
geography validation, duplicate review, provenance persistence, security tests,
and PostgreSQL tests. Public records remain `not_verified` and
`not_connected`; no live slots, beds, stock, certification, or booking path is
inferred from a directory listing.

No Nadia artifact or provider count is claimed by this plan. Counts belong in
the machine-readable acquisition/ingestion report after a permitted snapshot
has actually been prepared and reviewed.


