# September 2026 QES vintage: publisher-cell evidence

This package preserves the unchanged Stats NZ workbook for the September 2026
quarter, released at 10:45 NZDT on 4 November 2026 (21:45 UTC on 3 November).
It uses `xlsx_used_range` with no sheet restriction, so the parser preserves
every worksheet's rectangular used range (all sixteen worksheets) before fact
selection. The manifest records the hub's fetch receipt: source URL, fetch time
(2026-11-03T21:46:14Z), length (119,004 bytes) and SHA-256
(`d6fb9a947185551292dd6e81a527d994615ae15053b800a11e364ddb915626f3`). The
manifest's `raw/nz/stats_nz/...` key equals `chronicle.artifacts.build_r2_key`
for this package. This change does not verify an R2 copy of the object.
[Release page](https://www.stats.govt.nz/information-releases/labour-market-statistics-september-2026-quarter/).

## Exact scope and vintage ownership

The package emits only Table 7, “Average weekly earnings for FTEs(1)”, “By
sector”, in the same layout as the June 2026 workbook. P6 names the all-sector
group “Total”; P7/P8 identify ordinary time / SBSZ9A, and T7/T8 identify total
/ SBSZ9Z. A8 supplies the `QEMQ` prefix. The two series are `QEMQ.SBSZ9A` and
`QEMQ.SBSZ9Z`, in NZD per week per full-time equivalent employee, actual (not
seasonally adjusted).

| Quarter | Row | P `SBSZ9A` | T `SBSZ9Z` | Same quarter in June 2026 |
|---|---:|---:|---:|---|
| 2024-Q3 | 13 | 1595.11 | 1620.53 | row 14 |
| 2024-Q4 | 14 | 1622.73 | 1651.31 | row 15 |
| 2025-Q1 | 15 | 1637.2 | 1665.72 | row 16 |
| 2025-Q2 | 16 | 1652.72 | 1678.9 | row 17 |
| 2025-Q3 | 17 | 1661.12 | 1687.51 | row 18 |
| 2025-Q4 | 18 | 1681.06 | 1712.05 | row 19 |
| 2026-Q1 | 19 | 1685.39 | 1715.66 | row 20 |
| 2026-Q2 | 20 | 1700.68 | 1729.95 | row 21 |
| 2026-Q3 | 21 | 1714.86 | 1743.23 | not published |

The package emits all nine quarters, 18 facts. Each quarter and series comes
from the newest QES vintage that publishes it, the rule the June 2025 and June
2026 packages follow. September 2026 therefore owns September 2024–June 2026,
and the June 2026 package now emits only June 2024 (its row 13), which this
workbook does not publish. The test suite compares every shared value from the
workbook bytes: June 2026 rows 14–21 agree exactly with rows 13–20 here in
both series (16 comparisons), and June 2025 rows 18–21 agree exactly with rows
13–16 here (8 comparisons). The older vintages keep those cells preserved and
unemitted. Chronicle emits each quarter and series once and constructs no
reconciliation, source arithmetic, annual average, growth rate, ageing factor
or consumer target.

Public/private sector columns, overtime R, percentage-change blocks below the
levels, and all other worksheets stay preserved but unemitted. Footnote 1 at
B49 reads: “Average weekly earnings are calculated by dividing earnings by the
number of FTEs.” This is the publisher's denominator definition; Chronicle
reads the published average and performs no division.

## Period, measurement basis, labels and guards

Facts use `period_type: quarter`, `period: YYYY-Qn`, with calendar quarter
boundaries in period coverage, as in the June 2026 package. Period notes
record the hub-supplied QES source-period definition (the pay week ending on
or before the 20th of the quarter's middle month); the fact period stays the
published quarter.

Every record set states `provenance_class: survey_aggregate`,
`survey_instrument: Quarterly Employment Survey (QES)` and
`assertion: observation` in its own YAML mapping. Labels, dimensions and
measures copy the June 2026 package. Selectors guard the table title, sector,
series prefix, dollar unit, level block, column codes and components, quarter
row headers (C13–C21), year anchors (A13 `2024`, A15 `2025`, A19 `2026`) and
the FTE footnote. Two vintage guards sit on every record set: A13 `2024`, the
first level year, and C13 `Sep`, the first level quarter. A13 alone matches the
June 2026 workbook too; C13 separates the two vintages.

## Licence and provenance limits

The manifest records Stats NZ CC BY 4.0 attribution, using the hub-supplied
[Stats NZ copyright statement](https://www.stats.govt.nz/about-us/copyright/).
The tests check the committed XLSX's hash and length against the hub's fetch
receipt in the manifest; this change fetched no publication or licence pages.
