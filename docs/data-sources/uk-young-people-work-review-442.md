# Young people and work review facts for chronicle#442

[chronicle#442](https://github.com/PolicyEngine/chronicle/issues/442) asks for the published
facts behind young people's health-related benefits that the benchmarks check of the Milburn
review dashboard (PolicyEngine/uk-milburn-review-dashboard#1) found missing. Microcosm UK's
targets and diagnostics, and the dashboard's benchmarks tab, read them.

Two packages add 117 facts, all from DWP's publications for the Young People and Work review
under the Open Government Licence v3.0, with no microdata.
- **Generator:** `scripts/build_uk_young_people_work_review_packages.py` writes both from the
  pinned workbooks, asserting the publisher's text. `--check` compares the output with the
  committed YAML.
- **Tests:** `tests/test_source_uk_young_people_work_review.py` re-reads the workbooks with an
  ODS reader of its own and matches every fact to its cell.
- **Files:** both are committed and in R2 (`chronicle publish-raw`, read back by
  `chronicle verify-raw`).

## Sources

| Package | File | Publisher, date | sha256 |
|---|---|---|---|
| `dwp-young-people-pip-lcwra-projections-2026` | `analytical-annex-data-tables.ods` | DWP, [Young people and work: interim report](https://www.gov.uk/government/publications/young-people-and-work-interim-report), analytical annex data tables, published 28 May 2026, file replaced 10 August 2026 | `8a3270e3…` |
| `dwp-welfare-state-to-working-state-tables-2026` | `from-a-welfare-state-to-a-working-state-accompanying-data-tables.ods` | DWP, [From a Welfare State to a Working State: a new settlement for the next generation](https://www.gov.uk/government/publications/from-a-welfare-state-to-a-working-state-a-new-settlement-for-the-next-generation), data tables, 17 November 2026 | `eb182010…` |

The interim report's page records one change to the data tables: on 10 August 2026 "an error
in the Excel formula" was corrected in Table 23, and "No changes have been made to the main
report or the analytical annex". The pinned file is that corrected edition (GOV.UK serves it
with a last-modified date of 10 August 2026).

## Item 1: the interim report's Table 28

Table 28, "PIP and UCH-LCWRA caseload and expenditure projections, aged 16-24", prints four
rows for every financial year from 2019-20 to 2040-41, not only the three years #442 lists:

| Row | Unit | Rounding (the table's notes) |
|---|---|---|
| UC health element (LCWRA), caseload | people | nearest 1,000 |
| UC health element (LCWRA), expenditure | £ million | nearest £10 million |
| PIP, caseload | people | nearest 1,000 |
| PIP, expenditure | £ million | nearest £100 million |

How the facts are typed:
- **Concepts.** The caseloads and spending sit on DWP's own concepts,
  `dwp.benefit_caseload_count` and `dwp.benefit_expenditure_amount`, as
  `dwp-benefit-expenditure-caseload-spring-2026` uses them. The benefit is the filter
  `health_and_disability_benefit` (`uc_health_lcwra`, `personal_independence_payment`).
- **Who.** `age_band` `16_to_24` (ages 16 to 24) in England and Wales (`K04000001`), as the
  table's "Population: England and Wales" says. Caseloads are `person` / `claimant`; spending
  is `government` / `payer`, scaled from £ million to pounds.
- **People, not households.** The analytical annex (section 18) defines the UC health caseload:
  "UC Health (UC-H) in this analysis refers to claimants in receipt of the 'limited capability
  to work' element, also known as the 'health element', which is offered to claimants receiving
  a LCWRA WCA outcome". Microcosm's bound row `dwp.uc.households_lcwra_element` counts
  households, so the two differ in unit as well as in age.
- **Outturn and projection.** The table's period line reads "Period: 2026-27 to 2040-41", the
  annex's "fifteen-year caseload projections". The annex adds: "PIP and UC-H / LCWRA caseload
  and expenditure forecasts for 16 to 24 year olds are based on data from Stat-Xplore and
  Autumn Budget 2025 benefit caseload and expenditure tables". Those tables still forecast
  2025-26, and `dwp-benefit-expenditure-caseload-spring-2026` types the year the same way.
  So:
  - 2025-26 to 2040-41 are DWP's projections (`model_output`, `source_projection`), 2025-26
    included although the period line starts a year later;
  - 2019-20 to 2024-25, outturn years in those tables, are the series' history
    (`administrative`, `observation`).
- **Price basis.** Neither the table nor the annex names one, so none is asserted. The annex
  projects average awards "capped so that weekly amounts cannot exceed maximum award levels".

Read them this way:
- **An indication, not a forecast of record.** The annex: "Forecast outputs have used a simple
  methodology and should be treated as an indication only. Forecast estimates are based on the
  proportion of young people and therefore may not align with published benefit expenditure
  and caseload tables." They are compared with the Autumn Budget 2025 forecasts for PIP and DLA
  to 2031, with "an average uplift" assumed after.
- **Annex cross-check.** The annex's findings quote the table, and the generator asserts each:
  - PIP spending of "approximately £1.3 billion" in 2019-20 and "around £3.3 billion" in
    2024-25;
  - "£6.5 billion and cover 700,000 young people" in 2031-32;
  - PIP at "877,000 and £9.2 billion" in 2040-41;
  - UC health at "229,000" and "£750 million" in 2040-41.
- **Cover sheet slip.** The workbook's cover prints "Published:28 May 2025"; GOV.UK published
  the report on 28 May 2026.
- **Not ported:** the workbook's other 57 tables.

## Item 2: the final report's data tables

The final report's data tables hold three tables, and none carries young people's PIP or UC
health caseloads or spending. The report's analytical annex (section 9) takes its 2036/37 PIP
and DLA caseloads from "forecasts ... produced for the Young people and work: interim report",
which item 1's package carries. The package ports the two comparators #442 asks for. Both are
the review's "internal modelling" (`model_output`, `source_projection`), and the tables'
guidance says the analysis "should not be regarded as official government analysis or as
representing agreed government policy".

**Table 2, "Annual cost and saving per policy area in 2036/37, £m, 2026/27 prices".** Seven
facts on `dwp.recommended_policy_package_annual_cost`, filters `policy_area` and
`price_basis` `2026_27_prices`, period 2036-37. Costs are positive and savings negative, as
printed, "rounded to the nearest £100 million". The annex says "The geographical coverage of
the costs vary, in part depending on the devolved responsibilities of the departments
involved", so each row carries the coverage the annex states for it:

| Policy area | £m | Geography | Concept relation |
|---|---|---|---|
| Opportunity and Support Guarantees | 1,900 | Great Britain | `source_label` |
| Health | 700 | England | `source_label` |
| Education | 2,100 | England | `source_label` |
| Youth hiring incentives | 1,100 | Great Britain | `approximate` (grants Great Britain, apprenticeships England only) |
| Welfare savings | -3,600 | United Kingdom ("PIP and UC expenditure across the UK") | `source_label` |
| Fiscal offsets | -2,400 | United Kingdom | `approximate` (the annex states no coverage) |
| Total NET Cost | -200 | United Kingdom | `approximate` (sums every area) |

"Local system reform" prints "[low]", which the notes define as "a negligible figure, i.e. a
figure that rounds to zero but is not zero" (the annex: "less than £100m"). It emits no fact,
and the other rows sum to the total.

**Table 3, "Total NEET rate impact profile, UK, 2026/27 to 2036/27".** The title's last year is
a slip: the columns run 2026/27 to 2036/37. The table holds 22 facts on
`dwp.neet_rate_projection`, for 16 to 24 year olds in the United Kingdom, in percent rounded to
one decimal place. The filter `neet_rate_projection` takes two values:
- `baseline`: "Projected baseline NEET rate";
- `with_report_recommendations`: "Projected NEET rate with report recommendations".

The annex (section 2) says the baseline "was derived from a central, seasonally-adjusted NEET
projection scenario from Youth Futures Foundation (YFF) SARIMAX modelling", which "DWP and DfE
internal analysis" then adjusted. The generator asserts:
- the two rows agree in 2026/27;
- the recommendations lower the rate every later year;
- the annex's "NEET rate of around 6.8%" holds in 2036.

Not ported: Table 1, "Average annual investment in major NEET schemes", whose schemes' periods
the table does not give.

## Items 3 and 4: nothing new to package

- **Item 3, LCWRA households by claimant age.** Stat-Xplore's Households on Universal Credit
  cube (`str:database:UC_Households`) has no field for the claimant's age. Its age fields are
  the number of children by age and the age of the youngest child. People on Universal Credit
  (`str:database:UC_Monthly`) has the claimant's age but no capability for work field. No
  Universal Credit cube crosses LCW entitlement with claimant age. The nearest published fact,
  people on UC by age and conditionality regime, is already in Chronicle
  (`dwp-uc-people-country-age-conditionality-regime-april-2024-may-2026`).
- **Item 4, HMRC's employer NICs reliefs.** HMRC's tax relief statistics are still at the
  January 2026 edition. `hmrc-employer-nics-age-reliefs-january-2026` (PolicyEngine/chronicle#420
  item 9) already carries what the item asks for:
  - Table 2's cost of NIC-NS1 and NIC-NS2, 2020-21 to 2025-26, with 2025-26 as HMRC's forecast;
  - Table 5's employers claiming each relief;
  - HMRC's note that the apprentice relief takes precedence for apprentices under 21.

  Its pinned workbook is the file GOV.UK serves today.
