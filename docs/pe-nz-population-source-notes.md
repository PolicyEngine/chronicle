# NZ population source notes

This records the bounded source-ingestion work for demographic packages 1 and 2
of [issue #176](https://github.com/PolicyEngine/chronicle/issues/176), checked on
30 August 2026 UTC. It does not mark the demographic target surface complete.

## Pinned publisher evidence

| Artifact | Publisher reference | SHA-256 | Bytes |
|---|---|---|---:|
| Subnational population workbook | At 30 June 2025, published 29 October 2025 | `001e8a896cfb50f5ed17836dc815b235e3bcca55ee91c9869a2afaeb054b50a6` | 97,990 |
| Regional council code/name attributes | Boundaries at 1 January 2025 | `e5d53fa6abf742121d123bff970c77658a16e8c9b405b83d1a978cc22920d660` | 3,381 |
| National population release landing page only | At 30 June 2025, published 19 August 2025 | `b2d2751800857895b1498d87df6f03ac3511ec8c7a9b17cc3150c8ab56533053` | 61,286 |

All artifacts came directly from Stats NZ's website or Stats NZ's official
geographic service. Their manifests record exact publisher URLs, hashes,
retrieval timestamps, sizes, and immutable country-scoped R2 keys:

- [Subnational workbook manifest](../db/data/stats_nz/subnational_population_estimates_2025/manifest.yaml).
- [REGC 2025 classification manifest](../db/data/stats_nz/regional_council_2025_codes/manifest.yaml).
- [National landing-page evidence manifest](../db/data/stats_nz/national_population_estimates_2025/manifest.yaml).

The objects use
`r2://ledger-raw/raw/nz/stats_nz/<package>/2025/<sha256>/<filename>`.
After upload, all three remote objects were downloaded through the authorized
Chronicle/Wrangler path and their byte counts and SHA-256 hashes matched the
local publisher artifacts.
The two population references share a 30 June 2025 reference date, not a
publication date. The national landing page is evidence of the missing download
surface, **not** a single-year-age data artifact or a national source package.
The classification is geography evidence only and emits no population facts.

## S7: partial workbook package

The [source package](../packages/stats_nz/subnational_population_estimates_2025/README.md)
admits 85 cells from Tables 1 and 3: 17 geographic rows × all ages/four broad
age bands. Its precise scope, semantics, and guards are documented there.

The workbook does not contain the requested five-year-age × sex × region cut.
Stats NZ's public metadata catalog lists `POPES_SUB_004`:

> Subnational population estimates (RC, SA2), by age and sex, at 30 June 1996-2025 (2025 boundaries)

This identifies the needed population/age/sex/boundary family, not a claim that
the query's original publication vintage has been verified. The documented API
request for its structure returned **HTTP 401** without a subscription:

```text
https://api.data.stats.govt.nz/rest/dataflow/STATSNZ/POPES_SUB_004/1.0?references=all&detail=referencepartial
```

The [official API guide](https://www.stats.govt.nz/tools/aotearoa-data-explorer/ade-api-user-guide/)
describes API subscription access. No existing subscription was available to
this ingestion run. No account was created and no authentication bypass was
attempted. An authorized export still needs verification of the exact five-year
age categories, sex categories, 2025 REGC boundaries, reference date, and source
revision vintage before it can extend this package. In particular,
`POPES_SUB_003` advertises **2026 boundaries** and is not a substitute.

The regional five-year-age × sex table is a **follow-up**, not part of this
package. This package lands only the 85 partial counts above. The follow-up
extends it once an authorized export passes those checks; until then the
package emits no five-year-age or sex-specific fact.

## S8: national single-year ages remain missing

The pinned [19 August 2025 national release](https://www.stats.govt.nz/information-releases/national-population-estimates-at-30-june-2025/)
contains headline counts and directs users to Infoshare's Population / Population
Estimates – DPE tables for annual and quarterly single-year-age data. Its page
payload contains no downloadable XLSX/CSV document block. This corrects the
inventory's assumption that the release itself provided a single-year-age XLSX.

No reproducible publisher single-year-age artifact for this original reference
date/publication vintage was acquired. The public ADE catalog query did not
identify a corresponding national 2025 age table. The missing artifact remains
an access/discovery gap, not a zero population count. A subscribed API request
may assist discovery, but access alone does not establish that the required
original-vintage table is available.

The release explicitly says that Stats NZ revises the preceding six quarters.
A current 2025 observation may therefore differ from the 19 August 2025
publication. An eventual publisher export must carry its actual revision
vintage; it must not be relabeled as the original release. No latest-2026
population, projection, mirrored third-party bytes, or inferred age allocation
has been substituted. No national single-year-age source-package alias is
registered, and the national facts count added by S8 is **zero**.

## Validation and boundary

The partial S7 package passes source-package validation, exact source-cell
comparisons, geography mapping checks, source-semantic drift tests, consumer
contract validation, and an explicit one-package build. The bounded source
build records 85/85 lineaged facts and 2,265 parsed cells.

The source build warns that Axiom CLI canonical-concept validation did not run.
All mappings are source-label relations; this work claims neither Axiom
canonical certification nor calibration quality.

Microcosm retains responsibility for choosing constraints, reconciling source
universes, aging, imputing, constructing solver targets, and activating a
population. The 85 counts are available source facts, not proof that these
downstream steps have run. Independent source-fidelity and boundary review is
still required before landing.
