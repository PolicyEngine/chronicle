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
| `stats_nz/subnational_population_estimates_2025` | [ ] | [ ] | [ ] | |
| `stats_nz/national_population_estimates_2025` | [ ] | [ ] | [ ] | |
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
