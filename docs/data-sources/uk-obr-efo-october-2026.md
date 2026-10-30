# OBR Economic and fiscal outlook, October 2026 (chronicle#393)

[PolicyEngine/chronicle#393](https://github.com/PolicyEngine/chronicle/issues/393) asks for
the October 2026 EFO, which the OBR published with the Budget on 28 October 2026, as a new
vintage beside the March 2026 one. policyengine-uk is moving its economic assumptions to it
(PolicyEngine/policyengine-uk#2717); Microcosm's OBR targets read the March vintage today and
re-pin when the engine moves (PolicyEngine/microcosm#1095). Every value is a published OBR
figure; no microdata is involved.

`scripts/build_obr_efo_october_2026.py` writes the five packages from the pinned workbooks
(`--check` compares instead of writing).

## Sources

All five are on the [EFO page](https://obr.uk/efo/economic-and-fiscal-outlook-october-2026/),
published on 28 October 2026 under the Open Government Licence (the OBR's
[copyright page](https://obr.uk/legal-pages/copyright/)). obr.uk refuses scripted downloads,
so they were fetched with a browser on 29 October 2026; each manifest pins the bytes.

| Package | File | Bytes | Facts |
|---|---|---|---|
| `obr-efo-receipts-october-2026` | detailed forecast tables: receipts | 214,092 | 1,551 |
| `obr-efo-expenditure-october-2026` | detailed forecast tables: expenditure | 280,700 | 165 |
| `obr-efo-economy-october-2026` | detailed forecast tables: economy | 518,472 | 56 |
| `obr-efo-aggregates-october-2026` | detailed forecast tables: aggregates | 218,000 | 25 |
| `obr-efo-policy-october-2026` | detailed forecast tables: policy | 106,602 | 2,520 |

The manifests carry each file's canonical R2 key; `chronicle publish-raw` uploads them.

## Conventions

- **The vintage.** Record-set ids start `obr.efo_2026_10.`. The March 2026 packages stay in
  the bundle under `obr.efo_2026_03.`, so a consumer picks a vintage by package.
- **March lines.** Every line of the four March packages keeps its line id, display label
  and concept. Its October table is found by title, since the chapters moved by one:
  receipts tables 3.x are now 4.x and expenditure tables 4.x are now 5.x. Its row is found
  by label. Each record set carries its October table and row.
- **Outturn and forecast.** Each year column's assertion follows the band above it.
  'Outturn' (and 'Estimate', 'Estimated Outurn') gives `observation`, and 'Forecast' gives
  `source_projection`; a table with no band is all forecast. 2025-26 is outturn in October
  (it was a forecast in March), and 2031-32 is a new forecast year. The economy tables mark
  no forecast start: calendar 2025 is stamped outturn and 2026 onwards forecast.
- **Units and bases** as each table states them, with the basis note or title as a guard
  cell. Where the stated unit is wrong, the notes say so (table 4.22 below).

## Receipts: the whole workbook

- **The March lines** (42): income tax and NICs (table 4.4), the cash receipts lines
  (4.8, vehicle excise duties among them since chronicle#395), betting and gaming (4.10), tobacco and alcohol clearances (4.11, 4.12), the levies
  (4.2) and SDLT by sector (4.7).
- **Every other row** of tables 4.1 to 4.22, except two tables:
  - 4.9 (air passenger duty passengers by band) states no unit;
  - 4.19 (counterfactual and actual personal tax thresholds) prints '£ billion' over
    thresholds in pounds (a personal allowance of 12,570) and flags no outturn.
- **Naming.** A row beyond the March lines is line `<table key>.<row>` with concept
  `obr.<table key>.<row>`. The table key names the table (`other_hmrc_taxes`,
  `cash_receipts`, `self_employed_income_growth`, `fiscally_neutral_receipts`, ...). Table
  4.8's sub-rows, printed in column C under an 'of which', prefix their parent
  (`corporation_tax_onshore`).
- **Table 4.5, 'Self-employed income streams: growth rates'.** Its 'Savings income' row is
  `obr.self_employed_income_growth.savings_income`, measure `growth_rate`, unit `percent`: a
  percentage change on a year earlier, from 2024-25 to 2031-32. The table prints every
  column under 'Forecast', 2024-25 included, so every fact is a `source_projection`. It has
  no 2023-24 column: the growth from 2023-24 to 2025-26 is 2024-25's 34.96% and 2025-26's
  0.65% (×1.358). The note says the numbers are pre-measures.
- **Gambling.** Table 4.8's cash betting and gaming duties, table 4.10's accrued
  breakdown by duty (machine games duty included; the table now starts in 2026-27, its
  first forecast year), table 4.1's accrued 'Betting and gaming taxes' for 2025-26 (from
  2026-27 it restates table 4.10's total) under the same concept, and table 4.2's levies.
- **Northern Ireland domestic rates** are carried both places the OBR shows them, each with
  its own table and row: receipts table 4.2 row 6 ('Northern Ireland domestic rates',
  under other taxes) and expenditure table 5.1 row 16 ('NI domestic rates', inside net
  council tax receipts). Their values differ; the OBR calls neither regional or district.
- **Restated rows are ported once**, as the March package left out sheet 3.7's total. The
  build asserts each copy equal to the row kept:
  - table 4.7's 'Total SDLT' and ATED rows (table 4.8's rows 24 and 25);
  - table 4.22's VAT refunds, community infrastructure levy, extended producer
    responsibility and five environmental levies (tables 4.8, 4.2 and 4.20);
  - table 4.21's '(c * d + e + f) Forecast' row (table 4.20's contracts for difference, in
    GBP million);
  - table 4.1's 'Betting and gaming taxes' from 2026-27 (table 4.10's total).
- **Cash and accrued taxes.** Tables 4.1 (accrued) and 4.8 (cash) print eight of the same
  taxes: customs duties, landfill tax, aggregates levy, the soft drinks levy, diverted
  profits tax, plastic packaging tax, RPDT and CBAM. Each pair shares one concept
  (`obr.customs_duties`, ...) with `concept_relation: exact` and differs in
  `accounting_basis`, as chronicle#381's excise duties do; each keeps its table's source
  concept. Table 4.1's vaping tax joins the March line's `obr.vaping_tax`. Diverted profits
  tax prints the same values on both bases. Row labels say '(cash)' or '(accrued)', and
  the March lines' measure labels name their basis.
- **Table 4.22** prints '£ million', but its cells are GBP billion: the build checks that
  its VAT refunds equal table 4.8's £ billion line in every year. Its rows carry
  `value_scale` 1e9, with the cell kept as a guard.

## Expenditure, economy and aggregates

- **Expenditure** (165 facts): the March package's 24 lines: council tax by nation and its
  totals, Northern Ireland domestic rates, the welfare lines of table 5.9 and the BBC
  licence fee. October changes two labels: 'England council tax receipts1' gains a
  footnote (its outturn is MHCLG's pre-measures data, not the public sector finances) and
  'Total net council tax receipts' renumbers its footnote. The DWP lines keep the March
  package's geography (Great Britain, or England and Wales where DWP excludes Scotland).
- **Economy** (56 facts): the March package's six lines for calendar 2025 to 2031, plus two
  series PolicyEngine/policyengine-uk#2638's interest projection reads: table 1.9's deposit
  rate (`obr.deposit_rate`) and table 1.11's household financial assets
  (`obr.household_financial_assets`, ONS NNML). The table does not say whether a
  calendar-year row of a stock is the year-end or the average.
- **Aggregates** (25 facts): the March package's four lines. Tables 6.1, 6.2 and 6.5 print
  only forecast years, now 2026-27 to 2031-32; table 6.13 has 2025-26 as outturn.

## Policy

Table 1.1, 'Breakdown of policy decisions since March 2026', in GBP million for 2026-27 to
2031-32, all under 'Forecast':
- one record set per measure and year, concept `obr.policy_decision_costing`, with a row per
  head and category (`policy_head`, `policy_category`) and the measure's total;
- the 98 scorecard measures keep the OBR's numbers (`measure_1` to `measure_98`), and the
  three fiscally neutral and two non-scorecard measures are numbered in table order
  (`policy_section` says which);
- rows 490 to 555, the effects by head and category and the direct and indirect effects of
  the Government's decisions, are one record set per year (`summary`, concept
  `obr.policy_decisions_effect`).

A negative sign is a loss to the Exchequer, as the table's note says. Each measure's rows
sum to its total.

## Annex A and the devolved forecasts

- **Annex A** ('charts and tables: Annex A') was checked against the policy workbook. It is
  the EFO's detailed summary tables (A.1 to A.12: the economy, the determinants of the
  fiscal forecast, current receipts, total managed expenditure, the fiscal aggregates and
  the balance sheet, each with its changes since March). It has no measure rows, so none is
  missing from the policy workbook, and it is not archived. Its Table A.5 'other' lines are
  the ones receipts tables 4.1 to 4.3 break down, as their footnotes say.
- **The devolved tax and spending forecasts** are optional in #393 and not ported.

## For Microcosm

Re-pin the UK feed to the merge commit first. Then select the October vintage by package:
- the March lines under `obr.efo_2026_10.<kind>.<line id>.fy<year>`, with the March
  concepts;
- Table 4.5's savings income from `obr-efo-receipts-october-2026`, as above.

**No 2024-25.** Every one of the 33 lines Microcosm selects runs from 2025-26 (outturn) to
2031-32 in October; the tables no longer print 2024-25. So the calendar-2025 window (three
twelfths of 2024-25 and nine of 2025-26) can't be built from the October package alone. Its
2024-25 part has to come from the March package's 2024-25 outturn
(`obr.efo_2026_03.<kind>.<line id>.fy2024`, an `observation` there) or from ONS.

Both vintages forecast the March lines for 2026-27 to 2030-31 (receipts and expenditure)
and 2026 to 2029 (economy and aggregates), so the bundle reports their 363 shared semantic
keys as duplicates; a target binds one vintage. Aligning fiscal years with the calendar-2025
window, and choosing between the two Northern Ireland domestic rates placements, are the
consumer's decisions.
