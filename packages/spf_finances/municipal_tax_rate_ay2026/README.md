# SPF Finances municipal PIT surcharge rates: income year 2025 (assessment year 2026)

This package preserves all **565 published commune rate cells**, one fact per
cell, from FPS Finance / SPF Finances / FOD Financiën's five-page PDF headed
“Municipal tax rates (%)” and “for tax assessment year 2026”. No commune is
absent or duplicated relative to Statbel's NIS 2025 catalogue.

## Source capture

The file was downloaded on **2026-10-23** by an HTTP GET of
<https://fin.belgium.be/sites/default/files/media/documents/municipal-tax-rate-2026.pdf>.
The manifest also records the same path on `finances.belgium.be`, which
was not fetched. Its metadata title is “Municipal tax rate | FPS Finance” and
its creation date is 2026-03-17. The unrelated metadata `/Year` value `2022.00` is not used as
the reference period: the visible heading explicitly states 2026.

The exact **182,097-byte** PDF is captured at
[`db/data/spf_finances/municipal_tax_rate_ay2026/municipal-tax-rate-2026.pdf`](../../../db/data/spf_finances/municipal_tax_rate_ay2026/municipal-tax-rate-2026.pdf)
relative to the repository root, with SHA-256
`051211d85f05367002c31ad1879b294af50b8c14119d2127451bc976bd5e1606`.
The harness's `fetch-artifact` command registered these already-downloaded bytes
locally before selectors were generated. The deterministic manifest pins
both the PDF and its representation-only CSV. Both are stored under their
manifest keys in the `ledger-raw` R2 bucket and were verified by SHA-256
readback on 2026-10-24.

## Period semantics

The PDF publishes rates **for tax assessment year 2026** (aanslagjaar /
exercice d'imposition 2026). Those rates tax income of **2025**.

The facts follow the convention of the other Belgian tax packages:
- the `tax_year` period is the income year, here **`tax_year: 2025`**;
- the publisher's assessment year is kept as a constraint.

The precedents:
- [`statbel/fiscal_income_distribution_2023`](../../statbel/fiscal_income_distribution_2023/source_package.yaml)
  keys income-year 2023 tables as `tax_year: 2023`. It carries the
  `income_year == 2023` ("Publisher income year") and `assessment_year == 2024`
  ("Publisher assessment year") constraints, and the legal vintage
  `income_year_2023_assessment_year_2024`.
- [`spf_finances/pit_2023`](../pit_2023/source_package.yaml) and
  [`statbel/fiscal_income_2023_nis_2025`](../../statbel/fiscal_income_2023_nis_2025/source_package.yaml)
  also key the income year as `tax_year: 2023`.

This package therefore declares:
- `period: 2025`;
- the shared constraints `income_year == 2025` and `assessment_year == 2026`, with the same labels;
- the legal vintage `income_year_2025_assessment_year_2026`.

The publisher's year is not re-labelled. `source_period_label` keeps the
verbatim line `for tax assessment year 2026`, with `basis: tax`, and the source
table name keeps it too. No coverage dates are invented.

Income of policy year 2026 would need assessment-year 2027 rates, which this
file does not contain. Chronicle does not extrapolate these rates to 2026
income. A consumer that applies them to 2026 income must declare that it is
carrying them forward.

## Values and geography

`unit: percent` and `aggregation: rate` use Chronicle's existing vocabulary for
a publisher's rate. Decimal commas become decimal points (`7,5` → `7.5`),
without dividing by 100, rounding, averaging or constructing a regional rate.
Zero is retained, including Knokke-Heist's printed `0,0`. `entity: government`
identifies the municipal authority whose administrative rate is published;
these are neither taxpayer counts nor measured effective household tax rates.
Every record set explicitly declares `provenance_class: administrative`.

Geography IDs, names and vintage come directly from the committed
[`statbel_population_structure_commune_2025.csv`](../../../db/data/statbel/population_structure_commune_2025/statbel_population_structure_commune_2025.csv),
using its 565 `nis_<code>_total` rows. Names equal that package's `geography_name`
literally: for example, PDF **Bruxelles** maps through the French alias to
NIS **21004**, whose canonical geography name is **Brussels**. No merger sums,
boundary translation or value reconciliation occur.

The publisher's municipality label is preserved as the `publisher_commune`
dimension and an equality constraint, separately from the canonical name.
Matching proceeds in two tiers:

1. Exact equality with Statbel's `source_municipality_nl` or
   `source_municipality_fr`: **558** rows.
2. Case folding, Unicode NFKD diacritic removal, and removal of apostrophes,
   hyphens and spaces: **7** rows. Hyphenated PDF line wraps are joined before
   either tier. Normalization changes names only, never rates.

The seven second-tier labels are `Blégny`, `Braine-l'Alleud`,
`Fontaine-l'Evêque`, `Les-Bons-Villers`, `Mont-de-l'Enclus`,
`Ottignies-Louvain-La-Neuve` and `Villers-le-Bouillet`. Their paired Statbel
spellings and every exact match are in
[`commune_mapping_audit.csv`](commune_mapping_audit.csv). No exception aliases
or residual declarations are needed. Unresolved labels, ambiguity at either
tier, duplicate labels/codes, or an incomplete catalogue match are fatal.

For the nine German-language communes, the catalogue's nominal Dutch column
already contains German spellings, including `Amel`, `Büllingen`,
`Bütgenbach`, `Kelmis` and `Sankt Vith`. Its French column supplies `Amblève`,
`Bullange`, `Butgenbach`, `La Calamine` and `Saint-Vith`. All nine PDF names
match exactly. Post-2025 merged names, including
`Beveren-Kruibeke-Zwijndrecht`, `Bilzen-Hoeselt` and `Tongeren-Borgloon`, map
directly to the existing NIS 2025 catalogue.

## Locators, reproduction and limits

The CSV and audit retain the PDF SHA-256, URL, **1-based page**, **column
block 1–3 from left to right**, and **1-based start/end/rate lines** in
`pypdf.PdfReader(...).pages[page-1].extract_text().splitlines()`, counting blank
lines. These are text-extraction lines, not inferred visual table rows. The
raw printed rate token is retained. A wrapped example is
`Berchem-Sainte-Agathe`: page 1, block 2, name at lines 56–57 and rate at
line 58. CSV guards bind each selector to its NIS code, publisher label and
exact PDF locator. Chronicle's source-cell lineage points to the checksum-pinned
CSV; its locator fields and the captured PDF provide the publisher-cell trail.

From the repository root, with the project dependencies installed:

```sh
python packages/spf_finances/municipal_tax_rate_ay2026/build_package.py
chronicle validate-package spf-finances-municipal-tax-rate-ay2026 --year 2025
chronicle build-suite spf-finances-municipal-tax-rate-ay2026 --year 2025 \
  --out .hub-scratch/municipal-tax-rate-suite --replace
```

The focused test file is
`tests/test_chronicle_spf_finances_municipal_tax_rate.py`. It independently
re-parses every rate using PDF layout extraction, verifies the sequential text
locators, checks mapping against both Statbel name columns, and checks
deterministic generated bytes, lineage and rate/period semantics.

Coverage is confined to this release: income year 2025, assessment year 2026.
The package contains no regional averages, national rate, rates for other
years, consumer selection contract or model target.
