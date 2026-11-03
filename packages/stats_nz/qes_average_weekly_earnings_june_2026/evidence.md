# QES average weekly earnings: publisher-cell evidence

Two packages preserve the unchanged Stats NZ June 2025 and June 2026 quarterly
employment workbooks. Both use `xlsx_used_range` with no sheet restriction:
every worksheet's rectangular used range is preserved before fact selection.
Source URLs, receipt timestamps, lengths and SHA-256 hashes are in each manifest;
the canonical `raw/nz/stats_nz/...` keys are generated with
`chronicle.artifacts.build_r2_key`. The hub published both objects to those keys
on 2026-10-23 and verified each by streaming it back and matching its SHA-256.

## Exact scope and vintage ownership

Only Table 7, “Average weekly earnings for FTEs(1)”, “By sector”, is emitted.
P6 names the all-sector group “Total”; P7/P8 identify ordinary time / SBSZ9A,
and T7/T8 identify total / SBSZ9Z. A8 supplies the `QEMQ` prefix. The two
series are `QEMQ.SBSZ9A` and `QEMQ.SBSZ9Z`, in NZD per week per full-time
equivalent employee, actual (not seasonally adjusted).

| Package | Source rows | Published quarters | Facts |
|---|---|---|---:|
| `stats_nz/qes_average_weekly_earnings_june_2025` | Table 7 rows 13–16, P/T | June 2023–March 2024 | 8 |
| `stats_nz/qes_average_weekly_earnings_june_2026` | Table 7 rows 13–21, P/T | June 2024–June 2026 | 18 |

The June 2025 file also publishes June 2024–June 2025 in rows 17–21. All
five overlapping quarters agree exactly in both P and T against June 2026
rows 13–17 (ten comparisons, checked independently from workbook bytes).
Those older-vintage overlap cells remain preserved but are not emitted. Each
quarter/series is emitted once. No reconciliation, source arithmetic, annual
average, growth rate, aging factor or consumer target is constructed.

Public/private sector columns, overtime R, percentage-change blocks below the
levels, and all other worksheets are preserved but not emitted. Footnote 1
at B49 reads: “Average weekly earnings are calculated by dividing earnings by
the number of FTEs.” This is the publisher's denominator definition; Chronicle
reads the published average and performs no division.

## Period, measurement basis and labels

Facts use Chronicle's existing `period_type: quarter`, `period: YYYY-Qn`
convention (also used by `ofgem/energy_price_cap_q1_2024`), with calendar
quarter boundaries in period coverage. The QES source-period definition
supplied by the hub is the pay week ending on or before the 20th of the
quarter's middle month. It is recorded in period notes and is not substituted
for the published quarter. The staged Table 7 does not itself repeat that
methodological definition.

Every record set explicitly declares `provenance_class: survey_aggregate`,
`survey_instrument: Quarterly Employment Survey (QES)` and
`assertion: observation`. Labels and dimensions retain series reference,
ordinary-time/total component, all-sector scope, FTE denominator and actual
(not seasonally adjusted) status. Selectors guard the table title, sector,
series prefix, dollar unit, level block, column codes/components, quarter,
year anchor, workbook vintage and FTE footnote. Independent literal cell
maps and source/YAML mutants cover their failure modes.

## Licence and provenance limits

Stats NZ CC BY 4.0 attribution is recorded in both manifests, using the
hub-supplied [Stats NZ copyright statement](https://www.stats.govt.nz/about-us/copyright/).
The build verified each committed XLSX's hash and length against the hub's
fetch receipt, whose URL, timestamp, length and SHA-256 the manifests record;
it did not fetch publication or licence pages. The publisher release pages are
linked in the manifests. The raw objects are on R2 and verified by SHA-256
(2026-10-23).
