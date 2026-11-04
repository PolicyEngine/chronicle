# UK occupation facts for chronicle#407

[chronicle#407](https://github.com/PolicyEngine/chronicle/issues/407) asks for published
occupation totals that Microcosm UK can check its new occupation variable against
([PolicyEngine/microcosm#1490](https://github.com/PolicyEngine/microcosm/issues/1490)):
the Annual Population Survey's people in employment by SOC 2020 major and sub-major group,
from Nomis, and ASHE Table 2's earnings by two-digit SOC. Both are ONS publications of
aggregates under the Open Government Licence v3.0. No survey microdata is read or stored;
the values are the publisher's own cells, with the publisher's suppression.

`scripts/build_uk_occupation_packages.py` writes the fifteen packages from the pinned bytes
and asserts the publisher's text cell by cell. `--check` compares its output with the
committed YAML, and `tests/test_source_uk_occupation_facts.py` runs it.

## Sources

| Packages | File | Publisher, date | sha256 |
|---|---|---|---|
| `ons-aps218-occupation-apr-2024-mar-2025` | `aps218_occupation_apr_2024_mar_2025.csv` | Nomis APS218, Apr 2024-Mar 2025, released 17 July 2025 | `15f0cc06…` |
| `ons-aps218-occupation-jan-dec-2025` | `aps218_occupation_jan_dec_2025.csv` | Nomis APS218, Jan 2025-Dec 2025, released 21 April 2026 | `656944f1…` |
| `ons-aps218-occupation-apr-2025-mar-2026` | `aps218_occupation_apr_2025_mar_2026.csv` | Nomis APS218, Apr 2025-Mar 2026, released 21 July 2026 | `12deddc0…` |
| `ons-ashe-table2-{weekly,annual}-pay-gross[-cv]-2024-revised` | `ashetable22024revised.zip` | ONS, ASHE Table 2, 2024 revised, released 23 October 2025, corrected 3 November 2025 | `68481328…` |
| `ons-ashe-table2-{weekly,annual}-pay-gross[-cv]-2025-revised` | `ashetable22025revised.zip` | ONS, ASHE Table 2, 2025 revised, 22 October 2026 | `99c6b4ca…` |
| `ons-ashe-table2-{weekly,annual}-pay-gross[-cv]-2026-provisional` | `ashetable22026provisional.zip` | ONS, ASHE Table 2, 2026 provisional, 22 October 2026 | `a376d72d…` |

Each Nomis file is one pinned API response; its manifest records the query and Nomis's
revision metadata for the period. Each ASHE zip is shared by four packages, one per
workbook member. All six files are committed; none is in R2 yet, so the consumer export
fails with `missing_contract_provenance: source.raw_r2_uri` until `chronicle publish-raw`
uploads them.

## 1. Annual Population Survey: people in employment by occupation (Nomis APS218)

Nomis dataset APS218 (`NM_218_1`), "annual population survey - regional - occupation
(SOC2020) by sex by employment type". Three packages, 24,956 facts.

- **What is ported:** the count of people in employment, and the half-width of its
  confidence interval where Nomis publishes one, by:
  - all occupations, the nine SOC 2020 major groups and the 26 sub-major groups;
  - sex: all persons, males, females;
  - employment type: all, employees, self-employed;
  - the UK, England, Wales, Scotland, Northern Ireland and the nine English regions.
- **Not ported:**
  - Nomis's fourth employment type, "Other", which "includes unpaid family worker", so
    employees and the self-employed do not add to all;
  - the full-time/part-time and permanent/temporary splits; every fact is their total;
  - the "Rate" measure, each cell's share of all in employment in the area;
  - minor and unit groups (the four-digit tables are out of scope).
- **Semantics:**
  - Concept `ons.aps_people_in_employment`, entity `person`, role `in_employment`,
    `survey_aggregate`, survey instrument `Annual Population Survey`.
  - Residence based: Nomis describes the APS as "a residence based labour market survey".
  - Nomis rounds every count to the nearest hundred.
- **Dimensions:**
  - `sex` (`all`, `male`, `female`);
  - `employment_status` (`all`, `employee`, `self_employed`);
  - `statistic` (`estimate`, `confidence_interval_half_width`);
  - `soc2020_major_group` (1 to 9) on major-group facts, `soc2020_sub_major_group` (11
    to 92) on sub-major facts;
  - the record sets' groupby axis is `soc2020_group`, whose `all` rows are totals.
- **Confidence intervals:** Nomis labels the measure "Confidence" and publishes it beside
  each estimate as a plus-or-minus half-width. Its dataset pages do not state the level.
  Scottish Government APS publications call the limits Nomis publishes 95 per cent
  limits, so the value is `confidence_interval_half_width`, not `ci_95_half_width`.
- **Reliability flags.** Nomis flags every cell in its status column:
  - A, "Normal Value";
  - F, "Estimate and confidence interval not available since the group sample size is
    zero or disclosive (0-2)";
  - G, "Estimate and confidence interval unreliable since the group sample size is small
    (3-9)";
  - H, "Estimate is less than 500".

  A blank cell (F or H) emits no fact. Nomis marks an interval G, and in a few dozen
  cells per period F, while still printing the estimate. That estimate is ported with its
  interval's status cell guarded, so the flag is in the fact's source-cell lineage, and
  no interval fact is emitted. Chronicle's fact model has no quality field, so the flag
  is not a fact field; a consumer can tell these estimates by the missing interval fact.
- **Periods.** Nomis publishes rolling twelve-month periods every quarter. Chronicle's
  period types cover the April-to-March and January-to-December windows only:
  - Apr 2024-Mar 2025 is `fiscal_year` 2024 (the FRS 2024-25 year);
  - Jan 2025-Dec 2025 is `calendar_year` 2025;
  - Apr 2025-Mar 2026 is `fiscal_year` 2025;
  - the exact dates are in `period_coverage` (basis `survey_reference`), as the
    house-price packages store a year ending in March.

  Jul 2025-Jun 2026, the latest period, and the other July-to-June and
  October-to-September windows have no period type and are not ported.
- **Revision note.** Nomis's metadata records one revision of the dataset: on 27 January
  2023 it re-released October 2021 to September 2022, "Estimates revised due to
  identified error". That period is not ported. The three ported periods are each
  revision 0. Every package header and manifest records this.
- **Parity**, asserted by the generator and the test on the published estimates:
  - each major group's sub-major groups add to it, within rounding (50 per summed cell);
  - the four countries add to the UK, and the nine regions to England, within rounding;
  - the nine major groups add to less than the all-occupations total, never more beyond
    rounding. The gap is at most 0.51, 0.36 and 0.34 per cent of the total in the three
    periods in order, and 0.13 to 0.14 per cent for the UK's all persons. Nomis publishes
    no residual
    category, so the difference is people in employment in the total and in no major
    group. The issue's "major groups sum to the total, within rounding" therefore holds
    as a bound, not as an equality.

## 2. ASHE Table 2: earnings by two-digit SOC

ONS's [ASHE Table 2](https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/earningsandworkinghours/datasets/occupation2digitsocashetable2),
United Kingdom. Twelve packages, 48,083 facts.

- **Editions and tables.** For each edition (2024 revised, 2025 revised, 2026
  provisional):
  - Table 2.1a, gross weekly pay, and Table 2.7a, gross annual pay;
  - Tables 2.1b and 2.7b, the coefficients of variation ONS publishes for them.
- **Rows and sheets.** Every sheet but the notes: all employee jobs, male, female,
  full-time, part-time and the four sex by working-pattern sheets. Each sheet's "All
  employees" row, its nine major groups and its 26 sub-major groups.
- **Measures:**
  - the number of jobs (thousand), which ONS calls "for indicative purposes only";
  - the median, the mean and the 10th, 20th, 25th, 30th, 40th, 60th, 70th, 75th, 80th
    and 90th percentiles;
  - the annual percentage changes are not ported.
- **Concepts:**
  - `ons.ashe_gross_weekly_pay` and `ons.ashe_gross_annual_pay`: aggregation `median`,
    `mean` or `quantile` (with `earnings_percentile`), unit `gbp`;
  - `ons.ashe_weekly_pay_jobs` and `ons.ashe_annual_pay_jobs`: the indicative job counts,
    which differ between the tables because their populations differ;
  - entity `person`, role `employee_job`, as the ASHE pension packages use.
- **Dimensions:** `sex`, `working_pattern` (`all`, `full_time`, `part_time`),
  `statistic` (`estimate` or `coefficient_of_variation`), and `soc2020_major_group` or
  `soc2020_sub_major_group`.
- **Jobs, not people.** ASHE "is based on a 1% sample of jobs taken from HM Revenue and
  Customs' Pay As You Earn (PAYE) records", so someone with two jobs can appear twice. It
  "does not cover the self-employed".
- **Periods:**
  - Weekly pay relates to the pay period that includes the survey reference date, so it
    is `calendar_year` Y with that date in `period_coverage`: 17 April 2024, 30 April
    2025 and 22 April 2026, from the bulletins.
  - Annual pay is "for the tax year that ended on 5th April in the reference year", so it
    is `tax_year` Y-1 (6 April to 5 April). It covers employees in the same job for more
    than a year.
- **Quality markers.** The estimate tables show each cell's CV band only by colour, which
  Chronicle does not read, and print "x" where the CV is over 20 per cent ("Estimates
  with a CV greater than 20% are suppressed from publication on quality grounds"). So:
  - each CV is ported as its own fact, which carries the band;
  - an "x" cell emits no fact, and neither does a CV cell marked "." ("unavailable" in
    the CV key), found only in the 2024 tables;
  - a row with such a cell sits in a record set whose measures leave that column out
    (`…without_p90` and the like), so the row's other cells are ported;
  - the "Not Classified" row prints ":" ("not applicable") and emits no fact.

  In 2025 and 2026 the two tables mark the same cells "x". The 2024 CV tables still print
  the CV of each estimate suppressed for a CV over 20 per cent (53 weekly and 85 annual
  cells), and those CVs are ported.
- **Corrections:**
  - 3 November 2025: ONS first published the 2024 provisional data as the 2024 revised
    table, on 23 October 2025, and then replaced it. The pinned zip, fetched on 4
    November 2026, is the corrected table.
  - 19 December 2025: ONS suppressed the 2025 provisional annual pay estimates for
    occupations 3312, 331 and 33 (police) for London, the South East, East and the UK.
    Table 2 is two-digit, so only sub-major group 33's UK row is affected. The 2025
    provisional Table 2.7a prints "x" for that row's pay in every sheet; the 2025 revised
    Table 2.7a restores it, keeping "x" only where a part-time CV is over 20 per cent.
    The 2025 provisional edition is not ported.
- **Parity.** Each edition's full-time all-employees median matches the bulletin's
  headline to the bulletin's rounding:

  | Edition | Weekly (Table 2.1a) | Annual (Table 2.7a) | Bulletin |
  |---|---|---|---|
  | 2024 revised | 728.3 | 37,439 | "£728.27 in April 2024", "£37,439" ([Employee earnings in the UK: 2025](https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/earningsandworkinghours/bulletins/annualsurveyofhoursandearnings/2025)) |
  | 2025 revised | 766.6 | 39,157.2 | "£766.60 in April 2025", "£39,157" ([Employee earnings in the UK: 2026](https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/earningsandworkinghours/bulletins/annualsurveyofhoursandearnings/2026)) |
  | 2026 provisional | 811.2 | 40,911.2 | "£811.20 in April 2026", "£40,911" (the same bulletin) |

## Labels

Both sources word the SOC 2020 groups their own way: Nomis capitalises them and cuts
major group 1 short. Every row is therefore labelled in ASHE Table 2's wording, and each
row's guards compare the publisher's own text.

The values these packages share are added to
`chronicle/dimension_values/canonical_labels.json`, each with the one wording the packages
use:

- `soc2020_group`: 36 values;
- `soc2020_sub_major_group`: 26 values;
- `employment_status`, `working_pattern`: 3 values each;
- `earnings_percentile`: 10 values;
- `statistic`: `confidence_interval_half_width` and `coefficient_of_variation`.

The register's label for `soc2020_major_group` 3 changes from "Associate professional and
technical occupations", the SOC 2010 name the ASHE pension tables print, to SOC 2020's
"Associate professional occupations", the name ASHE Table 2 and Nomis print. Fifteen
packages word it this way against the pension tables' five, so it follows the register's
majority rule; `CHOSEN_LABELS` records the choice. The five pension packages' declarations
follow the register, and their row headers keep ONS's text.
