# West Bengal + India Public Data Acquisition v1

## Scope correction

ZENDOC's first geography acquisition target is **the whole State of West Bengal**.

Nadia is retained only as a regression/quality-validation district because earlier ingestion tests were built there. Nadia is **not** a coverage boundary and must never be presented as the statewide acquisition scope.

In parallel, ZENDOC maintains an **all-India official/public source catalog** so national geography and healthcare directories can be acquired once and filtered/normalized for every State/UT.

## Data workspace on the founder PC

Keep raw changing datasets outside normal Git history. Pick any drive with sufficient space.

Windows example:

```powershell
python scripts/bootstrap_public_data_workspace.py --storage-root D:\ZENDOC_DATA
```

Linux/macOS example:

```bash
python scripts/bootstrap_public_data_workspace.py --storage-root ~/ZENDOC_DATA
```

The command creates:

```text
ZENDOC_DATA/
  incoming/     exact newly downloaded/exported files
  raw/          immutable source/sha256/file snapshots
  manifests/    source and snapshot provenance
  curated/      accepted normalized outputs
  samples/      small non-sensitive development samples
  rejected/     artifacts rejected by source/schema/quality gates
  logs/         bounded acquisition/import summaries
  README.md
```

`raw/` is content-addressed. Re-downloading the same artifact does not silently overwrite another version.

## What belongs in Git

Commit:

- acquisition/download scripts;
- official source registry metadata;
- source bundle definitions;
- schemas and mapping rules;
- snapshot manifests/checksums without secrets;
- small, legally reusable, non-sensitive samples;
- tests and documentation.

Do **not** normally commit:

- large monthly raw government exports;
- patient records, prescriptions, claims or private conversations;
- pharmacy live stock/actual selling price feeds;
- private provider operational data;
- API keys/tokens/cookies;
- authorized ABDM exports unless the governing agreement explicitly allows repository storage.

The repository ignores `data_workspace/` and `ZENDOC_DATA/` to reduce accidental raw-data commits.

## West Bengal statewide source stack

`zendoc.public_data_bundle.west_bengal_bundle()` is the machine-readable source plan.

Priority source families:

1. **LGD** — State/district/sub-district/local-body/village government geography.
2. **OGD National Hospital Directory** — public hospital/facility directory with geocodes where supplied.
3. **National Register of Clinical Establishments** — only where the applicable jurisdiction/register publishes records.
4. **West Bengal Health Scheme empanelled HCO directory** — scheme-provider snapshot.
5. **Swasthya Sathi active hospital directory** — scheme-provider snapshot.
6. **NABL laboratory directory** — accreditation evidence, not live slots/prices.
7. **NABH healthcare organisation directory** — accreditation evidence, not live capacity.
8. **Jan Aushadhi Kendra directory** — public pharmacy locations, not live medicine stock.
9. **OGD Blood Bank Directory** and **e-RaktKosh** — directory/freshness-aware blood-centre discovery; static data is not live blood availability.
10. **CGHS / PM-JAY provider directories** — scheme-provider discovery only.
11. **CDSCO / State Drug Controller gateway** — regulatory/licence reference where public state outputs are available.

All district coverage is resolved from the current official LGD snapshot rather than a manually frozen list of district codes.

## India-wide public source layer

The India bundle additionally catalogs public official sources for:

- all-State/UT LGD geography;
- hospitals and clinical establishments;
- NABH/NABL accreditation;
- Jan Aushadhi locations/products;
- blood centres;
- PM-JAY and CGHS provider discovery;
- NMC medical registration/college references;
- nursing/pharmacy education directories;
- HMIS aggregate indicators;
- NPPA price references;
- CDSCO approved-drug/NLEM/regulatory references;
- myScheme discovery.

ABDM HFR/HPR are catalogued as **AUTHORIZED_ONLY** for systematic access. The public downloader refuses to fetch them until a legitimate authorized access path exists.

## Current official OGD anchors

