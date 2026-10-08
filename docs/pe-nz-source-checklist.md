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
| `ird/taxable_income_distribution_2025` | [ ] | [ ] | [ ] | |
| `ird/wage_salary_distribution_2025` | [ ] | [ ] | [ ] | |
| `ird/working_for_families_statistics_sept_2025` | [x] | [x] | [x] | TY2024: 330 administrative facts; count/entitlement, children, family size, and full published income table. |
| `ird/student_loan_statistics_march_2026` | [ ] | [ ] | [ ] | |
| `msd/benefit_fact_sheets_national_march_2026` | [ ] | [ ] | [ ] | |
| `msd/benefit_fact_sheets_supplementary_march_2026` | [ ] | [ ] | [ ] | |
| `msd/nzs_vp_fact_sheet_march_2026` | [ ] | [ ] | [ ] | |
| `msd/annual_report_benefit_expenses_2025` | [ ] | [ ] | [ ] | |
| `mbie/tenancy_bond_rents_tla_2026` | [ ] | [ ] | [ ] | |
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
