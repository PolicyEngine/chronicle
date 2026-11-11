The primary fact source is the Treasury's *Expenditure - Budget 2026 Data
from the Estimates of Appropriations 2026/27* workbook. `Intro!A2` records
publication on 28 May 2026; `Intro!A4` identifies the New Zealand Treasury.
The hub found the workbook on
<https://www.budget.govt.nz/budget/2026/estimates/data.htm> and staged its
unchanged bytes from
<https://www.budget.govt.nz/budget/excel/data/b26-expenditure-data.xlsx>.
The receipt records 918,842 bytes, fetched `2026-10-10T08:33:39Z`, SHA-256
`3fc6bba178c78c4a4b259c920a6f55307ec95a547353f340086c86fc2a26f5a0`.

The second artifact is *Vote Social Development – The Estimates of
Appropriations 2026/27 – B.5 Vol.9*, staged from
<https://budget.govt.nz/budget/pdfs/estimates/v9/est26-v9-socdev.pdf>.
The receipt records 2,212,387 bytes, fetched `2026-10-10T08:31:09Z`, SHA-256
`85ff85e5b93a8b3e3ef7442a034eb8d3abdd0f1675f76646afad8311d8e30c23`.
It has 132 PDF pages and contributes scope and conditions evidence only.
None of its figures is emitted as another fact. The hub published both
manifest-declared objects to their content-addressed `raw/nz/treasury/...`
R2 keys with `chronicle publish-raw --r2-prefix raw/nz` and verified each by
streaming it back (SHA-256 matches) on 2026-10-10.

The licence is `CC BY 4.0`. In addition to the hub's copyright-page check,
the workbook itself states the licence at `Intro!A13`. `Intro!A14` requires
written attribution to the Crown and prohibits infringing use of departmental
or governmental emblems, logos or the Coat of Arms. This package attributes
the work to the Crown / New Zealand Treasury.

The package selects every `Raw Data` row whose `Vote` is `Social Development`
and `Appropriation or Category Type` is `Benefits or Related Expenses`.
There are 112 rows and each yields one separately published fact. Other Votes
and the pivot sheets contribute no facts. The workbook has 17 `Raw Data`
columns, `A:Q`: the additional status field is **`Amount Type` in `M1`**,
following `Amount $000` in `K1` and `Year` in `L1`; it is not an unnamed
column. `Explanation!B42` defines `Actuals` as audited prior-year amounts,
`Estimated Actual` for the year immediately prior to the current Main
Estimates, and `Main Estimates` for the Main Estimates year.

| Publisher `Year` (ending 30 June) | `Amount Type` | Selected rows | Chronicle period | Assertion |
|---|---|---:|---|---|
| 2022 | Actuals | 19 | `fiscal_year:2021` | `observation` |
| 2023 | Actuals | 18 | `fiscal_year:2022` | `observation` |
| 2024 | Actuals | 18 | `fiscal_year:2023` | `observation` |
| 2025 | Actuals | 19 | `fiscal_year:2024` | `observation` |
| 2026 | Estimated Actual | 19 | `fiscal_year:2025` | `source_projection` |
| 2027 | Main Estimates | 19 | `fiscal_year:2026` | `source_projection` |

`Explanation!B3` gives actual expenditure for years ended 30 June 2022–2025,
estimated actual expenditure for the year ending 30 June 2026 and budgeted
expenditure for the year ending 30 June 2027. `Explanation!B40:B41` declares
the amounts in thousands and `Year` as the year ending at 30 June. Chronicle
uses the opening-year `fiscal_year` convention already used by the MSD annual
report package, records 1 July to 30 June coverage, and preserves the
publisher's ending-year label in `source_period_label`. `value_scale: 1000`
normalizes $000 to NZD; no averages or growth rates are calculated.

Chronicle's existing assertion vocabulary is `observation` and
`source_projection` (`chronicle/core.py`, `ALLOWED_ASSERTIONS`). Its fact
definition distinguishes measured or administered outcomes from the
publisher's projections. The audited `Actuals` therefore use `observation`.
The provisional `Estimated Actual` is the publisher's estimate of an outcome,
so `source_projection` is the closest existing value; the schema has no
separate estimated-actual assertion. The future `Main Estimates` amounts also
use `source_projection`. The original `Amount Type` stays explicit for every
row, so estimated actual and budget amounts remain distinguishable.

