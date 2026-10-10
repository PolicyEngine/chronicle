# PolicyEngine New Zealand source checklist

This checklist records Chronicle's New Zealand source-ingestion decisions. The
canonical wave-1 inventory and acceptance criteria live in
[issue #176](https://github.com/PolicyEngine/chronicle/issues/176); this file is
the repository execution ledger for that issue, not a separate target design.
Chronicle stores publisher-backed facts only. Microcosm owns target selection,
reconciliation, aging, and activation.

## Period convention

IRD labels New Zealand's April-March income tax year by its ending year.
Publisher label "2024 tax year" therefore becomes `tax_year: 2024`, with every
NZ tax-year record set also carrying:

```yaml
period_coverage:
  start_date: 2023-04-01
  end_date: 2024-03-31
  basis: tax
  source_period_label: 2024 tax year
```

This differs from Chronicle's opening-year treatment of split UK labels such as
FY2024-25.

## Geography and aggregation rulings

These decisions implement the rulings recorded in
[issue #175](https://github.com/PolicyEngine/chronicle/issues/175):

- Territorial authorities use `geography_level: local_authority` and
  `geography_vintage: ta_2025`.
- MSD Work & Income regions use `geography_level: statistical_scope`,
  `geography_vintage: msd_wi_region`, and stable `nz-wi-...` slug IDs.
- SA2 is deferred to wave 3, issue #178. When admitted, it will be a
  first-class `sa2` geography rather than `statistical_scope`.
- The original rent-quartile blocker in #175 predates Eurostat #168.
  Chronicle now supports `aggregation: quantile`; publisher quartile cut-points
  can use it with the percentile label or code carried in explicit constraints
  and source evidence, following `eurostat/ilc_di01`. No new aggregation name is
  needed. This removes a vocabulary blocker without expanding #176's package
  scope. Publisher medians use `aggregation: median`; geometric means use
  `aggregation: mean`, `concept_relation: approximate`, and evidence notes that
  explicitly identify the geometric mean.

## Wave-1 ingestion ledger

An unchecked row means that package work remains; it does not imply that the
official source is unavailable. Each completed row must pin the publisher
artifact and checksum, validate its source package, pass its country regression
tests, and record a verified `raw/nz/...` R2 URI.

| Package from #176 | Artifact pinned | Package valid | `raw/nz` verified | Notes |
|---|---:|---:|---:|---|
| `stats_nz/subnational_population_estimates_2025` | [x] | [ ] | [x] | **Partial:** 85 validated workbook counts (16 regions + published NZ total; all ages/four broad age bands). Five-year-age × sex coverage is missing; its ADE structure request returned HTTP 401. Package-completion box stays unchecked. [Evidence and access notes](pe-nz-population-source-notes.md). |
| `stats_nz/national_population_estimates_2025` | [ ] | [ ] | [ ] | **Blocked:** no original-vintage single-year-age artifact acquired. The 19 August 2025 release points to Infoshare, not an XLSX. Landing-page evidence only is hash-pinned in `raw/nz`; it emits zero facts. [Evidence and access notes](pe-nz-population-source-notes.md). |
| `stats_nz/census_2023_households_by_region` | [ ] | [ ] | [ ] | |
| `stats_nz/census_2023_family_type` | [ ] | [ ] | [ ] | |
| `stats_nz/census_2023_ethnicity_age_region` | [ ] | [ ] | [ ] | |
| `ird/taxable_income_distribution_2025` | [x] | [x] | [x] | I1, TY2024 (September 2025 release): 3,522 administrative facts; full national income bands, age marginals, and Tab 4 age × band counts. Raw workbook published to its `raw/nz/ird/...` key and verified by SHA-256 on 2026-10-07. |
| `ird/wage_salary_distribution_2025` | [ ] | [ ] | [ ] | I2 deferred: revised wage/salary workbook is not staged; its direct publisher file URL remains unresolved. |
| `ird/working_for_families_statistics_sept_2025` | [x] | [x] | [x] | TY2024: 330 administrative facts; count/entitlement, children, family size, and full published income table. |
| `ird/student_loan_statistics_march_2026` | [ ] | [ ] | [ ] | |
| `msd/benefit_fact_sheets_national_june_2026` | [x] | [x] | [x] | Row 10: June 2026 supersedes March; 46 administrative count facts, benefit × age, published benefit-status cuts, and separate national supplementary totals. Raw artifact published to its `raw/nz/msd/...` key and verified by SHA-256 on 2026-10-07. |
| `msd/benefit_fact_sheets_supplementary_june_2026` | [x] | [x] | [x] | Row 11: 36 all-ages counts across 11 W&I regions plus Other regions; combined SPB/TAS preserved. No regional AS status split or national reconstruction. Raw artifact published to its `raw/nz/msd/...` key and verified by SHA-256 on 2026-10-07. |
| `msd/nzs_vp_fact_sheet_june_2026` | [x] | [x] | [x] | Row 12: 46 June 2026 NZS/VP recipient count facts, including published additional-support and demographic cuts. Raw artifact published to its `raw/nz/msd/...` key and verified by SHA-256 on 2026-10-07. |
| `msd/annual_report_benefit_expenses_2025` | [x] | [x] | [x] | Row 13: 11 actual FY2024/25 expense facts, fiscal_year 2024, published $000 × 1000. Accommodation Assistance 2,232,026; total 38,267,536 in source $000. Payment-definition evidence absent from staged PDF. Raw artifact published to its `raw/nz/msd/...` key and verified by SHA-256 on 2026-10-07. |
| `mbie/tenancy_bond_rents_tla_2026` | [x] | [x] | [x] | 5,663 administrative facts, August 2025–July 2026, the latest 12 months of MBIE's September 2026 TLA file (published 10 September 2026; MBIE calls the data provisional and subject to revision); 66 TA IDs plus ALL/NA. Raw CSV published to its `raw/nz/mbie/...` key and verified by SHA-256 on 2026-10-09. Source scope and TA-register caveats below. |
| `stats_nz/qes_average_earnings_march_2026` | [ ] | [ ] | [ ] | |

### WFF source semantics

The September 2025 IRD workbook contributes 330 facts for the 2024 tax year.
The national recipient totals describe administrative claims with non-zero
entitlement, not every eligible family or cash paid during the financial year.
The income table uses an entitlement-time-weighted average of assessed family
scheme income. For Work and Income recipients who did not file a WFF return,
IRD uses individual tax-return income, which excludes partner income. These
workbook Explanatory notes qualify the published income bands; this is not the
individual taxable-income universe in the other IRD packages. Numeric band
labels remain source labels until a consumer supplies an evidenced mapping.
Unknown income and the published total remain distinct source rows; the
publisher's rounding-adjustment row is parsed and tested but is not a population
fact. Independently published family and credit totals are not reconciled here.

The workbook was uploaded to the manifest's immutable `raw/nz/ird/...` key and
downloaded again on 2026-08-29. Its SHA-256 remained
`95ae66f4d44f3f47ea3daa006328b22f061a163cf7e31b487342cde649390833`.

### MBIE tenancy bond source semantics

The package pins `detailed-monthly-tla-tenancy-september.csv`, the file MBIE
published on 10 September 2026 (data February 1993 to July 2026), fetched by
the hub on 8 October 2026. It replaces the 23 June 2026 `-v2` file (data to
April 2026), which MBIE no longer links. The package pins the file's latest
12 months, August 2025–July 2026, with the existing full-row parser and
`selected_rows`. MBIE describes the data as provisional and subject to
revision while bond data migrate to a new system, and says to use the latest
file; no revision-final status is supplied. MBIE also warns that recent data
may not be directly comparable with earlier periods: there are 17,550 more
active bonds because the two systems recorded the information differently.
MBIE does not date the change; the ALL row's active bonds rise by 9,075 and
7,347 in November and December 2025, so the window appears to span it. Values
stay as published, unadjusted. The file has a UTF-8 BOM, unquoted
headers without spaces, `d/mm/yyyy` months, newest month first and no
thousands separators; the parser decodes it as `utf-8-sig` and keeps
`TimeFrame` as published text. Seven source measures yield 5,663 facts:
lodged/active/closed bond counts, median and geometric mean weekly rent, and
upper/lower quartile rent cut-points. Geometric mean uses the approximate
mean mapping above; quartiles carry labelled 25/75 percentile constraints and
remain NZD per week, not shares or annual amounts. The log standard deviation
column is preserved as raw rows/cells without a semantic fact because no
faithful aggregation exists in the current vocabulary.

The file has no bedrooms, dwelling-type or arithmetic-mean columns. It also
has no definitions connecting the rent summaries to newly lodged bonds or
active stock. The landing page describes the source database as recording
all new rental bonds lodged each month, by tenancy start date, but does not
define the rent columns, so Chronicle asserts no rent population. Both bond
counts are preserved without treating them as household counts.

There are 66 positive location IDs, plus separately retained ALL and NA.
`ta_2025` follows the checklist ruling; an authoritative register is not staged
and the official ID/name comparison is pending. The file contains no Chatham
Islands row. Missing Kaikoura (August/October 2025, March/June 2026),
Westland (December 2025) and Waimate (January/March 2026) rows remain absent;
the file gives no reason for their omission. MBIE's landing page says counts
use fixed random rounding to base 3 and results are suppressed when there are
fewer than 5 bonds for a selection; Chronicle keeps the published values and
assumes no suppression reason. The manifest's `raw/nz/mbie/...` key was built
with Chronicle's own key builder. The hub published the September CSV with
`chronicle publish-raw` and verified the object by SHA-256 on 2026-10-09.

### MSD June 2026 and annual report source semantics

The quarter-end packages pin `month:2026-06`, retain the publisher's `Jun-26`
label, and record 30 June 2026 as the reference date. They emit published
recipient counts rather than quarter averages. All workbook worksheets remain
source cells, including unused historic quarters, percentages and notes.
Counts are independently randomly rounded to base 3; no totals are reconciled.

The regional workbook states verbatim: “• Supplementary and hardship assistance
data are all ages.” and “• People may be receiving more than one type of
Supplementary Assistance.” It has no national row and no AS cut by main-benefit,
NZS or non-beneficiary status. Its “Special Benefit (SPB) or Temporary Additional
Support (TAS)” row is a combined category, not TAS alone. The national workbook
separately publishes AS recipients as 363,309. The NZS/VP package's AS counts
describe only recipients of those pensions. See the regional package's
[cell evidence](../packages/msd/benefit_fact_sheets_supplementary_june_2026/evidence.md).

The annual report's actual column `2025` describes FY2024/25, 1 July 2024 to
30 June 2025. Chronicle stores the opening year as `fiscal_year:2024`, with the
publisher's column label preserved. Accommodation Assistance is reported as
2,232,026 in $000; it is never relabelled Accommodation Supplement. The staged
210-page PDF does not define its included payments and lists this appropriation
as exempt from reporting. The requested definition remains an open evidence
item; the candidate missing source is the Treasury Vote Social Development
2024/25 Estimates PDF, whose URL is recorded as unverified in the annual package's
[evidence note](../packages/msd/annual_report_benefit_expenses_2025/evidence.md).
All four canonical `raw/nz/msd/...` keys are derived with Chronicle's key builder
from the hub's receipts. The hub published all four objects with `chronicle publish-raw`
and verified each by streaming it back (SHA-256 matches the manifest) on 2026-10-07.

### Taxable-income source semantics (I1)

The staged `taxable-income-distribution-of-individuals-2025.xlsx` is the
September 2025 release, extracted from IRD systems on 12 September 2025. Its
latest published income tax year is **2024**, evidenced by `Income tables
2001-24!BU4`, `BU285`, and the title of `Age by income band distribution!A1`.
Every emitted fact refers to 1 April 2023 to 31 March 2024. The Explanatory
notes, stored as text in `xl/drawings/drawing1.xml` inside the unchanged source,
describe a March-year basis and population data from 2016 onward. Historical
cells are preserved but this package emits only TY2024 observations.

The individual universe is IRD's administrative coverage, including qualifying
children and part-year records, passive-income-only individuals (added with
automatic assessments from 2019), and taxable welfare/NZ Super/earnings-related
ACC income. It excludes nonresident-return filers, individuals with no taxable
income who did not file, and
people whose only income is correctly source-taxed PIE income (`Explanatory
notes!A40:C49`). Taxable income is assessable income less allowable deductions
and claimed losses, excluding exempt and PIE income (drawing 1, shape 2;
`Explanatory notes!A58:C62`). Tax on taxable income applies the publisher's
personal tax scale with IETC and specified IR3/PTS rebates, excluding WFF,
overseas taxes paid that may reduce New Zealand tax payable, donation tax credits,
and other listed rebates (drawing 1, shape 3).
This is the publisher's defined tax calculation, rather than a cash-collection
measure. These source qualifications accompany the facts as concept evidence.

National bands retain all 237 published rows, including `nil`, the
`$0.01    -   $100` band and the negative nil-band tax value at `BW8`.
The national top band is `Over $1,000,000`; Tab 4's top band is
`Over $180,000`. Band spelling and spacing remain publisher labels, including
irregular lower endpoints. No interval endpoints, means, or aligned values are
constructed. The notes place loss-making individuals in the nil band; the graph
notes in `xl/drawings/drawing2.xml` say low-income groups omitted from graphs
remain in the tables.

Tab 4 preserves all 15 age columns, including `Unknown`, and each column's
separately published `All` row. The income sheet also publishes age marginals
and their own total. Those cells remain independent facts: for example,
the income sheet's unknown-age count (`BU303`, 4,990) differs from Tab 4's
unknown-age total (`B189`, 5,050). Totals read the publisher's cached formula
values; Chronicle does not calculate sums of bands or reconcile the different
tables. The package parses the complete used ranges of both data worksheets,
including unselected historical, decile and percentile cells, and preserves
the complete immutable workbook bytes.

The manifest pins receipt SHA-256
`fc7bf7ecdb27a08219cac1ad0cb06cc6bc8de0aae03d605c6ef8d42a15d4b592`,
294,932 bytes, fetched `2026-10-07T19:23:14Z`. Its `raw/nz/ird/...` location
was constructed with Chronicle's key builder. The hub published the workbook
with `chronicle publish-raw` and verified the object by streaming it back
(SHA-256 matches) on 2026-10-07. I2 is not implemented: no revised wage/salary workbook was
staged and the hub must resolve and stage its exact publisher file URL first.

## Additional household wealth source

| Package | Artifact pinned | Package valid | `raw/nz` verified | Notes |
|---|---:|---:|---:|---|
| `stats_nz/household_net_worth_2024` | [x] | [x] | [x] | added for microcosm#592; outside #176's 15. September 2025 HES release: 1,413 published estimates for July 2023–June 2024 (opening-year `fiscal_year:2023`), retained in $000s or household/people 000s. Complete XLSX bytes; Contents and all 14 scoped worksheet ranges preserved. Non-zero-holder and all-household populations remain distinct; seven suppressed estimates stay source cells. Relative sampling errors and percentage changes are omitted from facts and preserved as source cells. CC BY 4.0, Stats NZ attribution; receipt-pinned R2 key awaiting hub upload. [Package scope and evidence](../packages/stats_nz/household_net_worth_2024/README.md). |

## Wave-2 fiscal comparators (#177 subset)

| Package | Artifact pinned | Package valid | `raw/nz` verified | Notes |
|---|---:|---:|---:|---|
| `treasury/an24_01_fiscal_totals` | [x] | [x] | [x] | 27 Treasury-published analytical observations in the TY2019 column; unchanged NZD amounts and verbatim Notes. CC0-1.0. Raw CSV and licence published under `raw/nz/treasury/...` and verified by SHA-256 on 2026-10-07. |

The fiscal totals CSV and its CC0 licence are preserved unchanged at Treasury
repository commit `6e840d54b67bb7f34c63b9d34897e234317445c3`. The package
records Treasury as publisher and uses `assertion: observation` with
`provenance_class: model_output` for its analytical fiscal totals. It does not
recompute Treasury's weighting, excise proportions, or other derivations.
All quantities retain the publisher's `TY2019` column label, represented as
`tax_year: 2019` with 1 April 2018 to 31 March 2019 tax-year coverage. Notes
retain the underlying fiscal-year inputs: PBFF model budget total and Winter
Energy Payment use FY2019 directly. Tax-year coverage describes the published
column, rather than asserting that every input actual covers that span.

In particular, **Accommodation Supplement** is the publisher's Quantity label
for **NZD 1,531,000,000**. Its Notes describe a weighted average of
**Accommodation Assistance** actuals for FY2018 and FY2019. The package preserves
both pieces of evidence; the source does not establish an AS-only cash-paid or
full-entitlement amount. Best Start includes Parental tax credit; Jobseeker
Support includes Emergency Benefit; NZ Super and Vets combines both programmes;
Student loan is a fair-value write-down on new borrowing. These qualifications
remain in each fact's source evidence.

Receipt hashes and sizes pin the CSV and licence. Manifest R2 locations use
Chronicle's `build_r2_key` with explicit `prefix="raw/nz"`; the current publisher
country map does not include Treasury, so the hub must likewise pass
`--r2-prefix raw/nz` when publishing. The locations are declared for the hub's
pre-merge upload and have not been remotely verified by this lane.

The Budget 2026 Estimates and MSD Benefit System Report are outside this
package. Their artifacts were not staged, so no facts from them are emitted.
