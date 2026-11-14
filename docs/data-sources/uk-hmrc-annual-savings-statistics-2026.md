# HMRC annual savings statistics 2026 for PolicyEngine/microcosm#1415

[PolicyEngine/microcosm#1415](https://github.com/PolicyEngine/microcosm/issues/1415)
imputes yearly ISA subscriptions per adult by type, so that ISA-limit reforms and the
Lifetime ISA bonus stop scoring zero on Microcosm. These packages give it HMRC's published
ISA statistics and the one published fact that crosses age with amount. Everything here is
a published aggregate; no microdata is involved.
`packages/hmrc/isa_statistics_2026/build_package.py` regenerates all three packages from the
pinned bytes (`--check` compares instead of writing).

## Sources

All three were published by HMRC on GOV.UK under the Open Government Licence v3.0, and all
are committed and stored in R2.

| Package | File | Bytes | sha256 |
|---|---|---|---|
| `hmrc-isa-statistics-2026` | `Individual_Savings_Account_Tables_2026.ods` ("Individual Savings Account (ISA) tables: September 2026", published 16 September 2026) | 60,311 | `a0eaf908…10e3b` |
| `hmrc-lisa-statistics-2026` | `Lifetime_ISA_Tables_2026.ods` ("Lifetime Individual Savings Account (LISA) tables: September 2026") | 17,089 | `bba1520b…02231` |
| `hmrc-cash-isa-limit-reduction-2026` | the HTML of "Cash Individual Savings Account (ISA) limit reduction: tax information and impact note" (17 September 2026) | 103,157 | `3a27fd60…c6212` |

The two workbooks are on the
[release page](https://www.gov.uk/government/statistics/annual-savings-statistics-2026),
which also has the commentary and the methodology note. Budget 2026 (28 October 2026)
announced that the GBP 12,000 cash limit the impact note describes will not go ahead, so the
page may change; the package pins the bytes fetched on 28 October 2026.

## `hmrc-isa-statistics-2026`: 3,230 facts

Record-set ids start `hmrc.isa_statistics_2026.`.

**What it carries, by table:**
- **Table 9.4** (`table9_4.accounts.ty<year>`, `table9_4.amounts.ty<year>`, tax years 2008
  to 2024).
  - What it counts: Adult ISA accounts subscribed to in the year (`hmrc.isa_accounts_subscribed`, thousands)
    and amounts subscribed (`hmrc.isa_amount_subscribed`, GBP million).
  - `isa_component` values: `cash`, `stocks_and_shares`, `innovative_finance`, `lifetime`,
    `stocks_and_shares_insurance` and `all`.
  - Administrative totals from ISA managers' returns. They count accounts, not individuals
    (methodology section 5.1), so their role is `isa_account`, not the `isa_subscriber` of
    Tables 9.7 to 9.9.
  - Products that did not exist in a year carry no fact for it. Innovative Finance ISAs start
    in 2016-17 and Lifetime ISAs in 2017-18.
  - HMRC marks 2024-25 as provisional.
- **Table 9.6** (`table9_6.ty<year>`, 2011 to 2024).
  - What it counts: the market value of Adult ISA funds (`hmrc.isa_market_value`, GBP million) at the end
    of each tax year.
  - Dimensions: `isa_component` and `isa_asset_type`. The stocks-and-shares component's
    lines include `cash_on_deposit`.
  - HMRC's note says Lifetime ISA market values are inside the cash and stocks-and-shares
    totals.
- **Table 9.7** (`table9_7.ty2023.<type>.subscribers` and `.holders`).
  - What it counts: individuals subscribing (`hmrc.isa_subscribers`) in 2023-24, and ISA
    holders who made no further subscription in it (`hmrc.isa_holders`).
  - Rows are 11 `isa_income_band`s plus all ranges, with `total_income` bounds.
  - Columns are 11 `isa_subscription_band`s plus all subscriptions. The bands have an edge
    at GBP 12,000 and an exact GBP 20,000 band.
  - For holders, the no-further-subscription column. The all-holders column restates
    Table 9.10's totals, so it is ported from Table 9.10.
  - It is split into four `isa_type` blocks: `all`, `cash_only`, `stocks_and_shares_only`
    and `cash_and_stocks_and_shares`. In the `all` and `cash_and_stocks_and_shares` blocks,
    the band is the combined amount subscribed.
- **Table 9.8** (`table9_8.ty2023.<sex>.subscribers` and `.holders`): the same counts by 21
  `age_band`s and sex, with types as columns. The all-sexes, all-ages row restates Table
  9.7's totals and is ported from Table 9.7.
- **Table 9.9** (`table9_9.ty2023.subscribers` and `.holders`): the same counts by English
  region and country. HMRC's overseas and unknown row is the statistical scope
  `hmrc:overseas_and_unknown`. The United Kingdom row restates Table 9.7's totals and is
  ported from Table 9.7.
- **Tables 9.10, 9.11 and 9.12**: individuals holding ISAs at the end of 2023-24.
  - Breakdowns: by income and type (9.10), by age and sex (9.11), and by region (9.12).
  - Columns are 12 `isa_market_value_band`s, with each breakdown's total and HMRC's average
    market value per holder (`hmrc.isa_mean_market_value_per_holder`).
  - Table 9.11's all-sexes, all-ages row and Table 9.12's United Kingdom row restate Table
    9.10's all-types "All ranges" row and are ported from Table 9.10.
  - Table 9.12's share of adults aged 18 or over (`hmrc.isa_holders_share_of_adults`) is
    its own `model_output` record set, since it rests on ONS population estimates. It
    carries an `age >= 18` constraint, HMRC's denominator. HMRC does not say whether
    holders aged 16 or 17 are in the numerator.

**Provenance.**
- Tables 9.4 and 9.6 are `administrative`.
- Tables 9.7 to 9.12 are `survey_aggregate`. HMRC estimates them from a sample of
  individuals' accounts matched to the Survey of Personal Incomes, calibrated to the
  totals in Tables 9.4 and 9.6. Income, age, sex and region come from the Survey of
  Personal Incomes.

**Caveats.** The first three are in the facts' notes. The next two come from arithmetic
on the published cells, not from HMRC's text, so they are on this page only.
- **People under "(thousands)" headings.** The column headings of Tables 9.7 to 9.12 say
  "(thousands)", but the cells count individuals. Only that reading fits HMRC's
  commentary, which gives 15 million Adult ISA accounts subscribed to (section 1.1) and 23
  million holders (section 1.4) in 2023-24. It gives no count of subscribers. So those
  measures carry `value_scale: 1`, and the heading text stays as each measure's header
  guard.
- **Coverage.** Tables 9.7 to 9.12 exclude Innovative Finance ISA holders. Their notes do
  not say how Lifetime ISAs are classed. Help to Buy ISAs are inside cash subscriptions
  and market values, without being separated out (HMRC's background and methodology note,
  section 3.4).
- **Totals in more than one table.** HMRC prints some subscriber and holder totals in more
  than one of Tables 9.7 to 9.12. Each is ported once, as chronicle#391 did for GSGB's
  restated row, and `build_package.py` asserts every copy equal to the cell it keeps:
  - Tables 9.7 to 9.9's "All ISA Holders" columns restate Tables 9.10 to 9.12's "Total"
    columns row for row, so holder totals come from the holder tables;
  - the all-sexes, all-ages rows of Tables 9.8 and 9.11 and the United Kingdom rows of
    Tables 9.9 and 9.12 restate the "All ranges" rows of Tables 9.7 and 9.10.

  That leaves out 167 copies, and the package has no semantic duplicate key.
- **Table 9.7's bands against Table 9.4's amounts.** Table 9.7 has no amounts, and its
  bands cannot be reconciled with Table 9.4's amounts subscribed, so a consumer cannot
  bind both. Each subscriber subscribed at least their band's floor (GBP 1, 2,001, …,
  18,001 or 20,000). At those floors, the 13,054,561 subscribers of the `all` block put in
  at least GBP 114.3bn in 2023-24, and the cash-only block alone GBP 78.1bn. Table 9.4 has
  GBP 69,498m in cash ISAs and GBP 31,070m in stocks and shares ISAs (GBP 100.6bn, or
  GBP 103.0bn with Innovative Finance and Lifetime ISAs).
- **Lifetime ISAs in Tables 9.7 to 9.9.** HMRC does not say how they are classed, but the
  2023-24 cells answer most of it:
  - cash-only plus both types, 8,963,286 + 975,669 = 9,938,955, matches Table 9.4's 9,939
    thousand cash ISA accounts;
  - stocks-and-shares-only plus both, 3,115,606 + 975,669 = 4,091,275, matches its 4,091
    thousand stocks and shares ISA accounts;
  - the three type blocks sum exactly to the 13,054,561 subscribers.

  The methodology (section 5.2) says Tables 9.7 to 9.9 are calibrated to the totals in
  Tables 9.4 and 9.6, treating cash and stocks and shares separately. Table 9.4 counts
  Lifetime ISAs (964 thousand accounts in 2023-24) in a row of their own. So someone who
  paid only into a Lifetime ISA is not among Table 9.7's subscribers. HMRC does not say
  whether a Lifetime ISA subscription counts towards a subscriber's band.
- **Not ported:**
  - Table 9.4's average subscription per account, a quotient of ported cells;
  - the Junior ISA rows of Tables 9.4 and 9.6.

## `hmrc-lisa-statistics-2026`: 40 facts

Table 1a's yearly Lifetime ISA withdrawals, 2018-19 to 2025-26
(`hmrc.lisa_statistics_2026.table1a.ty<year>`):
- individuals withdrawing for a house purchase, and the value withdrawn;
- individuals making unauthorised withdrawals, and the value withdrawn;
- the withdrawal charges.

The concepts are `hmrc.lisa_withdrawers`, `hmrc.lisa_withdrawal_value` and
`hmrc.lisa_withdrawal_charges`, by `lisa_withdrawal_reason`. HMRC rounds the numbers of
individuals to the nearest 50. The 2025-26 house-purchase count is 99,750.

The workbook has no subscriptions, holdings or bonus. Lifetime ISA accounts and amounts
subscribed are Table 9.4's `lifetime` rows, and the government's bonus is published in
neither file. Not ported: Table 1b, the same flows by month, and Table 1a's two average
columns.

## `hmrc-cash-isa-limit-reduction-2026`: 2 facts

One sentence of the impact note: "In 2022 to 2023, 78% of cash ISA subscribers aged under
65 subscribed less than £12,000 to a cash ISA and 22% subscribed over £12,000."

- **Record set:** `hmrc.cash_isa_limit_reduction_2026.cash_subscribers_under_65.ty2022`,
  concept `hmrc.cash_isa_subscribers_share` (unit `percent`, aggregation `share`), by
  `cash_isa_subscription_band`.
- **Provenance:** the note names no data source, so the shares are `model_output`.
- **What the sentence leaves open:** where a subscription of exactly GBP 12,000 falls, and
  whether someone who also paid into a stocks-and-shares ISA is counted on the cash amount
  alone. So each row carries its `cash_isa_subscription_band` alone, with no amount bound.
  Bounds of `<` and `>` GBP 12,000 would leave exactly GBP 12,000 in neither row, though
  the shares sum to 100.
- **Not ported:** the page's other "22%", the flat-rate charge on interest on cash held in
  non-cash ISAs, because it is a rate, not this share.

## For Microcosm

Re-pin the UK feed to the merge commit first; the vendor tool refuses a feed that does not
match the pin. Then select:
- **Subscriber cells:** record sets `hmrc.isa_statistics_2026.table9_7.ty2023.*`,
  `table9_8.ty2023.*` and `table9_9.ty2023.*`. The national totals are Table 9.7's "All
  ranges" rows; Tables 9.8 and 9.9 carry no all-sexes, all-ages or United Kingdom row.
- **Growth and composition:** `table9_4.{accounts,amounts}.ty2023` and `.ty2024`, role
  `isa_account`. From 6 April 2024, the Individual Savings Account (Amendment) Regulations
  2024 (SI 2024/350) let a saver subscribe to more than one ISA of the same type in a tax
  year. Table 9.4 counts accounts, so its 2024-25 accounts (provisional: 10,713 thousand
  cash and 4,893 thousand stocks and shares) are no longer a proxy for people, and their
  growth from 2023-24 is not growth in subscribers. In 2023-24 the two still match Table
  9.7's people (see the Lifetime ISA caveat above).
- **Independent checks:** holders and market values from `table9_6.ty2024` and
  `table9_10` to `table9_12`, which carry every holder total, the impact note's record
  set, and Lifetime ISA Table 1a.

Bounds are first-class constraints, so a consumer reads band edges from them rather than
from value ids. Values are already people or pounds, so nothing should be multiplied by
1,000. Aligning the 2023-24 cells with a build year, and choosing between Table 9.7's bands
and Table 9.4's amounts (which cannot both bind; see the caveats), are the consumer's
decisions.