At implementation time (11 September 2026):

- the OGD Local Government Directory catalog publishes monthly resources for States, Districts, Sub-Districts, Villages and Local Bodies and exposes catalog ZIP/download facilities;
- the National Hospital Directory is published as a monthly geocoded resource;
- OGD-published resources are governed by the Government Open Data License - India / NDSAP terms shown by the platform.

Freshness must be recorded in each acquired manifest; these dates are not hard-coded as permanent truth.

## Controlled direct download

For an exact public artifact URL on a registered official host:

```powershell
python scripts/download_public_artifact.py `
  --source-id data_gov_hospitals `
  --artifact-url "<EXACT_OFFICIAL_CSV_OR_ZIP_URL>" `
  --storage-root D:\ZENDOC_DATA `
  --license-or-terms "Government Open Data License - India" `
  --dataset-version "2026-08" `
  --file-name national_hospital_directory_2026-08.csv
```

The downloader:

- requires a registered ZENDOC source ID;
- accepts HTTPS public artifacts only through the existing URL validator;
- blocks credential/token-like query keys;
- verifies official host/redirect boundaries;
- caps downloads at 50 MiB per artifact;
- computes SHA-256;
- creates an immutable raw path and normalized snapshot manifest.

For sources without a verified stable bulk URL, download/export the dated public artifact manually into `incoming/`, then use the existing command:

```powershell
python scripts/acquire_dataset.py `
  --source-id wbhs_empanelled_hco `
  --source-url "https://healthscheme.wb.gov.in/Home/wbhs_empanelled_hco.aspx" `
  --input D:\ZENDOC_DATA\incoming\<downloaded-file> `
  --storage-root D:\ZENDOC_DATA `
  --usage-basis official_public_download `
  --license-or-terms "<terms shown by source>" `
  --dataset-version "<published/version date>" `
  --inspect
```

Interactive lookup pages are not silently scraped merely to increase row count.

## Acquisition order

### Wave WB-0 — statewide geography

Acquire current LGD States, Districts, Sub-Districts, Local Bodies and Villages. Import **all West Bengal rows** through the existing LGD/state geography pipeline. Nadia is one regression check among the statewide data.

### Wave WB-1 — statewide healthcare directories

Acquire National Hospital Directory and West Bengal scheme/public facility directories. Normalize into public healthcare entities with source/trust/freshness state retained.

### Wave WB-2 — accreditation and specialized directories

Link NABH/NABL, blood-centre, Jan Aushadhi and regulatory references to geography/entities where identifiers/evidence support the link. Never merge entities solely because names look similar.

### Wave INDIA-0 — national baseline

Retain the full national versions of LGD and national healthcare directories once, then derive State/UT filtered curated views from those exact snapshots. Do not download the same national file separately for every state.

### Wave INDIA-1 — state-specific enrichments

Use `state_source_priorities.py` to add verified state sources. Each State/UT can be enriched without changing the national baseline architecture.

## Data that cannot be truthfully collected from static Internet directories

The following require providers, partners, field verification or authoritative real-time feeds:

- doctor live appointment slots;
- pharmacy live stock and actual selling price;
- lab live slots/actual current prices;
- live hospital/ICU bed vacancy;
- ambulance dispatch/ETA;
- personal scheme eligibility/approval/payment;
- insurance claim state;
- patient Health Memory without patient authorization.

These remain explicit data gaps. ZENDOC must not infer them from directory presence.

## Quality gate before production use

Every artifact/district/source must pass:

1. source validity and usage basis;
2. immutable snapshot provenance and SHA-256;
3. schema mapping;
4. official geography resolution;
5. duplicate/entity-link review;
6. conflict handling;
7. rejected-row accounting;
8. freshness state;
9. SQLite regression tests where supported;
10. PostgreSQL production-path tests;
11. Finder/query verification without fake live availability.

Only after those checks should a curated dataset be considered usable by Finder or other patient-facing discovery workflows.
