# Nadia source evidence — 2026-09-11

This is a source-access record, not a dataset import. No real raw artifact has
been acquired in this stage. Snapshot SHA-256, provider counts, accepted rows,
rejected rows and conflicts are therefore **not available**, rather than zero
measured coverage. Automated fixtures are synthetic and run in disposable tests.

| Source | Evidence inspected | Acquisition decision |
| --- | --- | --- |
| LGD | [Download Directory](https://lgdirectory.gov.in/downloadDirectory.do) offers state/district selection, administrative entities and XLS reports behind a CAPTCHA | `DOWNLOADABLE_SNAPSHOT` through a human-completed export; exact Nadia artifact still needed |
| data.gov.in hospital directory | [Resource page](https://www.data.gov.in/resource/national-hospital-directory-geo-code-and-additional-parameters-updated-till-last-month) returned an empty resource view with a sandbox/incomplete-data notice; catalogue search metadata advertises CSV | `MANUAL_VERIFICATION_REQUIRED` until the actual artifact, current source and terms are established; catalogue metadata is not an acquired dataset |
| Nadia District hospitals | [Public directory](https://nadia.gov.in/public-utility-category/hospitals/) contains a mixture of staff and facilities. [Website policy](https://nadia.gov.in/website-policies/) requires permission for reproduction | `MANUAL_VERIFICATION_REQUIRED`; no bulk scrape or staff contact publication |

The other candidate registries remain at the classifications in
[NADIA_PILOT_SOURCE_PLAN.md](NADIA_PILOT_SOURCE_PLAN.md); their bulk acquisition
has not been established by this evidence record. PMBJP, NABL, Swasthya Sathi,
NMC and regulator lookup pages must not be represented as working bulk APIs.

For the first real import, retain the exact permitted export and its source
terms, acquire/hash it outside Git, inspect and map the real column names, and
review stable source identifiers plus canonical Nadia parent references. Missing
geography, licensing evidence or conflicting identity remains a data gap. Public
directory presence provides no stock, beds, appointment slots, professional
certification, ZENDOC verification or booking connection.

## Acquisition integrity correction

Acquisition now uses the same canonical manifest as snapshot preview/apply, so
the snapshot UID remains identical from local acquisition through persisted
source metadata. The prior acquisition digest included MIME metadata while
ingestion used the registry source name, creating different identities for the
same handoff. MIME information remains available outside the canonical digest.

The PostgreSQL CI smoke includes a synthetic acquired CSV → preview → apply →
replay path on its disposable database. This tests actual insert IDs and
provenance; the prior PostgreSQL smoke tested schema/readiness only. Production
source ingestion and live deployment still require their separate evidence.