`Explanation!B10` says the workbook supports the official Budget documents
and identifies the printed Estimates and Supplementary Estimates as official
sources. `Explanation!B17` identifies the Crown's Financial and Information
System as the source and excludes 2025/26 Supplementary Estimates data.
`Explanation!B21` warns that historical agency-reported data have not been
restated for subsequent restructuring and can differ from Part 1.2 totals.
`Explanation!B23` says the 2026/27 appropriation name and scope are applied
to earlier years if the department has not advised of material scope changes
requiring a new appropriation. These are publisher qualifications; Chronicle
does not restate history or reconcile any columns or sources.

The following exact workbook cells anchor the amounts in source $000:

| Appropriation | App ID | Amount cell | `Year` cell | `Amount Type` cell | Amount $000 |
|---|---:|---|---|---|---:|
| Accommodation Assistance | 12381 | `K4783` | `L4783` = 2025 | `M4783` = Actuals | 2,232,026 |
| Accommodation Assistance | 12381 | `K4797` | `L4797` = 2026 | `M4797` = Estimated Actual | 2,308,335 |
| Accommodation Assistance | 12381 | `K4816` | `L4816` = 2027 | `M4816` = Main Estimates | 2,322,160 |
| New Zealand Superannuation | 5406 | `K4821` | `L4821` = 2027 | `M4821` = Main Estimates | 26,481,340 |
| Jobseeker Support and Emergency Benefit | 10803 | `K4807` | `L4807` = 2027 | `M4807` = Main Estimates | 5,018,386 |
| Sole Parent Support | 10804 | `K4808` | `L4808` = 2027 | `M4808` = Main Estimates | 2,473,973 |
| Supported Living Payment | 10805 | `K4809` | `L4809` = 2027 | `M4809` = Main Estimates | 3,023,208 |

The FY2024/25 Accommodation Assistance amount is the same published
2,232,026 $000 as the MSD annual report package; both refer to
`fiscal_year:2024`. This comparison establishes matching source values and
periods, without merging or reconciling their independent publisher claims.

The PDF summary at printed page **187**, PDF zero-based index **4**
(one-based PDF page **5**), identifies `Accommodation Assistance (M63) (A25)`.
It prints 2,361,935 for 2025/26 Final Budgeted, 2,308,335 for Estimated Actual,
and 2,322,160 for 2026/27 Budget, all in $000. Only the workbook's selected
rows yield facts; the PDF Final Budgeted amount is neither added nor
reconciled against the workbook. The scope is repeated on printed page
**243**, PDF zero-based index **60** (one-based PDF page **61**):

> This appropriation is limited to payments for accommodation costs, paid in accordance with criteria set out in, or in delegated legislation made under, the Social Security Act 2018.

The *Conditions on Use of Appropriation* table on printed page **245**, PDF
zero-based index **62** (one-based PDF page **63**), supplies two distinct
payment rows. The following transcribes both reference and conditions cells
verbatim, with PDF layout line breaks retained:

> Accommodation Supplement is paid under section
> 65 of the Social Security Act 2018
>
> The Accommodation Supplement provides a 70 percent subsidy for housing costs that
> exceed a set percentage of the recipient’s ‘base rate’ income (for renters, boarders or
> homeowners), up to a set maximum amount. The level of assistance depends on the
> recipient’s accommodation costs, tenure type, benefit payment rate, where the recipient
> lives and on their family size. The Supplement is a non-taxable payment that is asset-
> tested and income-tested.

> Away from Home Allowance is paid under the
> Away from Home Allowance Welfare Programme
> pursuant to section 124(1)(d) of the Social
> Security Act 1964 saved by clause 21 of Schedule
> 1 of the Social Security Act 2018 as if it were a
> special assistance programme approved and
> established under section 101 of the Social
> Security Act 2018
>
> Away from Home Allowance provides targeted assistance to caregivers with the
> accommodation costs of a dependent 16-17 year old who moves away from home to
> undertake tertiary study or an approved employment related training course. The level of
> Allowance is based on the same formula as for the Accommodation Supplement. The
> Allowance is a non-taxable payment.

Thus **Accommodation Assistance is not Accommodation Supplement alone**.
Every fact retains the appropriation name and App ID, including historical
rows. The 2026/27 conditions supply the requested payment-definition evidence;
they do not independently establish unchanged conditions for FY2024/25.
The PDF's 2027/28–2029/30 out-year estimates contribute no facts.
